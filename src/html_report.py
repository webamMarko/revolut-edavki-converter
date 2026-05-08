"""HTML report generator for portfolio analytics."""

import html
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=False,          # CSS/JS must not be HTML-escaped
    keep_trailing_newline=True,
)


def query_real_estate(conn: sqlite3.Connection, prices_conn: sqlite3.Connection | None = None) -> dict:
    """Return real estate properties with valuations and price history."""
    _pconn = prices_conn if prices_conn is not None else conn
    try:
        # Properties from user DB, valuations from prices DB
        props_raw = conn.execute("SELECT * FROM real_estate_properties ORDER BY purchase_date").fetchall()
    except Exception:
        return {}
    if not props_raw:
        return {}

    # Build props with latest valuation from prices DB
    props = []
    for p in props_raw:
        p_dict = dict(p)
        val_row = _pconn.execute(
            "SELECT close, date FROM daily_prices WHERE ticker = ? AND currency = 'EUR' ORDER BY date DESC LIMIT 1",
            (p["ticker"],)
        ).fetchone()
        p_dict["estimated_value_eur"] = val_row[0] if val_row else None
        p_dict["estimated_date"] = val_row[1] if val_row else None
        props.append(p_dict)
    try:
        pass  # props already fetched
    except Exception:
        return {}

    if not props:
        return {}

    prop_list = []
    total_purchase = 0.0
    total_estimated = 0.0

    for row in props:
        p = dict(row)
        purchase = p["purchase_price_eur"] or 0
        estimated = p["estimated_value_eur"] or purchase
        gain = estimated - purchase
        gain_pct = (gain / purchase * 100) if purchase > 0 else 0
        total_purchase += purchase
        total_estimated += estimated
        prop_list.append({
            "ticker": p["ticker"],
            "name": p["name"],
            "address": p.get("address", ""),
            "municipality": p.get("municipality", ""),
            "property_type": p["property_type"],
            "area_m2": p["area_m2"],
            "purchase_price_eur": round(purchase, 2),
            "purchase_date": p["purchase_date"],
            "estimated_value_eur": round(estimated, 2),
            "estimated_date": p.get("estimated_date") or "",
            "unrealized_gain_eur": round(gain, 2),
            "unrealized_gain_pct": round(gain_pct, 2),
        })

    # Price history per property
    tickers = [p["ticker"] for p in prop_list]
    history = {}
    for ticker in tickers:
        rows = conn.execute(
            "SELECT date, close FROM daily_prices WHERE ticker = ? AND currency = 'EUR' ORDER BY date",
            (ticker,)
        ).fetchall()
        if rows:
            history[ticker] = {
                "dates": [r[0] for r in rows],
                "values": [round(r[1], 2) for r in rows],
            }

    total_gain = total_estimated - total_purchase
    return {
        "properties": prop_list,
        "total_purchase_eur": round(total_purchase, 2),
        "total_estimated_eur": round(total_estimated, 2),
        "total_gain_eur": round(total_gain, 2),
        "total_gain_pct": round(total_gain / total_purchase * 100, 2) if total_purchase > 0 else 0,
        "history": history,
    }


def query_transactions(conn: sqlite3.Connection,
                       year: int | None = None,
                       start_date: datetime | None = None,
                       end_date: datetime | None = None) -> list[dict]:
    """Query transactions from database with optional date filtering."""
    conditions = []
    params = []

    if year:
        conditions.append("date LIKE ?")
        params.append(f"{year}-%")
    else:
        if start_date:
            conditions.append("date >= ?")
            params.append(start_date.strftime("%Y-%m-%d"))
        if end_date:
            conditions.append("date <= ?")
            params.append(end_date.strftime("%Y-%m-%d 23:59:59"))

    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = conn.execute(
        f"""SELECT date, ticker, type, quantity, price_per_share, total_amount,
                   currency, fx_rate, asset_class
            FROM transactions{where} ORDER BY date DESC""",
        params,
    ).fetchall()
    return [dict(r) for r in rows]



def query_fire_config(conn: sqlite3.Connection) -> dict | None:
    """Return full FIRE config dict or None if not configured.

    Keys: target, annual_expenses, annual_income, withdrawal_rate, inflation_rate
    """
    try:
        rows = {r[0]: r[1] for r in conn.execute(
            "SELECT key, value FROM metadata WHERE key LIKE 'fire_%'"
        ).fetchall()}
        if "fire_annual_expenses" not in rows:
            return None
        expenses  = float(rows["fire_annual_expenses"])
        income    = float(rows.get("fire_annual_income", 0))
        rate      = float(rows.get("fire_withdrawal_rate", 4.0))
        inflation = float(rows.get("fire_inflation", 2.5))
        if rate <= 0:
            return None
        target = round((expenses - income) / (rate / 100), 2)
        return {
            "target": target,
            "annual_expenses": expenses,
            "annual_income": income,
            "withdrawal_rate": rate,
            "inflation_rate": inflation,
        }
    except Exception:
        return None


