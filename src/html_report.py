"""HTML report generator for portfolio analytics."""

import html
import json
import sqlite3
from datetime import datetime


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


def query_transactions(conn: sqlite3.Connection, scope: str = "all",
                       year: int | None = None,
                       start_date: datetime | None = None,
                       end_date: datetime | None = None) -> list[dict]:
    """Query transactions from database with scope/date filtering."""
    conditions = []
    params = []

    if scope != "all":
        conditions.append("asset_class = ?")
        params.append(scope)

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


def query_fire_target(conn: sqlite3.Connection) -> float | None:
    """Return the FIRE target in EUR from stored config, or None if not configured."""
    try:
        rows = {r[0]: r[1] for r in conn.execute(
            "SELECT key, value FROM metadata WHERE key LIKE 'fire_%'"
        ).fetchall()}
        if "fire_annual_expenses" not in rows:
            return None
        expenses = float(rows["fire_annual_expenses"])
        income   = float(rows.get("fire_annual_income", 0))
        rate     = float(rows.get("fire_withdrawal_rate", 4.0)) / 100
        if rate <= 0:
            return None
        return round((expenses - income) / rate, 2)
    except Exception:
        return None


def _serialize_report_data(analytics, tax, transactions: list[dict],
                           per_class: dict | None = None,
                           real_estate: dict | None = None,
                           fire_target: float | None = None) -> dict:
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
                    "market_value_eur": round(p.market_value_eur, 2),
                    "unrealized_gain_eur": round(p.unrealized_gain_eur, 2),
                    "unrealized_gain_pct": round(p.unrealized_gain_pct, 2),
                    "weight_pct": round(p.weight_pct, 2),
                }
                for p in analytics.positions
            ],
            key=lambda x: x["market_value_eur"],
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

    # Tax data
    if tax:
        data["tax"] = {
            "year": tax.year,
            "total_realized_gain_eur": round(tax.total_realized_gain_eur, 2),
            "total_realized_tax_eur": round(tax.total_realized_tax_eur, 2),
            "total_dividends_eur": round(tax.total_dividends_eur, 2),
            "total_fees_eur": round(tax.total_fees_eur, 2),
            "total_tax_eur": round(tax.total_tax_eur, 2),
            "realized_sales": [
                {
                    "ticker": s.ticker,
                    "sell_date": s.sell_date,
                    "quantity": round(s.quantity, 4),
                    "sell_price_eur": round(s.sell_price_eur, 2),
                    "cost_basis_eur": round(s.cost_basis_eur, 2),
                    "gain_eur": round(s.gain_eur, 2),
                    "holding_years": round(s.holding_years, 1),
                    "tax_rate": round(s.tax_rate, 2),
                    "tax_eur": round(s.tax_eur, 2),
                }
                for s in tax.realized_sales
            ],
        }

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
                            "market_value_eur": round(p.market_value_eur, 2),
                            "unrealized_gain_eur": round(p.unrealized_gain_eur, 2),
                            "unrealized_gain_pct": round(p.unrealized_gain_pct, 2),
                            "weight_pct": round(p.weight_pct, 2),
                        }
                        for p in ac_analytics.positions
                    ],
                    key=lambda x: x["market_value_eur"],
                    reverse=True,
                ),
            }

    data["real_estate"] = real_estate or {}
    data["fire_target"] = fire_target  # float or None
    return data


def generate_html_report(analytics, tax, transactions: list[dict],
                         per_class: dict | None = None,
                         real_estate: dict | None = None,
                         fire_target: float | None = None) -> str:
    """Generate a self-contained HTML report."""
    data = _serialize_report_data(analytics, tax, transactions, per_class=per_class,
                                  real_estate=real_estate, fire_target=fire_target)
    data_json = json.dumps(data, separators=(",", ":"))

    scope_label = {"stock": "Stocks", "cfd": "CFD", "crypto": "Crypto", "savings": "Savings", "realestate": "Real Estate", "all": "All Assets"}.get(data["scope"], "All")
    title = f"Portfolio Report — {scope_label}"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2"></script>
<style>
{_CSS}
</style>
</head>
<body>

<header>
  <h1>{html.escape(title)}</h1>
  <p class="subtitle">{html.escape(data['start_date'])} to {html.escape(data['end_date'])} &middot; Generated {html.escape(data['generated_at'])}</p>
</header>

<div id="assetFilter" class="asset-filter" style="display:none">
  <span class="filter-label">Asset Classes:</span>
  <div id="assetToggles" class="toggles"></div>
</div>

<div id="selectionBanner" class="selection-banner" style="display:none">
  <span id="selectionLabel"></span>
  <button onclick="resetZoom()">Reset Zoom</button>
</div>

<main>
  <section id="summary" class="card-grid"></section>

  <section class="chart-section">
    <div class="chart-header">
      <h2>Portfolio Value</h2>
      <div class="range-bar" id="rangeBar">
        <button class="range-btn" data-days="7">7D</button>
        <button class="range-btn" data-days="30">30D</button>
        <button class="range-btn" data-ytd="1">YTD</button>
        <button class="range-btn" data-days="365">1Y</button>
        <button class="range-btn" data-days="1095">3Y</button>
        <button class="range-btn" data-days="1825">5Y</button>
        <button class="range-btn active" data-days="-1">All</button>
      </div>
      <span class="chart-hint">Drag to select a period</span>
    </div>
    <div class="chart-wrap"><canvas id="portfolioChart"></canvas></div>
  </section>

  <section class="chart-section" id="benchmarkSection" style="display:none">
    <h2 id="benchmarkSectionTitle">Performance</h2>
    <div class="chart-wrap"><canvas id="benchmarkChart"></canvas></div>
  </section>

  <section class="chart-section">
    <h2>Monthly Performance</h2>
    <div id="heatmap"></div>
  </section>

  <section class="two-col">
    <div class="card">
      <h2>Gains Breakdown</h2>
      <table id="gainsTable" class="data-table"></table>
    </div>
    <div class="card" id="benchmarkTableCard" style="display:none">
      <h2>Benchmark Comparison</h2>
      <table id="benchmarkTable" class="data-table"></table>
    </div>
  </section>

  <section class="card" id="positionsSection" style="display:none">
    <h2>Current Positions</h2>
    <div class="table-scroll">
      <table id="positionsTable" class="data-table sortable"></table>
    </div>
  </section>

  <section class="card" id="realEstateSection">
    <h2>Real Estate</h2>
    <div id="reCards" class="card-grid small" style="margin-bottom:1rem"></div>
    <div class="chart-wrap" style="height:260px;margin-bottom:1rem"><canvas id="reChart"></canvas></div>
    <div class="table-scroll">
      <table id="reTable" class="data-table"></table>
    </div>
  </section>

  <section class="card" id="taxSection" style="display:none">
    <h2>Tax Summary</h2>
    <div id="taxCards" class="card-grid small"></div>
    <div class="table-scroll">
      <table id="taxTable" class="data-table sortable"></table>
    </div>
  </section>

  <section class="card">
    <h2>Transaction History</h2>
    <div class="toolbar">
      <input type="text" id="txFilter" placeholder="Filter by ticker or type…">
      <span id="txCount"></span>
    </div>
    <div class="table-scroll">
      <table id="txTable" class="data-table sortable"></table>
    </div>
    <div id="txPagination" class="pagination"></div>
  </section>
