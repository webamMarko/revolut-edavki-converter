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


def query_real_estate(conn: sqlite3.Connection) -> dict:
    """Return real estate properties with valuations and price history."""
    try:
        props = conn.execute("""
            SELECT p.*,
                   dp.close AS estimated_value_eur,
                   dp.date  AS estimated_date
            FROM real_estate_properties p
            LEFT JOIN (
                SELECT ticker, close, date,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
                FROM daily_prices WHERE currency = 'EUR'
            ) dp ON dp.ticker = p.ticker AND dp.rn = 1
            ORDER BY p.purchase_date
        """).fetchall()
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


def _serialize_report_data(analytics, tax_by_year, transactions: list[dict],
                           per_class: dict | None = None,
                           real_estate: dict | None = None,
                           fire_config: dict | None = None,
                           investment_notes: list[dict] | None = None,
                           conn: sqlite3.Connection | None = None) -> dict:
    """Convert analytics/tax results + transactions to JSON-safe dict."""
    daily = analytics.daily_series
    data = {
        "scope": analytics.scope,
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
        return {
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

    if tax_by_year:
        data["tax_by_year"] = {str(yr): _ser_tax(t) for yr, t in tax_by_year.items()}

    # Per-asset-class daily series (for the scope filter UI)
    data["per_class"] = {}
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
            }

    data["real_estate"] = real_estate or {}
    data["fire"] = fire_config  # full config dict or None (replaces old fire_target)
    data["investment_notes"] = investment_notes or []

    # Price history and company names for expandable position rows
    pos_tickers = [p["ticker"] for p in data["positions"]]
    data["position_price_history"] = _query_position_price_history(conn, pos_tickers)
    data["company_names"] = _query_company_names(conn, pos_tickers)

    return data


def generate_html_report(analytics, tax_by_year, transactions: list[dict],
                         per_class: dict | None = None,
                         real_estate: dict | None = None,
                         fire_config: dict | None = None,
                         investment_notes: list[dict] | None = None,
                         conn: sqlite3.Connection | None = None) -> str:
    """Generate a self-contained HTML report."""
    data = _serialize_report_data(analytics, tax_by_year, transactions, per_class=per_class,
                                  real_estate=real_estate, fire_config=fire_config,
                                  investment_notes=investment_notes, conn=conn)

    template = _env.get_template("report.html.j2")
    return template.render(
        title="Portfolio Report",
        start_date=html.escape(data["start_date"]),
        end_date=html.escape(data["end_date"]),
        generated_at=html.escape(data["generated_at"]),
        data_json=json.dumps(data, separators=(",", ":")),
    )