def query_investment_notes(conn: sqlite3.Connection) -> list[dict]:
    """Return investment notes enriched with live ticker data."""
    try:
        from .notes import query_notes_for_report
        return query_notes_for_report(conn)
    except Exception:
        return []


def _query_dividend_data(conn: sqlite3.Connection | None) -> dict:
    """Query per-ticker and monthly dividend data from transactions."""
    if conn is None:
        return {"by_ticker": [], "by_month": [], "total_eur": 0}

    dividend_types = ("DIVIDEND", "BOND COUPON", "INTEREST PAID", "STAKING REWARD", "LEARN REWARD")
    placeholders = ",".join("?" for _ in dividend_types)

    # Per-ticker totals
    rows = conn.execute(f"""
        SELECT ticker, SUM(
            CASE WHEN fx_rate > 0 AND currency != 'EUR' THEN ABS(total_amount) / fx_rate
                 ELSE ABS(total_amount) END
        ) as total_eur,
        COUNT(*) as payment_count
        FROM transactions
        WHERE type IN ({placeholders}) AND total_amount IS NOT NULL AND total_amount != 0
        GROUP BY ticker
        ORDER BY total_eur DESC
    """, dividend_types).fetchall()

    by_ticker = [
        {"ticker": r[0] or "Unknown", "total_eur": round(r[1], 2), "count": r[2]}
        for r in rows
    ]
    total_eur = round(sum(t["total_eur"] for t in by_ticker), 2)

    # Monthly totals
    rows = conn.execute(f"""
        SELECT SUBSTR(date, 1, 7) as month,
        SUM(
            CASE WHEN fx_rate > 0 AND currency != 'EUR' THEN ABS(total_amount) / fx_rate
                 ELSE ABS(total_amount) END
        ) as total_eur
        FROM transactions
        WHERE type IN ({placeholders}) AND total_amount IS NOT NULL AND total_amount != 0
        GROUP BY month
        ORDER BY month
    """, dividend_types).fetchall()

    by_month = [{"month": r[0], "total_eur": round(r[1], 2)} for r in rows]

    # TTM (trailing 12 months) per-ticker for yield calculation
    from datetime import datetime as _dt, timedelta as _td
    ttm_start = (_dt.now() - _td(days=365)).strftime("%Y-%m-%d")
    rows = conn.execute(f"""
        SELECT ticker, SUM(
            CASE WHEN fx_rate > 0 AND currency != 'EUR' THEN ABS(total_amount) / fx_rate
                 ELSE ABS(total_amount) END
        ) as ttm_eur
        FROM transactions
        WHERE type IN ({placeholders}) AND total_amount IS NOT NULL AND total_amount != 0
          AND date >= ?
        GROUP BY ticker
    """, (*dividend_types, ttm_start)).fetchall()
    ttm_by_ticker = {r[0]: round(r[1], 2) for r in rows}

    return {"by_ticker": by_ticker, "by_month": by_month, "total_eur": total_eur,
            "ttm_by_ticker": ttm_by_ticker}


def _query_position_price_history(conn: sqlite3.Connection, tickers: list[str]) -> dict:
    """Return daily EUR price history for each ticker (last 2 years)."""
    history = {}
    if not tickers or conn is None:
        return history

    # Get EUR/USD rates for conversion
    fx_rows = conn.execute(
        "SELECT date, eur_usd FROM fx_rates ORDER BY date"
    ).fetchall()
    fx_map = {r[0]: r[1] for r in fx_rows}

    from datetime import date as _date, timedelta as _timedelta

    def eur_usd_for(date: str) -> float:
        # Walk backwards up to 5 days to find a rate
        for i in range(5):
            d = (_date.fromisoformat(date) - _timedelta(days=i)).isoformat()
            if d in fx_map:
                return fx_map[d]
        return 1.1  # fallback

    for ticker in tickers:
        # Strip asset-class prefix for DB lookup
        db_ticker = ticker
        for prefix in ("CFD:", "CRYPTO:", "SAVINGS:"):
            if ticker.startswith(prefix):
                db_ticker = ticker[len(prefix):]
                break

        rows = conn.execute(
            """SELECT date, close, currency FROM daily_prices
               WHERE ticker = ? ORDER BY date DESC LIMIT 730""",
            (db_ticker,)
        ).fetchall()
        if not rows:
            continue
        rows = list(reversed(rows))
        dates, values = [], []
        for r in rows:
            date, close, currency = r[0], r[1], r[2]
            if currency == "EUR":
                price_eur = close
            else:
                rate = eur_usd_for(date)
                price_eur = close / rate if rate else close
            dates.append(date)
            values.append(round(price_eur, 4))
        if dates:
            history[ticker] = {"dates": dates, "values": values}
    return history


