"""Portfolio Health Score — composite 0-100 score with sub-scores and action items.

Sub-scores:
  - Diversification Index  (HHI-based, 0-100): measures spread of position weights
  - Concentration Risk     (top-3 weight, 0-100): penalises top-heavy portfolios
  - Holding-Period Opportunity (0-100): fraction of unrealised gains within 12 mo of
    a lower tax bracket (i.e. gains that benefit from holding a bit longer)
  - Volatility Health      (0-100): max-drawdown penalty + drawdown warning
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from .tax_regimes import get_regime, DEFAULT_REGIME, get_tax_rate


@dataclass
class HealthSubScore:
    name: str
    score: float          # 0-100
    label: str            # "Good", "Fair", "Poor"
    detail: str           # one-line explanation
    weight: float         # contribution weight (sums to 1.0 across sub-scores)


@dataclass
class ActionItem:
    priority: int         # 1 = highest
    category: str         # "diversification", "concentration", "tax", "risk"
    title: str
    detail: str


@dataclass
class HealthScore:
    overall: float                    # 0-100, weighted composite
    grade: str                        # "A", "B", "C", "D", "F"
    label: str                        # "Excellent", "Good", "Fair", "Poor", "Critical"
    sub_scores: list[HealthSubScore]
    actions: list[ActionItem]         # top 3, sorted by priority


def _label_for(score: float) -> str:
    if score >= 80:
        return "Good"
    if score >= 60:
        return "Fair"
    return "Poor"


def _grade_for(score: float) -> str:
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    if score >= 35:
        return "D"
    return "F"


def _overall_label_for(score: float) -> str:
    if score >= 80:
        return "Excellent"
    if score >= 65:
        return "Good"
    if score >= 50:
        return "Fair"
    if score >= 35:
        return "Poor"
    return "Critical"


def _diversification_score(positions: list) -> tuple[float, str]:
    """HHI-based diversification. Low HHI → high score."""
    if not positions:
        return 0.0, "No positions"
    total_mv = sum(p.get("market_value_eur", 0) for p in positions)
    if total_mv <= 0:
        return 0.0, "No market value"

    n = len(positions)
    hhi = sum((p.get("market_value_eur", 0) / total_mv) ** 2 for p in positions) * 10000

    # Perfect spread (1/n each): HHI = 10000/n
    # Single position: HHI = 10000
    # Map [10000/n .. 10000] → [100 .. 0]
    if n == 1:
        score = 0.0
    else:
        min_hhi = 10000.0 / n
        span = 10000.0 - min_hhi
        # Linear mapping; clamp to [0, 100]
        score = max(0.0, min(100.0, (1.0 - (hhi - min_hhi) / span) * 100))

    eff_n = round(10000 / hhi) if hhi > 0 else n
    detail = f"HHI {round(hhi)}, effective {eff_n} of {n} positions"
    return round(score, 1), detail


def _concentration_score(positions: list) -> tuple[float, str]:
    """Top-3 weight as pct of portfolio. Lower concentration → higher score."""
    if not positions:
        return 100.0, "No positions"
    total_mv = sum(p.get("market_value_eur", 0) for p in positions)
    if total_mv <= 0:
        return 100.0, "No market value"

    sorted_pos = sorted(positions, key=lambda p: p.get("market_value_eur", 0), reverse=True)
    top3_mv = sum(p.get("market_value_eur", 0) for p in sorted_pos[:3])
    top3_pct = top3_mv / total_mv * 100

    # 0-40% → 100; 40-80% → linear 100→20; 80-100% → 20→0
    if top3_pct <= 40:
        score = 100.0
    elif top3_pct <= 80:
        score = 100.0 - (top3_pct - 40) / 40 * 80
    else:
        score = max(0.0, 20.0 - (top3_pct - 80) / 20 * 20)

    tickers = ", ".join(p.get("ticker", "") for p in sorted_pos[:3])
    detail = f"Top 3 ({tickers}) = {round(top3_pct, 1)}% of portfolio"
    return round(score, 1), detail


def _holding_period_score(
    conn: sqlite3.Connection,
    positions: list,
    country: str,
    prices_conn: sqlite3.Connection | None,
) -> tuple[float, str]:
    """Fraction of unrealised gains that would benefit from crossing a bracket threshold.

    Looks at each FIFO lot's holding age and checks whether holding it up to 12 more
    months would reduce the tax rate (i.e. moves into the next lower bracket).
    Score = 100 when none of the gains are 'bracket-imminent'.
    Score falls as more EUR of gains sit within 12 months of a rate reduction.
    """
    regime = get_regime(country)
    brackets = regime.stock_brackets  # list of TaxBracket with .min_years and .rate

    # Build (ticker, buy_date, qty, cost_per_share_eur) from position_lots in analytics result
    # Passed via positions list which contains lot data from analytics.position_lots
    if not positions:
        return 100.0, "No open positions"

    today = date.today()
    total_gain = 0.0
    bracket_gain = 0.0  # gain currently taxed at a higher rate but within 12mo of next bracket

    _pconn = prices_conn if prices_conn is not None else conn
    if conn is None:
        return 100.0, "No data"

    # Fetch lots from DB directly for robustness
    try:
        rows = conn.execute(
            """SELECT ticker, date, SUM(quantity) as qty,
                      AVG(price_per_share) as avg_cost
               FROM transactions
               WHERE type='BUY' AND asset_class='stock'
               GROUP BY ticker, date
               ORDER BY ticker, date"""
        ).fetchall()
    except Exception:
        return 100.0, "Unable to query lots"

    # Current prices (quick map)
    price_map: dict[str, float] = {}
    pos_map = {p["ticker"]: p for p in positions}
    for p in positions:
        ticker = p["ticker"]
        mv = p.get("market_value_eur", 0)
        qty = p.get("quantity", 0)
        if qty and qty > 0:
            price_map[ticker] = mv / qty

    # FX for converting to EUR
    fx_row = (_pconn or conn).execute(
        "SELECT eur_usd FROM fx_rates ORDER BY date DESC LIMIT 1"
    ).fetchone() if conn else None
    eur_usd = fx_row[0] if fx_row else 1.10

    ticker_currency: dict[str, str] = {}
    for p in positions:
        tk = p["ticker"]
        if tk not in ticker_currency:
            row = conn.execute(
                "SELECT currency FROM transactions WHERE ticker=? AND type IN ('BUY','SELL') "
                "ORDER BY date DESC LIMIT 1", (tk,)
            ).fetchone()
            ticker_currency[tk] = row[0] if row else "EUR"

    def to_eur(amount: float, currency: str) -> float:
        if currency == "EUR":
            return amount
        return amount / eur_usd

    imminent_count = 0

    for row in rows:
        ticker, buy_date_raw, qty, avg_cost_raw = row
        if ticker not in pos_map:
            continue  # closed position
        if not qty or qty <= 0:
            continue

        try:
            buy_date = date.fromisoformat(str(buy_date_raw)[:10])
        except (ValueError, TypeError):
            continue

        holding_years = (today - buy_date).days / 365.25
        current_price = price_map.get(ticker)
        if current_price is None:
            continue

        currency = ticker_currency.get(ticker, "EUR")
        cost_eur = to_eur(avg_cost_raw * qty, currency)
        value_eur = current_price * qty  # already in EUR from analytics
        lot_gain = value_eur - cost_eur
        if lot_gain <= 0:
            continue  # loss lots don't benefit from time

        total_gain += lot_gain
        current_rate = get_tax_rate(brackets, holding_years)

        # Check if any bracket threshold is within the next 12 months
        for bracket in brackets:
            if bracket.min_years > holding_years and bracket.min_years <= holding_years + 1.0:
                next_rate = bracket.rate
                if next_rate < current_rate:
                    bracket_gain += lot_gain
                    imminent_count += 1
                    break  # only count once per lot

    if total_gain <= 0:
        return 100.0, "No unrealised gains to optimise"

    pct_imminent = bracket_gain / total_gain * 100
    # Score: 100 when 0% imminent; 0 when 100% imminent
    score = max(0.0, 100.0 - pct_imminent)

    if imminent_count == 0:
        detail = "No gains approaching a lower tax bracket"
    else:
        detail = (
            f"{round(bracket_gain, 0):.0f} EUR of gains within 12 mo of a lower bracket "
            f"({imminent_count} lot{'s' if imminent_count != 1 else ''})"
        )
    return round(score, 1), detail


def _volatility_score(analytics_summary: dict) -> tuple[float, str]:
    """Max-drawdown based volatility health. Smaller drawdown → higher score."""
    max_dd = abs(analytics_summary.get("max_drawdown_pct", 0) or 0)

    # 0% DD → 100; 10% → 90; 30% → 60; 50% → 30; >=70% → 0
    if max_dd == 0:
        score = 100.0
    elif max_dd <= 10:
        score = 100.0 - max_dd
    elif max_dd <= 30:
        score = 90.0 - (max_dd - 10) * 1.5
    elif max_dd <= 50:
        score = 60.0 - (max_dd - 30) * 1.5
    else:
        score = max(0.0, 30.0 - (max_dd - 50) * 1.5)

    peak_date = analytics_summary.get("max_drawdown_peak_date", "")
    trough_date = analytics_summary.get("max_drawdown_trough_date", "")
    if peak_date and trough_date and peak_date != trough_date:
        detail = f"Max drawdown {round(max_dd, 1)}% ({peak_date} → {trough_date})"
    else:
        detail = f"Max drawdown {round(max_dd, 1)}%"
    return round(score, 1), detail


def _build_actions(
    div_score: float,
    conc_score: float,
    hp_score: float,
    vol_score: float,
    positions: list,
    div_detail: str,
    conc_detail: str,
    hp_detail: str,
    vol_detail: str,
) -> list[ActionItem]:
    """Produce up to 3 prioritised action items from sub-score signals."""
    candidates: list[ActionItem] = []

    if div_score < 60:
        candidates.append(ActionItem(
            priority=2,
            category="diversification",
            title="Improve diversification",
            detail=f"Portfolio is concentrated — {div_detail}. Consider adding positions in "
                   f"uncorrelated sectors or asset classes.",
        ))

    if conc_score < 60:
        sorted_pos = sorted(positions, key=lambda p: p.get("market_value_eur", 0), reverse=True)
        top_ticker = sorted_pos[0].get("ticker", "") if sorted_pos else ""
        candidates.append(ActionItem(
            priority=1,
            category="concentration",
            title="Reduce top-position concentration",
            detail=f"{conc_detail}. Consider trimming the largest position ({top_ticker}) to bring "
                   f"portfolio balance closer to a 20% single-name cap.",
        ))

    if hp_score < 70:
        candidates.append(ActionItem(
            priority=2,
            category="tax",
            title="Hold to reach lower tax bracket",
            detail=hp_detail + ". Holding these lots a bit longer will reduce capital gains tax.",
        ))

    if vol_score < 60:
        candidates.append(ActionItem(
            priority=3,
            category="risk",
            title="Portfolio experiencing high drawdown",
            detail=vol_detail + ". Review position sizing and consider defensive hedges.",
        ))

    # Fallback when portfolio is healthy
    if not candidates:
        candidates.append(ActionItem(
            priority=3,
            category="diversification",
            title="Portfolio looks healthy",
            detail="No critical issues detected. Continue monitoring diversification and tax efficiency.",
        ))

    # Sort by priority, take top 3
    candidates.sort(key=lambda a: a.priority)
    return candidates[:3]


def compute_health_score(
    positions: list,
    analytics_summary: dict,
    conn: sqlite3.Connection | None = None,
    country: str = DEFAULT_REGIME,
    prices_conn: sqlite3.Connection | None = None,
) -> HealthScore:
    """Compute composite portfolio health score.

    positions: list of dicts with keys ticker, market_value_eur, quantity
    analytics_summary: the 'summary' sub-dict from _serialize_report_data
    conn: portfolio DB connection (needed for holding-period sub-score)
    country: ISO country code for tax regime
    prices_conn: shared prices DB
    """
    WEIGHTS = {
        "diversification": 0.35,
        "concentration":   0.30,
        "holding_period":  0.25,
        "volatility":      0.10,
    }

    div_score, div_detail = _diversification_score(positions)
    conc_score, conc_detail = _concentration_score(positions)
    vol_score, vol_detail = _volatility_score(analytics_summary)

    if conn is not None:
        hp_score, hp_detail = _holding_period_score(conn, positions, country, prices_conn)
    else:
        hp_score, hp_detail = 100.0, "Holding-period data unavailable"

    overall = (
        div_score  * WEIGHTS["diversification"] +
        conc_score * WEIGHTS["concentration"] +
        hp_score   * WEIGHTS["holding_period"] +
        vol_score  * WEIGHTS["volatility"]
    )
    overall = round(overall, 1)

    sub_scores = [
        HealthSubScore("Diversification",    div_score,  _label_for(div_score),  div_detail,  WEIGHTS["diversification"]),
        HealthSubScore("Concentration Risk", conc_score, _label_for(conc_score), conc_detail, WEIGHTS["concentration"]),
        HealthSubScore("Tax Efficiency",     hp_score,   _label_for(hp_score),   hp_detail,   WEIGHTS["holding_period"]),
        HealthSubScore("Drawdown Risk",      vol_score,  _label_for(vol_score),  vol_detail,  WEIGHTS["volatility"]),
    ]

    actions = _build_actions(
        div_score, conc_score, hp_score, vol_score,
        positions, div_detail, conc_detail, hp_detail, vol_detail,
    )

    return HealthScore(
        overall=overall,
        grade=_grade_for(overall),
        label=_overall_label_for(overall),
        sub_scores=sub_scores,
        actions=actions,
    )


def serialize_health_score(hs: HealthScore) -> dict:
    return {
        "overall": hs.overall,
        "grade": hs.grade,
        "label": hs.label,
        "sub_scores": [
            {
                "name": s.name,
                "score": s.score,
                "label": s.label,
                "detail": s.detail,
                "weight": s.weight,
            }
            for s in hs.sub_scores
        ],
        "actions": [
            {
                "priority": a.priority,
                "category": a.category,
                "title": a.title,
                "detail": a.detail,
            }
            for a in hs.actions
        ],
    }