</main>

<script>const D={data_json};</script>
<script>
{_JS}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
_CSS = """\
:root {
  --bg: #f5f6fa; --card: #fff; --text: #1a1a2e; --muted: #6b7280;
  --border: #e5e7eb; --blue: #4285f4; --green: #16a34a; --red: #dc2626;
  --hover: #f9fafb;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f172a; --card: #1e293b; --text: #e2e8f0; --muted: #94a3b8;
    --border: #334155; --hover: #293548;
  }
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.5;
}
header {
  background: var(--card); border-bottom: 1px solid var(--border);
  padding: 1.5rem 2rem; text-align: center;
}
header h1 { font-size: 1.5rem; font-weight: 700; }
.subtitle { color: var(--muted); font-size: 0.875rem; margin-top: 0.25rem; }
main { max-width: 1240px; margin: 0 auto; padding: 1.5rem 1rem; display: flex; flex-direction: column; gap: 1.5rem; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 1.25rem; }
.card h2 { font-size: 1.1rem; margin-bottom: 0.75rem; }
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 0.75rem; }
.card-grid.small { grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); }
.metric-card {
  background: var(--card); border: 1px solid var(--border); border-radius: 10px;
  padding: 1rem 1.25rem; text-align: center;
}
.metric-card .label { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
.metric-card .value { font-size: 1.35rem; font-weight: 700; margin-top: 0.25rem; }
.metric-card .sub { font-size: 0.7rem; color: var(--muted); margin-top: 0.15rem; }
.chart-section { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 1.25rem; }
.chart-section h2 { font-size: 1.1rem; margin-bottom: 0.5rem; }
.chart-wrap { position: relative; height: 340px; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
@media (max-width: 768px) { .two-col { grid-template-columns: 1fr; } }
.table-scroll { overflow-x: auto; }
.data-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.data-table th, .data-table td { padding: 0.5rem 0.75rem; text-align: right; border-bottom: 1px solid var(--border); white-space: nowrap; }
.data-table th:first-child, .data-table td:first-child { text-align: left; }
.data-table th { font-weight: 600; color: var(--muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; position: sticky; top: 0; background: var(--card); }
.data-table tbody tr:hover { background: var(--hover); }
.sortable th { cursor: pointer; user-select: none; }
.sortable th:hover { color: var(--text); }
.sortable th .arrow { font-size: 0.65rem; margin-left: 0.25rem; }
.pos { color: var(--green); } .neg { color: var(--red); }
.toolbar { display: flex; align-items: center; gap: 1rem; margin-bottom: 0.75rem; }
#txFilter {
  padding: 0.4rem 0.75rem; border: 1px solid var(--border); border-radius: 6px;
  background: var(--bg); color: var(--text); font-size: 0.85rem; width: 260px;
}
#txCount { font-size: 0.8rem; color: var(--muted); }
.pagination { display: flex; align-items: center; justify-content: center; gap: 0.5rem; margin-top: 0.75rem; font-size: 0.85rem; }
.pagination button {
  padding: 0.3rem 0.75rem; border: 1px solid var(--border); border-radius: 6px;
  background: var(--card); color: var(--text); cursor: pointer; font-size: 0.8rem;
}
.pagination button:disabled { opacity: 0.4; cursor: default; }
.pagination button:not(:disabled):hover { background: var(--hover); }
.tag { display: inline-block; padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.75rem; font-weight: 500; }
.tag-stock { background: #dbeafe; color: #1d4ed8; }
.tag-cfd { background: #fef3c7; color: #92400e; }
.selection-banner {
  background: var(--blue); color: #fff; text-align: center; padding: 0.5rem 1rem;
  display: flex; align-items: center; justify-content: center; gap: 1rem; font-size: 0.9rem; font-weight: 500;
}
.selection-banner button {
  background: rgba(255,255,255,0.2); color: #fff; border: 1px solid rgba(255,255,255,0.4);
  border-radius: 6px; padding: 0.25rem 0.75rem; cursor: pointer; font-size: 0.8rem;
}
.selection-banner button:hover { background: rgba(255,255,255,0.35); }
.chart-header { display: flex; align-items: baseline; gap: 0.75rem; margin-bottom: 0.5rem; }
.chart-header h2 { margin-bottom: 0; }
.chart-hint { font-size: 0.75rem; color: var(--muted); }
.asset-filter {
  background: var(--card); border-bottom: 1px solid var(--border);
  padding: 0.6rem 2rem; display: flex; align-items: center; gap: 1rem; justify-content: center;
}
.filter-label { font-size: 0.8rem; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
.toggles { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.toggle-btn {
  padding: 0.3rem 0.85rem; border-radius: 20px; font-size: 0.8rem; font-weight: 600;
  cursor: pointer; border: 2px solid transparent; transition: all 0.15s ease;
  user-select: none;
}
.toggle-btn.active { opacity: 1; }
.toggle-btn:not(.active) { opacity: 0.35; filter: grayscale(0.5); }
.toggle-btn:hover { opacity: 0.85; }
.toggle-stock { background: #dbeafe; color: #1d4ed8; border-color: #93bbfd; }
.toggle-cfd { background: #fef3c7; color: #92400e; border-color: #fcd34d; }
.toggle-crypto { background: #ede9fe; color: #6d28d9; border-color: #c4b5fd; }
.toggle-savings { background: #d1fae5; color: #065f46; border-color: #6ee7b7; }
@media (prefers-color-scheme: dark) {
  .tag-stock { background: #1e3a5f; color: #93c5fd; } .tag-cfd { background: #451a03; color: #fcd34d; }
  .tag-crypto { background: #2e1065; color: #c4b5fd; } .tag-savings { background: #064e3b; color: #6ee7b7; }
  .toggle-stock { background: #1e3a5f; color: #93c5fd; border-color: #3b82f6; }
  .toggle-cfd { background: #451a03; color: #fcd34d; border-color: #f59e0b; }
  .toggle-crypto { background: #2e1065; color: #c4b5fd; border-color: #8b5cf6; }
  .toggle-savings { background: #064e3b; color: #6ee7b7; border-color: #10b981; }
}
.chart-header { display:flex; align-items:center; gap:0.75rem; flex-wrap:wrap; margin-bottom:0.5rem; }
.chart-header h2 { margin-bottom:0; }
.range-bar { display:flex; gap:0.25rem; flex-wrap:wrap; margin-left:auto; }
.range-btn {
  padding:0.2rem 0.6rem; border-radius:4px; font-size:0.75rem; font-weight:600;
  cursor:pointer; border:1px solid var(--border); background:transparent; color:var(--muted);
  transition:all 0.15s;
}
.range-btn:hover { background:var(--hover); color:var(--text); }
.range-btn.active { background:var(--blue); color:#fff; border-color:var(--blue); }
.heatmap-wrap { overflow-x:auto; }
.heatmap-table { border-collapse:collapse; font-size:0.75rem; }
.heatmap-table th, .heatmap-table td { padding:0.28rem 0.45rem; text-align:center; white-space:nowrap; }
.heatmap-table thead th { color:var(--muted); font-weight:600; font-size:0.7rem; text-transform:uppercase; }
.heatmap-year-label { font-weight:700; text-align:left !important; padding-right:0.75rem !important; color:var(--text); }
.heatmap-cell { border-radius:3px; min-width:52px; transition:filter 0.1s; }
.heatmap-cell:hover { filter:brightness(1.15); cursor:default; }
.heatmap-empty { min-width:52px; }
.heatmap-year-col { border-left:2px solid var(--border); }
.heatmap-year-cell { border-left:2px solid var(--border); }
.tag-realestate { background: #fce7f3; color: #9d174d; }
@media (prefers-color-scheme: dark) {
  .tag-realestate { background: #4a0026; color: #f9a8d4; }
  .toggle-realestate { background: #4a0026; color: #f9a8d4; border-color: #db2777; }
}
.toggle-realestate { background: #fce7f3; color: #9d174d; border-color: #f472b6; }
"""