def _query_company_names(conn: sqlite3.Connection | None, tickers: list[str]) -> dict:
    """Return {ticker: company_name} from cached metadata."""
    if not tickers or conn is None:
        return {}
    names = {}
    for ticker in tickers:
        # Strip asset-class prefix for lookup
        db_ticker = ticker
        for prefix in ("CFD:", "CRYPTO:", "SAVINGS:"):
            if ticker.startswith(prefix):
                db_ticker = ticker[len(prefix):]
                break
        row = conn.execute(
            "SELECT value FROM metadata WHERE key = ?", (f"company_name:{db_ticker}",)
        ).fetchone()
        if row and row[0]:
            names[ticker] = row[0]
    return names


def _query_currency_exposure(conn: sqlite3.Connection, positions: list) -> list[dict]:
    """Determine native currency of each position and compute exposure breakdown."""
    if not conn or not positions:
        return []

    # Get the most recent trade currency for each ticker
    ticker_currency = {}
    for pos in positions:
        ticker = pos.ticker if hasattr(pos, 'ticker') else pos.get('ticker', '')
        # Strip prefix for DB lookup
        db_ticker = ticker
        for prefix in ("CFD:", "CRYPTO:", "SAVINGS:"):
            if ticker.startswith(prefix):
                db_ticker = ticker[len(prefix):]
                break
        row = conn.execute(
            "SELECT currency FROM transactions WHERE ticker = ? AND type IN ('BUY','SELL') "
            "AND currency IS NOT NULL ORDER BY date DESC LIMIT 1",
            (db_ticker,)
        ).fetchone()
        if row:
            ticker_currency[ticker] = row[0]
        else:
            # Check daily_prices for currency
            row = conn.execute(
                "SELECT currency FROM daily_prices WHERE ticker = ? LIMIT 1",
                (db_ticker,)
            ).fetchone()
            ticker_currency[ticker] = row[0] if row else "EUR"

    # Group market value by currency
    currency_totals = {}
    for pos in positions:
        ticker = pos.ticker if hasattr(pos, 'ticker') else pos.get('ticker', '')
        mv = pos.market_value_eur if hasattr(pos, 'market_value_eur') else pos.get('market_value_eur', 0)
        cur = ticker_currency.get(ticker, "EUR")
        currency_totals[cur] = currency_totals.get(cur, 0) + mv

    total = sum(currency_totals.values()) or 1
    return sorted(
        [{"currency": c, "value_eur": round(v, 2), "pct": round(v / total * 100, 1)}
         for c, v in currency_totals.items()],
        key=lambda x: x["value_eur"],
        reverse=True,
    )


def _query_sector_allocation(conn: sqlite3.Connection | None, positions: list) -> dict:
    """Build sector and industry allocation from position weights + metadata."""
    if not conn or not positions:
        return {"sectors": [], "industries": []}

    # Load sector/industry metadata
    sector_map = {}
    industry_map = {}
    rows = conn.execute("SELECT key, value FROM metadata WHERE key LIKE 'sector:%'").fetchall()
    for k, v in rows:
        sector_map[k[len("sector:"):]] = v
    rows = conn.execute("SELECT key, value FROM metadata WHERE key LIKE 'industry:%'").fetchall()
    for k, v in rows:
        industry_map[k[len("industry:"):]] = v

    # Aggregate by sector and industry
    sector_totals = {}
    industry_totals = {}
    total_mv = 0
    for pos in positions:
        ticker = pos.ticker if hasattr(pos, 'ticker') else pos.get('ticker', '')
        mv = pos.market_value_eur if hasattr(pos, 'market_value_eur') else pos.get('market_value_eur', 0)
        if mv <= 0:
            continue
        # Strip prefix
        db_ticker = ticker
        for prefix in ("CFD:", "CRYPTO:", "SAVINGS:"):
            if ticker.startswith(prefix):
                db_ticker = ticker[len(prefix):]
                break
        sector = sector_map.get(db_ticker, "Other")
        industry = industry_map.get(db_ticker, "Other")
        sector_totals[sector] = sector_totals.get(sector, 0) + mv
        industry_totals[industry] = industry_totals.get(industry, 0) + mv
        total_mv += mv

    if total_mv == 0:
        return {"sectors": [], "industries": []}

    sectors = sorted(
        [{"name": s, "value_eur": round(v, 2), "pct": round(v / total_mv * 100, 1)}
         for s, v in sector_totals.items()],
        key=lambda x: x["value_eur"], reverse=True,
    )
    industries = sorted(
        [{"name": i, "value_eur": round(v, 2), "pct": round(v / total_mv * 100, 1)}
         for i, v in industry_totals.items()],
        key=lambda x: x["value_eur"], reverse=True,
    )
    return {"sectors": sectors, "industries": industries}


def _query_geographic_allocation(conn: sqlite3.Connection | None, positions: list) -> dict:
    """Build geographic (country) allocation from position weights + metadata."""
    if not conn or not positions:
        return {"countries": []}

    country_map = {}
    rows = conn.execute("SELECT key, value FROM metadata WHERE key LIKE 'country:%'").fetchall()
    for k, v in rows:
        country_map[k[len("country:"):]] = v

    country_totals = {}
    total_mv = 0
    for pos in positions:
        ticker = pos.ticker if hasattr(pos, 'ticker') else pos.get('ticker', '')
        mv = pos.market_value_eur if hasattr(pos, 'market_value_eur') else pos.get('market_value_eur', 0)
        if mv <= 0:
            continue
        db_ticker = ticker
        for prefix in ("CFD:", "CRYPTO:", "SAVINGS:"):
            if ticker.startswith(prefix):
                db_ticker = ticker[len(prefix):]
                break
        country = country_map.get(db_ticker, "Other")
        country_totals[country] = country_totals.get(country, 0) + mv
        total_mv += mv

    if total_mv == 0:
        return {"countries": []}

    countries = sorted(
        [{"name": c, "value_eur": round(v, 2), "pct": round(v / total_mv * 100, 1)}
         for c, v in country_totals.items()],
        key=lambda x: x["value_eur"], reverse=True,
    )
    return {"countries": countries}


def _compute_concentration_risk(positions: list) -> dict:
    """Compute concentration risk metrics and flag over-concentrated positions."""
    if not positions:
        return {"warnings": [], "metrics": {}}

    total_mv = sum(
        (p.market_value_eur if hasattr(p, 'market_value_eur') else p.get('market_value_eur', 0))
        for p in positions
    )
    if total_mv <= 0:
        return {"warnings": [], "metrics": {}}

    weights = []
    for p in positions:
        ticker = p.ticker if hasattr(p, 'ticker') else p.get('ticker', '')
        mv = p.market_value_eur if hasattr(p, 'market_value_eur') else p.get('market_value_eur', 0)
        weights.append({"ticker": ticker, "weight_pct": round(mv / total_mv * 100, 2), "value_eur": round(mv, 2)})

    weights.sort(key=lambda x: x["weight_pct"], reverse=True)

    # Herfindahl-Hirschman Index
    hhi = sum((w["weight_pct"] / 100) ** 2 for w in weights) * 10000

    # Effective number of positions
    sum_sq = sum((w["weight_pct"] / 100) ** 2 for w in weights)
    effective_n = round(1 / sum_sq) if sum_sq > 0 else len(weights)

    # Top-N concentration
    top5_pct = sum(w["weight_pct"] for w in weights[:5])
    top10_pct = sum(w["weight_pct"] for w in weights[:10])

    # Warnings: positions exceeding 20% portfolio weight
    warnings = [
        {"ticker": w["ticker"], "weight_pct": w["weight_pct"], "value_eur": w["value_eur"]}
        for w in weights if w["weight_pct"] > 20
    ]

    return {
        "warnings": warnings,
        "metrics": {
            "hhi": round(hhi),
            "effective_n": effective_n,
            "top5_pct": round(top5_pct, 1),
            "top10_pct": round(top10_pct, 1),
            "total_positions": len(weights),
            "largest_ticker": weights[0]["ticker"] if weights else "",
            "largest_pct": weights[0]["weight_pct"] if weights else 0,
        },
    }