# ---------------------------------------------------------------------------
# JavaScript
# ---------------------------------------------------------------------------
_JS = """\
(function(){
const fmt = (v,d=2) => v==null?'—':v.toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
const fmtEur = v => v==null?'—':fmt(v)+' EUR';
const cls = v => v==null?'':v>=0?'pos':'neg';
const pct = v => v==null?'—':fmt(v)+'%';
const sign = v => v==null?'—':(v>=0?'+':'')+fmt(v);

// --- Asset class filter state ---
const perClass = D.per_class || {};
const classKeys = Object.keys(perClass);
const hasFilter = classKeys.length > 1;
// These classes start inactive by default (different time horizon / skews the main chart)
const defaultInactive = new Set(['realestate', 'savings']);
let activeClasses = new Set(classKeys.filter(k => !defaultInactive.has(k)));
const classLabels = {stock:'Stocks',cfd:'CFD',crypto:'Crypto',savings:'Savings',realestate:'Real Estate'};

// Build the active daily series by summing selected asset classes
// Each per_class entry has dates/value_eur/invested_eur/dividends_eur/realized_gain_eur
// We need to align them onto a common date grid.

// Keys included in the pre-computed "all" daily series (everything except realestate)
const allSeriesKeys = new Set(classKeys.filter(k => k !== 'realestate'));

function buildCombinedSeries() {
  // Use pre-computed "all" series only when ALL non-realestate classes are active
  // (i.e. savings is on, realestate is off)
  const nonReActive = [...activeClasses].filter(k => k !== 'realestate');
  if (!hasFilter || (nonReActive.length === allSeriesKeys.size && !activeClasses.has('realestate'))) {
    // Matches the pre-computed "all" series exactly
    return {
      dates: D.daily_series.dates,
      value_eur: D.daily_series.value_eur.slice(),
      invested_eur: D.daily_series.invested_eur.slice(),
      dividends_eur: D.daily_series.dividends_eur.slice(),
      realized_gain_eur: D.daily_series.realized_gain_eur.slice(),
      perf_index: (D.daily_series.perf_index || []).slice(),
    };
  }
  if (activeClasses.size === 0) {
    return {dates:[], value_eur:[], invested_eur:[], dividends_eur:[], realized_gain_eur:[], perf_index:[]};
  }
  if (activeClasses.size === 1) {
    const ac = [...activeClasses][0];
    const s = perClass[ac];
    return {
      dates: s.dates.slice(),
      value_eur: s.value_eur.slice(),
      invested_eur: s.invested_eur.slice(),
      dividends_eur: s.dividends_eur.slice(),
      realized_gain_eur: s.realized_gain_eur.slice(),
      perf_index: (s.perf_index || []).slice(),
    };
  }
  // Multiple but not all: collect all unique dates, then sum
  const dateSet = new Set();
  activeClasses.forEach(ac => { perClass[ac].dates.forEach(d => dateSet.add(d)); });
  const dates = [...dateSet].sort();
  // For each class, build a lookup: date -> index
  const lookups = {};
  activeClasses.forEach(ac => {
    const m = new Map();
    perClass[ac].dates.forEach((d,i) => m.set(d, i));
    lookups[ac] = m;
  });
  const N2 = dates.length;
  const value_eur = new Array(N2).fill(0);
  const invested_eur = new Array(N2).fill(0);
  const dividends_eur = new Array(N2).fill(0);
  const realized_gain_eur = new Array(N2).fill(0);
  for (let i = 0; i < N2; i++) {
    const d = dates[i];
    activeClasses.forEach(ac => {
      const s = perClass[ac];
      const m = lookups[ac];
      let idx = m.get(d);
      if (idx == null) {
        // Forward-fill: find last date <= d
        idx = -1;
        for (let j = s.dates.length - 1; j >= 0; j--) {
          if (s.dates[j] <= d) { idx = j; break; }
        }
      }
      if (idx >= 0) {
        value_eur[i] += s.value_eur[idx];
        invested_eur[i] += s.invested_eur[idx];
        dividends_eur[i] += s.dividends_eur[idx];
        realized_gain_eur[i] += s.realized_gain_eur[idx];
      }
    });
  }
  // Recompute perf_index from combined value series using chain-linking
  const perf_index = computePerfIndex(value_eur, invested_eur);
  return {dates, value_eur, invested_eur, dividends_eur, realized_gain_eur, perf_index};
}

function computePerfIndex(values, invested) {
  // Chain-linked performance index: daily returns exclude cash flow effects.
  // Approximation: daily cash flow ≈ change in invested.
  const n = values.length;
  const pi = new Array(n);
  let idx = 100.0;
  for (let i = 0; i < n; i++) {
    if (i === 0) { pi[i] = values[0] > 0 ? 100.0 : 0; continue; }
    const prev = values[i-1];
    if (prev > 1e-6) {
      const cashflow = invested[i] - invested[i-1];  // positive = inflow
      const ret = (values[i] - cashflow) / prev - 1;
      idx *= (1 + ret);
    }
    pi[i] = idx;
  }
  return pi;
}

function isDefaultSelection() {
  // True when selection matches the pre-computed "all" series (financial classes only, no realestate)
  const financialActive = [...activeClasses].filter(k => k !== 'realestate');
  return !hasFilter || (financialActive.length === allSeriesKeys.size && !activeClasses.has('realestate'));
}

function getActiveSummary() {
  if (isDefaultSelection()) return D.summary;
  if (activeClasses.size === 0) return {portfolio_value_eur:0,total_invested_eur:0,absolute_gain_eur:0,total_return_pct:0,cagr_pct:null,twr_pct:null,max_drawdown_pct:0,max_drawdown_peak_date:'',max_drawdown_trough_date:''};
  if (activeClasses.size === 1) return perClass[[...activeClasses][0]].summary;
  // Sum summaries for selected classes
  let pv=0,ti=0,ag=0; const summaries = [];
  activeClasses.forEach(ac => {
    const s = perClass[ac].summary;
    pv += s.portfolio_value_eur; ti += s.total_invested_eur; ag += s.absolute_gain_eur;
    summaries.push(s);
  });
  const ret = ti > 0 ? (ag / ti * 100) : 0;
  // Recompute max drawdown from combined series
  const cs = buildCombinedSeries();
  let peak = cs.value_eur[0]||0, maxDD = 0, peakDate = cs.dates[0]||'', troughDate = cs.dates[0]||'', curPeakDate = cs.dates[0]||'';
  for (let i = 0; i < cs.dates.length; i++) {
    const v = cs.value_eur[i];
    if (v > peak) { peak = v; curPeakDate = cs.dates[i]; }
    const dd = peak > 0 ? (v - peak) / peak * 100 : 0;
    if (dd < maxDD) { maxDD = dd; peakDate = curPeakDate; troughDate = cs.dates[i]; }
  }
  return {portfolio_value_eur:pv,total_invested_eur:ti,absolute_gain_eur:ag,total_return_pct:ret,cagr_pct:null,twr_pct:null,max_drawdown_pct:maxDD,max_drawdown_peak_date:peakDate,max_drawdown_trough_date:troughDate};
}

function getActiveGains() {
  if (isDefaultSelection()) return D.gains;
  if (activeClasses.size === 0) return {realized_eur:0,unrealized_eur:0,dividends_eur:0,fees_eur:0};
  if (activeClasses.size === 1) return perClass[[...activeClasses][0]].gains;
  let r=0,u=0,d=0,f=0;
  activeClasses.forEach(ac => { const g=perClass[ac].gains; r+=g.realized_eur; u+=g.unrealized_eur; d+=g.dividends_eur; f+=g.fees_eur; });
  return {realized_eur:r,unrealized_eur:u,dividends_eur:d,fees_eur:f};
}

function getActivePositions() {
  if (isDefaultSelection()) return D.positions;
  let all = [];
  activeClasses.forEach(ac => { all = all.concat(perClass[ac].positions); });
  // Recalculate weights
  const totalMV = all.reduce((a,p)=>a+p.market_value_eur,0) || 1;
  return all.map(p=>({...p, weight_pct: p.market_value_eur / totalMV * 100})).sort((a,b)=>b.market_value_eur-a.market_value_eur);
}

// --- Active series (recalculated on filter change) ---
let ds = buildCombinedSeries();
let allDates = ds.dates;
let N = allDates.length;

// --- Current selection state ---
let selStart = 0, selEnd = N - 1;
let isZoomed = false;

// --- Asset filter UI ---
if (hasFilter) {
  const filterEl = document.getElementById('assetFilter');
  filterEl.style.display = '';
  const togglesEl = document.getElementById('assetToggles');
  classKeys.forEach(ac => {
    const btn = document.createElement('div');
    const isActive = activeClasses.has(ac);
    btn.className = 'toggle-btn toggle-' + ac + (isActive ? ' active' : '');
    btn.textContent = classLabels[ac] || ac;
    btn.dataset.ac = ac;
    btn.addEventListener('click', function() {
      if (activeClasses.has(ac)) {
        if (activeClasses.size <= 1) return; // keep at least one
        activeClasses.delete(ac);
        btn.classList.remove('active');
      } else {
        activeClasses.add(ac);
        btn.classList.add('active');
      }
      onFilterChange();
    });
    togglesEl.appendChild(btn);
  });
}

function onFilterChange() {
  ds = buildCombinedSeries();
  allDates = ds.dates;
  N = allDates.length;
  selStart = 0; selEnd = N - 1; isZoomed = false;
  rebuildCharts();
  updateAll();
  buildHeatmap();
  document.querySelectorAll('.range-btn').forEach(function(b){ b.classList.toggle('active', b.dataset.days==='-1' && !b.dataset.ytd); });
}

// --- Zoom plugin config (shared) ---
const zoomOpts = {
  zoom: {
    drag: { enabled: true, backgroundColor: 'rgba(66,133,244,0.15)', borderColor: '#4285f4', borderWidth: 1 },
    mode: 'x',
    onZoomComplete: function(ctx) {
      const scale = ctx.chart.scales.x;
      const minMs = scale.min, maxMs = scale.max;
      let si = 0, ei = N - 1;
      for (let i = 0; i < N; i++) { if (new Date(allDates[i]).getTime() >= minMs) { si = i; break; } }
      for (let i = N - 1; i >= 0; i--) { if (new Date(allDates[i]).getTime() <= maxMs) { ei = i; break; } }
      if (si > ei) { si = 0; ei = N - 1; }
      selStart = si; selEnd = ei; isZoomed = true;
      syncChartZoom(ctx.chart);
      updateAll();
    }
  }
};

// --- Charts ---
let portfolioChart, benchmarkChart;

function buildPortfolioChart() {
  const ctx1 = document.getElementById('portfolioChart').getContext('2d');
  const chartDatasets = [
    {label:'Portfolio Value', data:ds.value_eur, borderColor:'#4285f4', backgroundColor:'rgba(66,133,244,0.08)', fill:true, tension:0.15, pointRadius:0, borderWidth:2},
    {label:'Cash Invested', data:ds.invested_eur, borderColor:'#9e9e9e', borderDash:[5,5], fill:false, tension:0.15, pointRadius:0, borderWidth:1.5},
  ];
  if (D.fire_target != null) {
    chartDatasets.push({
      label: 'FIRE Target',
      data: allDates.map(() => D.fire_target),
      borderColor: '#22c55e',
      borderDash: [6, 4],
      fill: false,
      tension: 0,
      pointRadius: 0,
      borderWidth: 2,
      order: 0,
    });
  }
  return new Chart(ctx1, {
    type:'line',
    data:{ labels: allDates, datasets: chartDatasets },
    options:{
      responsive:true, maintainAspectRatio:false,
      interaction:{mode:'index',intersect:false},
      scales:{
        x:{type:'time',time:{unit:'month',tooltipFormat:'yyyy-MM-dd'},grid:{display:false}},
        y:{title:{display:true,text:'EUR'},ticks:{callback:v=>v.toLocaleString()}}
      },
      plugins:{tooltip:{callbacks:{label:c=>c.dataset.label+': '+fmt(c.parsed.y)+' EUR'}}, zoom:zoomOpts}
    }
  });
}

function buildBenchmarkChart() {
  const bKeys = Object.keys(D.benchmark_series);
  document.getElementById('benchmarkSection').style.display='';
  if(bKeys.length>0) {
    document.getElementById('benchmarkTableCard').style.display='';
    document.getElementById('benchmarkSectionTitle').textContent='Performance vs Benchmarks';
  }
  // Use chain-linked performance index: excludes the effect of deposits/withdrawals,
  // showing pure investment performance comparable to benchmark indexes.
  const rebased = (ds.perf_index && ds.perf_index.length > 0)
    ? ds.perf_index.map(v => v > 0 ? v : null)
    : ds.value_eur.map(() => null);
  const bds=[{label:'Portfolio',data:rebased.map((v,i)=>({x:allDates[i],y:v})),borderColor:'#4285f4',borderWidth:2,pointRadius:0,tension:0.15}];
  const bColors={'S&P 500':'#ea4335','NASDAQ':'#34a853','Dow Jones':'#fbbc04','FTSE 100':'#7c3aed'};
  bKeys.forEach(tk=>{
    const b=D.benchmark_series[tk];
    bds.push({label:b.name,data:b.dates.map((d,i)=>({x:d,y:b.values[i]})),borderColor:bColors[b.name]||'#999',borderWidth:1.5,pointRadius:0,tension:0.15});
  });
  const ctx2=document.getElementById('benchmarkChart').getContext('2d');
  return new Chart(ctx2,{
    type:'line',data:{datasets:bds},
    options:{
      responsive:true,maintainAspectRatio:false,
      interaction:{mode:'index',intersect:false},
      scales:{
        x:{type:'time',time:{unit:'month',tooltipFormat:'yyyy-MM-dd'},grid:{display:false}},
        y:{title:{display:true,text:'Value per 100 EUR invested'}}
      },
      plugins:{tooltip:{callbacks:{label:c=>c.dataset.label+': '+fmt(c.parsed.y)}}, zoom:zoomOpts}
    }
  });
}

function rebuildCharts() {
  if (portfolioChart) portfolioChart.destroy();
  if (benchmarkChart) benchmarkChart.destroy();
  benchmarkChart = null;
  portfolioChart = buildPortfolioChart();
  benchmarkChart = buildBenchmarkChart();
}

portfolioChart = buildPortfolioChart();
benchmarkChart = buildBenchmarkChart();

const bKeys = Object.keys(D.benchmark_series);

// --- Sync zoom between charts ---
function syncChartZoom(sourceChart) {
  const target = sourceChart === portfolioChart ? benchmarkChart : portfolioChart;
  if (!target) return;
  const scale = sourceChart.scales.x;
  target.options.scales.x.min = scale.min;
  target.options.scales.x.max = scale.max;
  target.update('none');
}

// --- Reset zoom ---
function clearScaleLimits(chart) {
  delete chart.options.scales.x.min;
  delete chart.options.scales.x.max;
  chart.resetZoom();
  chart.update();
}
window.resetZoom = function() {
  selStart = 0; selEnd = N - 1; isZoomed = false;
  clearScaleLimits(portfolioChart);
  if (benchmarkChart) clearScaleLimits(benchmarkChart);
  updateAll();
};

// --- Compute period metrics ---
function computePeriodMetrics(si, ei) {
  const startVal = ds.value_eur[si];
  const endVal = ds.value_eur[ei];
  const startInv = ds.invested_eur[si];
  const endInv = ds.invested_eur[ei];
  const change = endVal - startVal;
  const returnPct = startVal > 0 ? (endVal / startVal - 1) * 100 : 0;
  const periodRealized = ds.realized_gain_eur[ei] - (si > 0 ? ds.realized_gain_eur[si - 1] : 0);
  const periodDividends = ds.dividends_eur[ei] - (si > 0 ? ds.dividends_eur[si - 1] : 0);

  let peak = ds.value_eur[si], maxDD = 0, peakDate = allDates[si], troughDate = allDates[si];
  let curPeakDate = allDates[si];
  for (let i = si; i <= ei; i++) {
    const v = ds.value_eur[i];
    if (v > peak) { peak = v; curPeakDate = allDates[i]; }
    const dd = peak > 0 ? (v - peak) / peak * 100 : 0;
    if (dd < maxDD) { maxDD = dd; peakDate = curPeakDate; troughDate = allDates[i]; }
  }
  const days = (new Date(allDates[ei]) - new Date(allDates[si])) / 86400000;
  const years = days / 365.25;
  let cagr = null;
  if (years >= 0.1 && startVal > 0) {
    cagr = (Math.pow(endVal / startVal, 1 / years) - 1) * 100;
  }
  return {
    startVal, endVal, startInv, endInv, change, returnPct,
    periodRealized, periodDividends, maxDD, peakDate, troughDate, cagr,
    startDate: allDates[si], endDate: allDates[ei], days
  };
}

// --- Update all sections ---
function updateAll() {
  const banner = document.getElementById('selectionBanner');
  const hint = document.querySelector('.chart-hint');
  if (isZoomed) {
    banner.style.display = '';
    document.getElementById('selectionLabel').textContent =
      'Selected period: ' + allDates[selStart] + ' to ' + allDates[selEnd];
    if (hint) hint.textContent = 'Drag to refine, or reset';
  } else {
    banner.style.display = 'none';
    if (hint) hint.textContent = 'Drag to select a period';
  }
  updateSummary();
  updateGains();
  updatePositions();
  updateBenchmarkTable();
  updateTransactions();
  updateTaxTable();
}

// --- Summary cards ---
function updateSummary() {
  const el = document.getElementById('summary');
  if (isZoomed) {
    const m = computePeriodMetrics(selStart, selEnd);
    const cards = [
      ['Start Value', fmtEur(m.startVal), '', allDates[selStart]],
      ['End Value', fmtEur(m.endVal), '', allDates[selEnd]],
      ['Period Change', sign(m.change)+' EUR', cls(m.change)],
      ['Period Return', sign(m.returnPct)+'%', cls(m.returnPct)],
      ['CAGR', m.cagr!=null?sign(m.cagr)+'%':'—', cls(m.cagr)],
      ['Max Drawdown', pct(m.maxDD), 'neg', m.peakDate+' → '+m.troughDate],
    ];
    el.innerHTML = cards.map(([l,v,c,sub])=>
      `<div class="metric-card"><div class="label">${l}</div><div class="value ${c||''}">${v}</div>${sub?`<div class="sub">${sub}</div>`:''}</div>`
    ).join('');
  } else {
    const s = getActiveSummary();
    const cards = [
      ['Portfolio Value', fmtEur(s.portfolio_value_eur)],
      ['Total Invested', fmtEur(s.total_invested_eur)],
      ['Absolute Gain', sign(s.absolute_gain_eur)+' EUR', cls(s.absolute_gain_eur)],
      ['Total Return', sign(s.total_return_pct)+'%', cls(s.total_return_pct)],
      ['CAGR', s.cagr_pct!=null?sign(s.cagr_pct)+'%':'—', cls(s.cagr_pct)],
      ['TWR', s.twr_pct!=null?sign(s.twr_pct)+'%':'—', cls(s.twr_pct)],
      ['Max Drawdown', pct(s.max_drawdown_pct), 'neg', s.max_drawdown_peak_date+' → '+s.max_drawdown_trough_date],
    ];
    if (D.fire_target != null) {
      const progress = s.portfolio_value_eur / D.fire_target * 100;
      const remaining = D.fire_target - s.portfolio_value_eur;
      cards.push(['FIRE Progress', fmt(progress, 1)+'%', progress >= 100 ? 'pos' : '',
                  (remaining > 0 ? '−'+fmtEur(remaining)+' to go' : '🎉 Achieved!')]);
    }
    el.innerHTML = cards.map(([l,v,c,sub])=>
      `<div class="metric-card"><div class="label">${l}</div><div class="value ${c||''}">${v}</div>${sub?`<div class="sub">${sub}</div>`:''}</div>`
    ).join('');
  }
}

// --- Gains breakdown ---
function updateGains() {
  const gt = document.getElementById('gainsTable');
  if (isZoomed) {
    const m = computePeriodMetrics(selStart, selEnd);
    const unrealized = m.endVal - m.endInv - ds.realized_gain_eur[selEnd];
    gt.innerHTML='<tbody>'+[
      ['Period Realized Gains', m.periodRealized],
      ['Unrealized (at end)', unrealized],
      ['Period Dividends', m.periodDividends],
    ].map(([l,v])=>`<tr><td>${l}</td><td class="${cls(v)}">${sign(v)} EUR</td></tr>`).join('')+'</tbody>';
  } else {
    const g = getActiveGains();
    gt.innerHTML='<tbody>'+[
      ['Realized Gains',g.realized_eur],['Unrealized Gains',g.unrealized_eur],
      ['Dividends',g.dividends_eur],['Fees',g.fees_eur],
    ].map(([l,v])=>`<tr><td>${l}</td><td class="${cls(v)}">${sign(v)} EUR</td></tr>`).join('')+'</tbody>';
  }
}

// --- Positions table ---
function updatePositions() {
  const positions = getActivePositions();
  const section = document.getElementById('positionsSection');
  if (positions.length === 0) { section.style.display = 'none'; return; }
  section.style.display = '';
  const pt = document.getElementById('positionsTable');
  pt.innerHTML='<thead><tr><th>Ticker</th><th>Qty</th><th>Cost Basis</th><th>Market Value</th><th>Unrealized</th><th>Return %</th><th>Weight</th></tr></thead><tbody>'+
    positions.map(p=>`<tr><td><strong>${p.ticker}</strong></td><td>${fmt(p.quantity,4)}</td><td>${fmtEur(p.cost_basis_eur)}</td><td>${fmtEur(p.market_value_eur)}</td><td class="${cls(p.unrealized_gain_eur)}">${sign(p.unrealized_gain_eur)} EUR</td><td class="${cls(p.unrealized_gain_pct)}">${sign(p.unrealized_gain_pct)}%</td><td>${fmt(p.weight_pct,1)}%</td></tr>`).join('')+'</tbody>';
  makeSortable(pt);
}

// --- Benchmark table ---
function updateBenchmarkTable() {
  if (bKeys.length === 0) return;
  const bt = document.getElementById('benchmarkTable');
  if (isZoomed) {
    const startDate = new Date(allDates[selStart]);
    const endDate = new Date(allDates[selEnd]);
    const startVal = ds.value_eur[selStart], endVal = ds.value_eur[selEnd];
    const portfolioRet = startVal > 0 ? (endVal / startVal - 1) * 100 : 0;
    const rows = [];
    bKeys.forEach(tk => {
      const b = D.benchmark_series[tk];
      let bsi = 0, bei = b.dates.length - 1;
      for (let i = 0; i < b.dates.length; i++) { if (new Date(b.dates[i]) >= startDate) { bsi = i; break; } }
      for (let i = b.dates.length - 1; i >= 0; i--) { if (new Date(b.dates[i]) <= endDate) { bei = i; break; } }
      const bStart = b.values[bsi], bEnd = b.values[bei];
      const benchRet = bStart > 0 ? (bEnd / bStart - 1) * 100 : 0;
      const alpha = portfolioRet - benchRet;
      rows.push({name: b.name, benchRet, portfolioRet, alpha});
    });
    bt.innerHTML='<thead><tr><th>Benchmark</th><th>Return</th><th>Portfolio</th><th>Alpha</th></tr></thead><tbody>'+
      rows.map(r=>`<tr><td>${r.name}</td><td>${sign(r.benchRet)}%</td><td>${sign(r.portfolioRet)}%</td><td class="${cls(r.alpha)}">${sign(r.alpha)}%</td></tr>`).join('')+'</tbody>';
  } else {
    bt.innerHTML='<thead><tr><th>Benchmark</th><th>Return</th><th>Portfolio</th><th>Alpha</th></tr></thead><tbody>'+
      D.benchmarks.map(b=>`<tr><td>${b.name}</td><td>${pct(b.return_pct)}</td><td>${pct(b.portfolio_return_pct)}</td><td class="${cls(b.alpha_pct)}">${sign(b.alpha_pct)}%</td></tr>`).join('')+'</tbody>';
  }
}

// --- Tax section ---
function updateTaxTable() {
  if(!D.tax) return;
  document.getElementById('taxSection').style.display='';
  const t=D.tax;
  const sales = isZoomed
    ? t.realized_sales.filter(s => s.sell_date >= allDates[selStart] && s.sell_date <= allDates[selEnd])
    : t.realized_sales;
  const periodGain = sales.reduce((a,s) => a + s.gain_eur, 0);
  const periodTax = sales.reduce((a,s) => a + s.tax_eur, 0);

  document.getElementById('taxCards').innerHTML=[
    ['Tax Year', t.year, ''],
    ['Realized Gain', sign(isZoomed ? periodGain : t.total_realized_gain_eur)+' EUR', cls(isZoomed ? periodGain : t.total_realized_gain_eur)],
    ['Realized Tax', fmtEur(isZoomed ? periodTax : t.total_realized_tax_eur), ''],
    ['Dividends', fmtEur(t.total_dividends_eur), ''],
    ['Fees', sign(t.total_fees_eur)+' EUR', cls(t.total_fees_eur)],
    ['Total Tax', fmtEur(isZoomed ? periodTax : t.total_tax_eur), 'neg'],
  ].map(([l,v,c])=>`<div class="metric-card"><div class="label">${l}</div><div class="value ${c}">${v}</div></div>`).join('');

  if(sales.length>0){
    const tt=document.getElementById('taxTable');
    tt.innerHTML='<thead><tr><th>Ticker</th><th>Date</th><th>Qty</th><th>Proceeds</th><th>Cost Basis</th><th>Gain</th><th>Held</th><th>Rate</th><th>Tax</th></tr></thead><tbody>'+
      sales.map(s=>`<tr><td>${s.ticker}</td><td>${s.sell_date}</td><td>${fmt(s.quantity,4)}</td><td>${fmtEur(s.sell_price_eur)}</td><td>${fmtEur(s.cost_basis_eur)}</td><td class="${cls(s.gain_eur)}">${sign(s.gain_eur)} EUR</td><td>${fmt(s.holding_years,1)}y</td><td>${Math.round(s.tax_rate*100)}%</td><td>${fmtEur(s.tax_eur)}</td></tr>`).join('')+'</tbody>';
    makeSortable(tt);
  }
}

// --- Transaction history ---
const PAGE_SIZE=50;
let txPage=0, txFiltered=[], txDateFiltered=[];
const txTable=document.getElementById('txTable');
const txPag=document.getElementById('txPagination');
const txCountEl=document.getElementById('txCount');
const txFilterEl=document.getElementById('txFilter');

function getDateFilteredTx() {
  let txs = D.transactions;
  // Filter by active asset classes
  if (hasFilter && !isDefaultSelection()) {
    txs = txs.filter(t => activeClasses.has(t.asset_class));
  }
  if (!isZoomed) return txs;
  const sd = allDates[selStart], ed = allDates[selEnd];
  return txs.filter(t => t.date >= sd && t.date <= ed);
}

function applyTxFilter() {
  txDateFiltered = getDateFilteredTx();
  const q = txFilterEl.value.toUpperCase();
  txFiltered = q
    ? txDateFiltered.filter(t => (t.ticker && t.ticker.toUpperCase().includes(q)) || (t.type && t.type.toUpperCase().includes(q)))
    : txDateFiltered;
  txPage = 0;
  renderTxPage();
}

function updateTransactions() { applyTxFilter(); }

function renderTxPage(){
  const start=txPage*PAGE_SIZE, end=start+PAGE_SIZE;
  const page=txFiltered.slice(start,end);
  const totalPages=Math.ceil(txFiltered.length/PAGE_SIZE);
  txCountEl.textContent=txFiltered.length+' transactions';
  const tagClsMap = {cfd:'tag-cfd',stock:'tag-stock',crypto:'tag-crypto',savings:'tag-savings'};
  txTable.innerHTML='<thead><tr><th>Date</th><th>Ticker</th><th>Type</th><th>Qty</th><th>Price</th><th>Amount</th><th>Ccy</th><th>FX</th><th>Class</th></tr></thead><tbody>'+
    page.map(t=>{
      const tagCls=tagClsMap[t.asset_class]||'tag-stock';
      return `<tr><td>${t.date}</td><td><strong>${t.ticker}</strong></td><td>${t.type}</td><td>${t.quantity!=null?fmt(t.quantity,4):'—'}</td><td>${t.price_per_share!=null?fmt(t.price_per_share,4):'—'}</td><td class="${cls(t.total_amount)}">${t.total_amount!=null?fmt(t.total_amount):'—'}</td><td>${t.currency}</td><td>${t.fx_rate!=null?fmt(t.fx_rate,4):'—'}</td><td><span class="tag ${tagCls}">${t.asset_class}</span></td></tr>`;
    }).join('')+'</tbody>';
  txPag.innerHTML=totalPages>1?
    `<button onclick="txGo(-1)" ${txPage===0?'disabled':''}>← Prev</button><span>Page ${txPage+1} of ${totalPages}</span><button onclick="txGo(1)" ${txPage>=totalPages-1?'disabled':''}>Next →</button>`:'';
  makeSortable(txTable);
}
window.txGo=function(dir){txPage=Math.max(0,txPage+dir);renderTxPage();};
txFilterEl.addEventListener('input', function() { applyTxFilter(); });

// --- Sortable tables ---
function makeSortable(table){
  const ths=table.querySelectorAll('th');
  ths.forEach((th,idx)=>{
    th.innerHTML=th.textContent+' <span class="arrow"></span>';
    th.addEventListener('click',function(){
      const tbody=table.querySelector('tbody');
      if(!tbody)return;
      const rows=Array.from(tbody.rows);
      const dir=th.dataset.dir==='asc'?'desc':'asc';
      ths.forEach(h=>{h.dataset.dir='';h.querySelector('.arrow').textContent='';});
      th.dataset.dir=dir;
      th.querySelector('.arrow').textContent=dir==='asc'?'▲':'▼';
      rows.sort((a,b)=>{
        let av=a.cells[idx].textContent.replace(/[^\\d.\\-]/g,'');
        let bv=b.cells[idx].textContent.replace(/[^\\d.\\-]/g,'');
        const an=parseFloat(av),bn=parseFloat(bv);
        if(!isNaN(an)&&!isNaN(bn))return dir==='asc'?an-bn:bn-an;
        av=a.cells[idx].textContent;bv=b.cells[idx].textContent;
        return dir==='asc'?av.localeCompare(bv):bv.localeCompare(av);
      });
      rows.forEach(r=>tbody.appendChild(r));
    });
  });
}

// --- Range buttons ---
(function(){
  const bar = document.getElementById('rangeBar');
  if (!bar) return;
  bar.addEventListener('click', function(e) {
    const btn = e.target.closest('.range-btn');
    if (!btn) return;
    bar.querySelectorAll('.range-btn').forEach(function(b){ b.classList.remove('active'); });
    btn.classList.add('active');
    const days = parseInt(btn.dataset.days);
    const ytd = btn.dataset.ytd === '1';
    if (days === -1) {
      selStart = 0; selEnd = N - 1; isZoomed = false;
      [portfolioChart, benchmarkChart].forEach(function(c) {
        if (!c) return;
        delete c.options.scales.x.min;
        delete c.options.scales.x.max;
        c.update();
      });
      updateAll();
      return;
    }
    let targetStart;
    if (ytd) {
      const lastDate = new Date(allDates[N-1]);
      targetStart = new Date(lastDate.getFullYear(), 0, 1);
    } else {
      const endDate = new Date(allDates[N-1]);
      targetStart = new Date(endDate.getTime() - days * 86400000);
    }
    let si = 0;
    for (let i = 0; i < N; i++) { if (new Date(allDates[i]) >= targetStart) { si = i; break; } }
    selStart = si; selEnd = N - 1; isZoomed = true;
    const startMs = new Date(allDates[si]).getTime();
    const endMs = new Date(allDates[N-1]).getTime();
    [portfolioChart, benchmarkChart].forEach(function(c) {
      if (!c) return;
      c.options.scales.x.min = startMs;
      c.options.scales.x.max = endMs;
      c.update('none');
    });
    updateAll();
  });
})();

// --- Monthly heatmap ---
function buildHeatmap() {
  const el = document.getElementById('heatmap');
  if (!el || ds.dates.length === 0) return;
  const dates = ds.dates;
  const hasPerfIdx = ds.perf_index && ds.perf_index.length === dates.length;
  const values = hasPerfIdx ? ds.perf_index : ds.value_eur;
  // Build month -> {si, ei} map
  const monthMap = {};
  for (let i = 0; i < dates.length; i++) {
    const ym = dates[i].substring(0, 7);
    if (!monthMap[ym]) monthMap[ym] = {si: i, ei: i};
    else monthMap[ym].ei = i;
  }
  // Collect sorted years
  const yrSet = new Set();
  const years = [];
  Object.keys(monthMap).sort().forEach(function(k){ const y=k.substring(0,4); if(!yrSet.has(y)){yrSet.add(y);years.push(y);} });
  const mNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  // Scale: find max absolute monthly return (cap at 20%)
  let maxAbs = 5;
  Object.keys(monthMap).forEach(function(ym){
    const d = monthMap[ym];
    if (values[d.si] > 0) { const r = Math.abs((values[d.ei]/values[d.si]-1)*100); if (r > maxAbs) maxAbs = r; }
  });
  maxAbs = Math.min(maxAbs, 20);
  function cellBg(ret) {
    const intensity = Math.min(Math.abs(ret)/maxAbs, 1);
    const alpha = (0.12 + 0.78*intensity).toFixed(2);
    return ret >= 0 ? 'rgba(22,163,74,'+alpha+')' : 'rgba(220,38,38,'+alpha+')';
  }
  function cellFg(ret) {
    return Math.min(Math.abs(ret)/maxAbs,1) > 0.5 ? '#fff' : 'var(--text)';
  }
  let h = '<div class="heatmap-wrap"><table class="heatmap-table"><thead><tr><th></th>';
  mNames.forEach(function(m){ h += '<th>'+m+'</th>'; });
  h += '<th class="heatmap-year-col">Year</th></tr></thead><tbody>';
  years.forEach(function(year){
    h += '<tr><td class="heatmap-year-label">'+year+'</td>';
    let ySi=null, yEi=null;
    for (let m=1; m<=12; m++) {
      const ym = year+'-'+(m<10?'0':'')+m;
      const d = monthMap[ym];
      if (!d || values[d.si] <= 0) { h += '<td class="heatmap-empty"></td>'; continue; }
      const ret = (values[d.ei]/values[d.si]-1)*100;
      const s = ret>=0?'+':'';
      h += '<td class="heatmap-cell" style="background:'+cellBg(ret)+';color:'+cellFg(ret)+'" title="'+ym+': '+s+ret.toFixed(2)+'%">'+s+ret.toFixed(1)+'%</td>';
      if (ySi===null) ySi=d.si;
      yEi=d.ei;
    }
    if (ySi!==null && values[ySi]>0) {
      const ret = (values[yEi]/values[ySi]-1)*100;
      const s = ret>=0?'+':'';
      h += '<td class="heatmap-cell heatmap-year-cell" style="background:'+cellBg(ret)+';color:'+cellFg(ret)+'"><strong>'+s+ret.toFixed(1)+'%</strong></td>';
    } else { h += '<td></td>'; }
    h += '</tr>';
  });
  h += '</tbody></table></div>';
  el.innerHTML = h;
}

// --- Initial render ---
updateAll();
buildHeatmap();

// --- Real Estate section (runs after main render so any error here is isolated) ---
try {
  const RE = D.real_estate;
  if (RE && RE.properties && RE.properties.length > 0) {
    document.getElementById('realEstateSection').style.display = '';

    const propTypeLabels = {
      stanovanje: 'Apartment', hisa: 'House', garaza: 'Garage',
      poslovni: 'Commercial', zemljisce: 'Land'
    };

    // Summary cards
    const cards = [
      ['Properties', RE.properties.length, ''],
      ['Purchase Total', fmtEur(RE.total_purchase_eur), ''],
      ['ETN Estimate', fmtEur(RE.total_estimated_eur), ''],
      ['Unrealized Gain', sign(RE.total_gain_eur) + ' EUR', cls(RE.total_gain_eur),
       sign(RE.total_gain_pct) + '%'],
    ];
    document.getElementById('reCards').innerHTML = cards.map(([l, v, c, sub]) =>
      '<div class="metric-card"><div class="label">' + l + '</div><div class="value ' + (c||'') + '">' + v + '</div>' +
      (sub ? '<div class="sub ' + (c||'') + '">' + sub + '</div>' : '') + '</div>'
    ).join('');

    // Value history chart
    const hist = RE.history || {};
    const reColors = ['#db2777','#f59e0b','#8b5cf6','#06b6d4','#10b981'];
    const reDatasets = RE.properties.map(function(p, i) {
      const h = hist[p.ticker];
      if (!h) return null;
      return {
        label: p.name,
        data: h.dates.map(function(d, j) { return {x: d, y: h.values[j]}; }),
        borderColor: reColors[i % reColors.length],
        backgroundColor: reColors[i % reColors.length] + '18',
        fill: false, tension: 0.3, pointRadius: 4, borderWidth: 2,
      };
    }).filter(Boolean);

    if (reDatasets.length > 0 && typeof Chart !== 'undefined') {
      const ctx = document.getElementById('reChart').getContext('2d');
      new Chart(ctx, {
        type: 'line',
        data: { datasets: reDatasets },
        options: {
          responsive: true, maintainAspectRatio: false,
          interaction: {mode: 'index', intersect: false},
          scales: {
            x: {type: 'time', time: {unit: 'month', tooltipFormat: 'yyyy-MM-dd'}, grid: {display: false}},
            y: {title: {display: true, text: 'EUR'}, ticks: {callback: function(v){ return v.toLocaleString(); }}}
          },
          plugins: {tooltip: {callbacks: {label: function(c){ return c.dataset.label + ': ' + fmt(c.parsed.y) + ' EUR'; }}}}
        }
      });
    }

    // Properties table
    const pt = document.getElementById('reTable');
    pt.innerHTML = '<thead><tr><th>Ticker</th><th>Name</th><th>Type</th><th>Area m²</th>' +
      '<th>Purchase Date</th><th>Purchase EUR</th><th>ETN Value EUR</th>' +
      '<th>Gain EUR</th><th>Gain %</th><th>ETN Date</th></tr></thead><tbody>' +
      RE.properties.map(function(p) {
        return '<tr>' +
          '<td><strong>' + p.ticker + '</strong></td>' +
          '<td>' + p.name + (p.address ? '<br><span style="font-size:0.75rem;color:var(--muted)">' + p.address + '</span>' : '') + '</td>' +
          '<td>' + (propTypeLabels[p.property_type] || p.property_type) + '</td>' +
          '<td>' + fmt(p.area_m2, 0) + '</td>' +
          '<td>' + p.purchase_date + '</td>' +
          '<td>' + fmtEur(p.purchase_price_eur) + '</td>' +
          '<td>' + fmtEur(p.estimated_value_eur) + '</td>' +
          '<td class="' + cls(p.unrealized_gain_eur) + '">' + sign(p.unrealized_gain_eur) + ' EUR</td>' +
          '<td class="' + cls(p.unrealized_gain_pct) + '">' + sign(p.unrealized_gain_pct) + '%</td>' +
          '<td style="color:var(--muted);font-size:0.8rem">' + (p.estimated_date || '—') + '</td>' +
          '</tr>';
      }).join('') + '</tbody>';
    makeSortable(pt);
  }
} catch(e) { console.error('Real estate section error:', e); }
})();
"""