def _compute_correlation_matrix(conn: sqlite3.Connection | None,
                                positions: list) -> dict | None:
    """Compute pairwise return correlation matrix for current holdings."""
    if not conn or not positions:
        return None

    import numpy as np

    # Get tickers with enough weight (top 15 by market value, skip tiny positions)
    sorted_pos = sorted(positions,
                        key=lambda p: p.market_value_eur if hasattr(p, 'market_value_eur') else p.get('market_value_eur', 0),
                        reverse=True)
    tickers = []
    for p in sorted_pos[:15]:
        ticker = p.ticker if hasattr(p, 'ticker') else p.get('ticker', '')
        if ticker:
            tickers.append(ticker)

    if len(tickers) < 2:
        return None

    # Load daily prices (last 1 year) for each ticker
    from datetime import date as _date, timedelta as _td
    one_year_ago = (_date.today() - _td(days=365)).isoformat()

    # Load FX rates for USD→EUR conversion
    fx_rows = conn.execute(
        "SELECT date, eur_usd FROM fx_rates WHERE date >= ? ORDER BY date",
        (one_year_ago,)
    ).fetchall()
    fx_map = {r[0]: r[1] for r in fx_rows}

    def eur_usd_for(dt: str) -> float:
        for i in range(5):
            d = (_date.fromisoformat(dt) - _td(days=i)).isoformat()
            if d in fx_map:
                return fx_map[d]
        return 1.1

    price_series = {}
    for ticker in tickers:
        db_ticker = ticker
        for prefix in ("CFD:", "CRYPTO:", "SAVINGS:"):
            if ticker.startswith(prefix):
                db_ticker = ticker[len(prefix):]
                break
        rows = conn.execute(
            "SELECT date, close, currency FROM daily_prices WHERE ticker = ? AND date >= ? ORDER BY date",
            (db_ticker, one_year_ago)
        ).fetchall()
        if len(rows) < 30:  # need minimum data for meaningful correlation
            continue
        prices = {}
        for r in rows:
            price = r[1] / eur_usd_for(r[0]) if r[2] != "EUR" else r[1]
            prices[r[0]] = price
        price_series[ticker] = prices

    valid_tickers = [t for t in tickers if t in price_series]
    if len(valid_tickers) < 2:
        return None

    # Align dates: use intersection of all dates
    all_dates = set(price_series[valid_tickers[0]].keys())
    for tk in valid_tickers[1:]:
        all_dates &= set(price_series[tk].keys())
    sorted_dates = sorted(all_dates)

    if len(sorted_dates) < 30:
        return None

    # Build returns matrix
    n = len(valid_tickers)
    returns_matrix = []
    for tk in valid_tickers:
        prices = [price_series[tk][d] for d in sorted_dates]
        returns = []
        for i in range(1, len(prices)):
            if prices[i - 1] > 0:
                returns.append((prices[i] - prices[i - 1]) / prices[i - 1])
            else:
                returns.append(0)
        returns_matrix.append(returns)

    # Compute correlation matrix
    arr = np.array(returns_matrix)
    corr = np.corrcoef(arr)

    # Convert to serializable format
    matrix = []
    for i in range(n):
        row = []
        for j in range(n):
            val = float(corr[i][j])
            if np.isnan(val):
                val = 0.0
            row.append(round(val, 2))
        matrix.append(row)

    return {
        "tickers": valid_tickers,
        "matrix": matrix,
        "data_points": len(sorted_dates),
    }


def _serialize_report_data(analytics, tax_by_year, transactions: list[dict],
                           per_class: dict | None = None,
                           available_classes: list[str] | None = None,
                           real_estate: dict | None = None,
                           fire_config: dict | None = None,
                           investment_notes: list[dict] | None = None,
                           conn: sqlite3.Connection | None = None,
                           country: str = "SI") -> dict:
    """Convert analytics/tax results + transactions to JSON-safe dict."""
    from .tax_regimes import get_regime, REGIMES
    from .i18n import get_translations, get_locale_for_country

    regime = get_regime(country)
    lang = get_locale_for_country(country)

    # FX rate for display currency conversion (EUR → regime currency)
    fx_display_rate = 1.0  # EUR→EUR
    if regime.currency != "EUR" and conn is not None:
        row = conn.execute(
            "SELECT eur_usd FROM fx_rates ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if row:
            fx_display_rate = row[0]  # 1 EUR = X USD

    daily = analytics.daily_series
    data = {
        "scope": analytics.scope,
        "country": country,
        "locale": regime.locale,
        "currency": regime.currency,
        "fx_display_rate": round(fx_display_rate, 6),
        "lang": lang,
        "regime": {
            "country_code": regime.country_code,
            "country_name": regime.country_name,
            "currency": regime.currency,
            "locale": regime.locale,
            "description": regime.description,
            "netting": regime.netting,
            "std_cost_rate": regime.std_cost_rate,
            "std_cost_rate_leveraged": regime.std_cost_rate_leveraged,
            "crypto_exemption_threshold": regime.crypto_exemption_threshold,
            "crypto_exemption_type": regime.crypto_exemption_type,
            "crypto_holding_exempt_years": regime.crypto_holding_exempt_years,
            "dividend_tax_rate": regime.dividend_tax_rate,
            "flat_rate": regime.flat_rate,
            "legal_refs": regime.legal_refs,
            "stock_brackets": [{"min_years": b.min_years, "rate": b.rate} for b in regime.stock_brackets],
            "cfd_brackets": [{"min_years": b.min_years, "rate": b.rate} for b in regime.cfd_brackets],
            "crypto_brackets": [{"min_years": b.min_years, "rate": b.rate} for b in regime.crypto_brackets],
            "savings_brackets": [{"min_years": b.min_years, "rate": b.rate} for b in regime.savings_brackets],
        },
        "available_regimes": [
            {"code": r.country_code, "name": r.country_name, "currency": r.currency}
            for r in REGIMES.values()
        ],
        "i18n": get_translations(lang),
        "start_date": analytics.start_date,
        "end_date": analytics.end_date,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "summary": {
            "portfolio_value_eur": round(analytics.portfolio_value_eur, 2),
            "total_invested_eur": round(analytics.total_invested_eur, 2),
            "absolute_gain_eur": round(analytics.absolute_gain_eur, 2),
            "total_return_pct": round(analytics.total_return_pct, 2),
            "cagr_pct": round(analytics.cagr_pct, 2) if analytics.cagr_pct else None,
            "twr_pct": round(analytics.twr_pct, 2) if analytics.twr_pct else None,
            "max_drawdown_pct": round(analytics.max_drawdown_pct, 2),
            "max_drawdown_peak_date": analytics.max_drawdown_peak_date,
            "max_drawdown_trough_date": analytics.max_drawdown_trough_date,
            "risk_metrics": analytics.risk_metrics,
        },
        "gains": {
            "realized_eur": round(analytics.total_realized_gain_eur, 2),
            "unrealized_eur": round(analytics.total_unrealized_gain_eur, 2),
            "dividends_eur": round(analytics.total_dividends_eur, 2),
            "fees_eur": round(analytics.total_fees_eur, 2),
        },
        "daily_series": {
            "dates": [str(d) for d in daily.index],
            "value_eur": [round(float(v), 2) for v in daily["value_eur"]],
            "invested_eur": [round(float(v), 2) for v in daily["invested_eur"]],
            "dividends_eur": [round(float(v), 2) for v in daily["dividends_eur"]],
            "realized_gain_eur": [round(float(v), 2) for v in daily["realized_gain_eur"]],
            "perf_index": [round(float(v), 2) for v in daily["perf_index"]] if "perf_index" in daily.columns else [],
        },
        "benchmark_series": {},
        "benchmarks": [
            {
                "name": b.name,
                "return_pct": round(b.return_pct, 2),
                "portfolio_return_pct": round(b.portfolio_return_pct, 2),
                "alpha_pct": round(b.alpha_pct, 2),
                "sharpe_ratio": b.sharpe_ratio,
                "max_drawdown_pct": b.max_drawdown_pct,
            }
            for b in analytics.benchmarks
        ],
        "positions": sorted(
            [
                {
                    "ticker": p.ticker,
                    "quantity": round(p.quantity, 4),
                    "cost_basis_eur": round(p.cost_basis_eur, 2),
                    "avg_cost_eur": round(p.cost_basis_eur / p.quantity, 4) if p.quantity else 0,
                    "market_value_eur": round(p.market_value_eur, 2),
                    "unrealized_gain_eur": round(p.unrealized_gain_eur, 2),
                    "unrealized_gain_pct": round(p.unrealized_gain_pct, 2),
                    "weight_pct": round(p.weight_pct, 2),
                    "realized_gain_eur": round(p.realized_gain_eur, 2),
                }
                for p in analytics.positions
            ],
            key=lambda x: x["market_value_eur"],
            reverse=True,
        ),
        "closed_positions": sorted(
            [
                {
                    "ticker": p.ticker,
                    "total_cost_eur": round(p.total_cost_eur, 2),
                    "total_proceeds_eur": round(p.total_proceeds_eur, 2),
                    "realized_gain_eur": round(p.realized_gain_eur, 2),
                    "realized_gain_pct": round(p.realized_gain_pct, 2),
                }
                for p in analytics.closed_positions
            ],
            key=lambda x: abs(x["realized_gain_eur"]),
            reverse=True,
        ),
        "position_lots": {
            ticker: [
                {"qty": round(qty, 4), "cost_eur": round(cost, 4), "date": date}
                for qty, cost, date in lots
            ]
            for ticker, lots in analytics.position_lots.items()
        },
        "tax": None,
        "transactions": [
            {
                "date": (t["date"] or "")[:10],
                "ticker": t["ticker"] or "",
                "type": t["type"] or "",
                "quantity": round(t["quantity"], 4) if t["quantity"] else None,
                "price_per_share": round(t["price_per_share"], 4) if t["price_per_share"] else None,
                "total_amount": round(t["total_amount"], 2) if t["total_amount"] else None,
                "currency": t["currency"] or "",
                "fx_rate": round(t["fx_rate"], 4) if t["fx_rate"] else None,
                "asset_class": t["asset_class"] or "stock",
            }
            for t in transactions
        ],
    }

    # Benchmark series
    for ticker, series in analytics.benchmark_series.items():
        from .price_fetcher import BENCHMARKS
        data["benchmark_series"][ticker] = {
            "name": BENCHMARKS.get(ticker, ticker),
            "dates": [str(d) for d in series.index],
            "values": [round(float(v), 2) for v in series.values],
        }

    # Tax data — keyed by year so the client can switch years
    def _ser_tax(t) -> dict:
        d = {
            "year": t.year,
            "total_dividends_eur": round(t.total_dividends_eur, 2),
            "total_fees_eur": round(t.total_fees_eur, 2),
            "realized_sales": [
                {
                    "ticker": s.ticker,
                    "asset_class": s.asset_class,
                    "sell_date": s.sell_date,
                    "quantity": round(s.quantity, 4),
                    "sell_price_eur": round(s.sell_price_eur, 2),
                    "cost_basis_eur": round(s.cost_basis_eur, 2),
                    "gain_eur": round(s.gain_eur, 2),
                    "std_costs_eur": round(s.std_costs_eur, 2),
                    "holding_years": round(s.holding_years, 1),
                    "tax_rate": round(s.tax_rate, 2),
                    "tax_eur": round(s.tax_eur, 2),
                }
                for s in t.realized_sales
            ],
        }
        if t.harvest_candidates:
            # Compute enhanced harvest data with wash-sale and net-benefit info
            try:
                from .harvest import compute_harvest_suggestions
                enhanced = compute_harvest_suggestions(conn, year=t.year, scope="all", country=t.country)
                enhanced_map = {s.ticker: s for s in enhanced.suggestions}
            except Exception:
                enhanced_map = {}

            d["harvest_candidates"] = []
            for c in t.harvest_candidates:
                entry = {
                    "ticker": c.ticker,
                    "asset_class": c.asset_class,
                    "quantity": round(c.quantity, 4),
                    "cost_basis_eur": round(c.cost_basis_eur, 2),
                    "market_value_eur": round(c.market_value_eur, 2),
                    "unrealized_loss_eur": round(c.unrealized_loss_eur, 2),
                    "tax_rate": round(c.tax_rate, 2),
                    "potential_tax_saving_eur": round(c.potential_tax_saving_eur, 2),
                    "avg_holding_years": round(c.avg_holding_years, 1),
                }
                enh = enhanced_map.get(c.ticker)
                if enh:
                    entry["wash_sale_risk"] = enh.wash_sale_risk
                    entry["wash_sale_note"] = enh.wash_sale_note
                    entry["net_benefit_eur"] = enh.net_benefit_eur
                    entry["offsetable_gain_eur"] = enh.offsetable_gain_eur
                d["harvest_candidates"].append(entry)
        return d

    if tax_by_year:
        data["tax_by_year"] = {str(yr): _ser_tax(t) for yr, t in tax_by_year.items()}

    # Per-asset-class daily series (for the scope filter UI)
    data["per_class"] = {}
    data["available_classes"] = available_classes or (list(per_class.keys()) if per_class else [])
    if per_class:
        for ac, ac_analytics in per_class.items():
            ac_daily = ac_analytics.daily_series
            data["per_class"][ac] = {
                "dates": [str(d) for d in ac_daily.index],
                "value_eur": [round(float(v), 2) for v in ac_daily["value_eur"]],
                "invested_eur": [round(float(v), 2) for v in ac_daily["invested_eur"]],
                "dividends_eur": [round(float(v), 2) for v in ac_daily["dividends_eur"]],
                "realized_gain_eur": [round(float(v), 2) for v in ac_daily["realized_gain_eur"]],
                "perf_index": [round(float(v), 2) for v in ac_daily["perf_index"]] if "perf_index" in ac_daily.columns else [],
                "summary": {
                    "portfolio_value_eur": round(ac_analytics.portfolio_value_eur, 2),
                    "total_invested_eur": round(ac_analytics.total_invested_eur, 2),
                    "absolute_gain_eur": round(ac_analytics.absolute_gain_eur, 2),
                    "total_return_pct": round(ac_analytics.total_return_pct, 2),
                    "cagr_pct": round(ac_analytics.cagr_pct, 2) if ac_analytics.cagr_pct else None,
                    "twr_pct": round(ac_analytics.twr_pct, 2) if ac_analytics.twr_pct else None,
                    "max_drawdown_pct": round(ac_analytics.max_drawdown_pct, 2),
                    "max_drawdown_peak_date": ac_analytics.max_drawdown_peak_date,
                    "max_drawdown_trough_date": ac_analytics.max_drawdown_trough_date,
                    "risk_metrics": ac_analytics.risk_metrics,
                },
                "gains": {
                    "realized_eur": round(ac_analytics.total_realized_gain_eur, 2),
                    "unrealized_eur": round(ac_analytics.total_unrealized_gain_eur, 2),
                    "dividends_eur": round(ac_analytics.total_dividends_eur, 2),
                    "fees_eur": round(ac_analytics.total_fees_eur, 2),
                },
                "positions": sorted(
                    [
                        {
                            "ticker": p.ticker,
                            "quantity": round(p.quantity, 4),
                            "cost_basis_eur": round(p.cost_basis_eur, 2),
                            "avg_cost_eur": round(p.cost_basis_eur / p.quantity, 4) if p.quantity else 0,
                            "market_value_eur": round(p.market_value_eur, 2),
                            "unrealized_gain_eur": round(p.unrealized_gain_eur, 2),
                            "unrealized_gain_pct": round(p.unrealized_gain_pct, 2),
                            "weight_pct": round(p.weight_pct, 2),
                            "realized_gain_eur": round(p.realized_gain_eur, 2),
                        }
                        for p in ac_analytics.positions
                    ],
                    key=lambda x: x["market_value_eur"],
                    reverse=True,
                ),
                "closed_positions": sorted(
                    [
                        {
                            "ticker": p.ticker,
                            "total_cost_eur": round(p.total_cost_eur, 2),
                            "total_proceeds_eur": round(p.total_proceeds_eur, 2),
                            "realized_gain_eur": round(p.realized_gain_eur, 2),
                            "realized_gain_pct": round(p.realized_gain_pct, 2),
                        }
                        for p in ac_analytics.closed_positions
                    ],
                    key=lambda x: abs(x["realized_gain_eur"]),
                    reverse=True,
                ),
                "position_lots": {
                    ticker: [
                        {"qty": round(qty, 4), "cost_eur": round(cost, 4), "date": date}
                        for qty, cost, date in lots
                    ]
                    for ticker, lots in ac_analytics.position_lots.items()
                },
            }

    data["real_estate"] = real_estate or {}
    data["fire"] = fire_config  # full config dict or None (replaces old fire_target)
    data["investment_notes"] = investment_notes or []
    data["dividends"] = _query_dividend_data(conn)

    # Dividend tax summary (Doh-Div) per year
    if conn is not None:
        try:
            from .doh_div_generator import build_dividend_entries, compute_dividend_tax_summary
            div_tax_by_year = {}
            div_years = [
                int(r[0]) for r in conn.execute(
                    "SELECT DISTINCT strftime('%Y', date) FROM transactions "
                    "WHERE type LIKE 'DIVIDEND%' AND asset_class = 'stock' ORDER BY 1"
                ).fetchall()
            ]
            for yr in div_years:
                try:
                    entries = build_dividend_entries(conn, yr)
                    if entries:
                        s = compute_dividend_tax_summary(entries, yr)
                        div_tax_by_year[str(yr)] = {
                            "total_gross_eur": s.total_gross_eur,
                            "total_withholding_eur": s.total_withholding_eur,
                            "total_net_received_eur": s.total_net_received_eur,
                            "si_tax_liability": s.si_tax_liability,
                            "total_credit_eur": s.total_credit_eur,
                            "net_tax_owed_si": s.net_tax_owed_si,
                            "total_reclaimable_eur": s.total_reclaimable_eur,
                            "entry_count": len(entries),
                            "by_country": {
                                k: {
                                    "country_name": v["country_name"],
                                    "gross_eur": round(v["gross_eur"], 2),
                                    "withholding_eur": round(v["withholding_eur"], 2),
                                    "credit_eur": round(v["credit_eur"], 2),
                                    "reclaimable_eur": round(v["reclaimable_eur"], 2),
                                    "treaty_rate": v["treaty_rate"],
                                    "count": v["count"],
                                } for k, v in s.by_country.items()
                            },
                        }
                except Exception:
                    pass
            data["dividend_tax"] = div_tax_by_year
        except Exception:
            data["dividend_tax"] = {}

    # Price history and company names for expandable position rows
    pos_tickers = [p["ticker"] for p in data["positions"]]
    data["position_price_history"] = _query_position_price_history(conn, pos_tickers)
    data["company_names"] = _query_company_names(conn, pos_tickers)

    # Currency exposure
    data["currency_exposure"] = _query_currency_exposure(conn, analytics.positions)

    # Sector/industry allocation
    data["sector_allocation"] = _query_sector_allocation(conn, analytics.positions)

    # Geographic allocation
    data["geographic_allocation"] = _query_geographic_allocation(conn, analytics.positions)

    # Concentration risk
    data["concentration_risk"] = _compute_concentration_risk(analytics.positions)

    # Correlation matrix
    data["correlation"] = _compute_correlation_matrix(conn, analytics.positions)

    return data


def generate_html_report(analytics, tax_by_year, transactions: list[dict],
                         per_class: dict | None = None,
                         available_classes: list[str] | None = None,
                         real_estate: dict | None = None,
                         fire_config: dict | None = None,
                         investment_notes: list[dict] | None = None,
                         conn: sqlite3.Connection | None = None,
                         country: str = "SI") -> str:
    """Generate a self-contained HTML report."""
    data = _serialize_report_data(analytics, tax_by_year, transactions, per_class=per_class,
                                  available_classes=available_classes,
                                  real_estate=real_estate, fire_config=fire_config,
                                  investment_notes=investment_notes, conn=conn,
                                  country=country)

    template = _env.get_template("report.html.j2")
    return template.render(
        title="Portfolio Report",
        start_date=html.escape(data["start_date"]),
        end_date=html.escape(data["end_date"]),
        generated_at=html.escape(data["generated_at"]),
        data_json=json.dumps(data, separators=(",", ":")),
    )


