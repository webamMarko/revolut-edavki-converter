"""Portfolio analytics engine — daily portfolio reconstruction and metric computation."""

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd


@dataclass
class PositionDetail:
    ticker: str
    quantity: float
    cost_basis_eur: float
    market_value_eur: float
    unrealized_gain_eur: float
    unrealized_gain_pct: float
    weight_pct: float


@dataclass
class BenchmarkComparison:
    name: str
    ticker: str
    return_pct: float
    portfolio_return_pct: float
    alpha_pct: float


@dataclass
class AnalyticsResult:
    # Summary
    portfolio_value_eur: float
    total_invested_eur: float
    absolute_gain_eur: float
    total_return_pct: float
    cagr_pct: float | None
    twr_pct: float | None
    max_drawdown_pct: float
    max_drawdown_peak_date: str
    max_drawdown_trough_date: str
    # Income
    total_dividends_eur: float
    total_realized_gain_eur: float
    total_unrealized_gain_eur: float
    # Positions
    positions: list[PositionDetail]
    # Benchmarks
    benchmarks: list[BenchmarkComparison]
    # Daily series (for export and charting)
    daily_series: pd.DataFrame
    benchmark_series: dict  # ticker -> pd.Series of rebased values
    # Period
    start_date: str
    end_date: str


def _get_fx_rate(fx_cache: dict, date_str: str, conn: sqlite3.Connection) -> float:
    """Get EUR/USD rate for a date, with forward-fill from cache."""
    if date_str in fx_cache:
        return fx_cache[date_str]
    row = conn.execute(
        "SELECT eur_usd FROM fx_rates WHERE date <= ? ORDER BY date DESC LIMIT 1",
        (date_str,)
    ).fetchone()
    rate = row[0] if row else 1.10  # sensible fallback
    fx_cache[date_str] = rate
    return rate


def _get_price(price_cache: dict, ticker: str, date_str: str, conn: sqlite3.Connection) -> float | None:
    """Get closing price for a ticker on a date, with forward-fill."""
    key = (ticker, date_str)
    if key in price_cache:
        return price_cache[key]
    row = conn.execute(
        "SELECT close, currency FROM daily_prices WHERE ticker = ? AND date <= ? ORDER BY date DESC LIMIT 1",
        (ticker, date_str)
    ).fetchone()
    if row:
        price_cache[key] = (row[0], row[1])
        return (row[0], row[1])
    return None


def _build_holdings_timeline(conn: sqlite3.Connection) -> list[dict]:
    """Query all transactions and return sorted list of dicts."""
    rows = conn.execute(
        """SELECT date, ticker, type, quantity, price_per_share, total_amount,
                  currency, fx_rate
           FROM transactions ORDER BY date"""
    ).fetchall()
    return [dict(r) for r in rows]


def _compute_price_adjustments(conn: sqlite3.Connection, transactions: list[dict]) -> dict:
    """Compute price adjustment factors per ticker.

    yfinance prices are fully split-adjusted (retroactively). To correctly value
    holdings at historical points in time, we need to know how much yfinance has
    adjusted each ticker's price relative to the actual transaction price.

    For each ticker, we compare the CSV's price_per_share on a known trade date
    to yfinance's close price on the same date. The ratio tells us how to
    convert between yfinance-adjusted and actual prices.

    We build a schedule of adjustment factors that changes at each split.
    Between splits, the factor is constant. At a split, yfinance's adjustment
    changes by the split ratio.

    Returns: {ticker: factor} where actual_price ≈ yfinance_price * factor
    The factor is valid for the CURRENT (latest) date and changes over time
    for tickers with historical splits.
    """
    # For robustness, we don't try to track historical adjustment factors.
    # Instead, we use a different approach: track holdings in ORIGINAL
    # (non-adjusted) terms and convert yfinance prices to actual prices
    # by computing price_adjustment = csv_price / yfinance_price for each trade.
    pass  # Not needed with the new approach below


def compute_analytics(conn: sqlite3.Connection, year: int | None = None,
                      start_date: datetime | None = None,
                      end_date: datetime | None = None) -> AnalyticsResult:
    """Compute full portfolio analytics.

    Holdings are tracked in ORIGINAL CSV quantities (not split-adjusted).
    For daily valuation, we compute each ticker's adjustment factor by comparing
    the last known CSV trade price to yfinance's price on that date, then apply
    that factor to all yfinance prices for that ticker until the next trade.
    """
    transactions = _build_holdings_timeline(conn)
    if not transactions:
        raise ValueError("No transactions in database. Run 'import' first.")

    # Determine date range
    first_date = transactions[0]["date"][:10]
    today = datetime.now().strftime("%Y-%m-%d")

    if year:
        period_start = f"{year}-01-01"
        period_end = f"{year}-12-31"
    elif start_date and end_date:
        period_start = start_date.strftime("%Y-%m-%d")
        period_end = end_date.strftime("%Y-%m-%d")
    else:
        period_start = first_date
        period_end = today

    # Walk through all transactions to build holdings state.
    # Holdings use ORIGINAL quantities from the CSV. Stock splits adjust them.
    # For daily valuation, we derive a price correction factor per ticker.
    holdings = defaultdict(float)  # ticker -> quantity (original CSV terms)
    cost_basis = defaultdict(float)  # ticker -> total cost in EUR
    fifo_lots = defaultdict(list)  # ticker -> [(qty, cost_per_share_eur, date)]
    total_invested = 0.0
    total_dividends = 0.0
    total_realized_gain = 0.0
    cash_flows = []  # (date, amount_eur) for TWR

    # Price correction: for each ticker, store the ratio actual_price / yfinance_price
    # computed at the last trade date. This corrects for yfinance's retroactive
    # split adjustments. Updated on every BUY/SELL with a known price.
    price_correction = {}  # ticker -> factor (multiply yfinance close by this)

    fx_cache = {}
    price_cache = {}

    # Daily tracking
    daily_records = []
    tx_by_date = defaultdict(list)
    for tx in transactions:
        tx_by_date[tx["date"][:10]].append(tx)

    # Generate date range from first transaction to today/period_end
    current = datetime.strptime(first_date, "%Y-%m-%d")
    end = datetime.strptime(min(period_end, today), "%Y-%m-%d")

    while current <= end:
        date_str = current.strftime("%Y-%m-%d")

        # Process transactions for this date
        for tx in tx_by_date.get(date_str, []):
            tx_type = tx["type"]
            ticker = tx["ticker"]
            qty = tx["quantity"] or 0
            amount = tx["total_amount"] or 0
            fx = tx["fx_rate"] or 1.0
            pps = tx["price_per_share"] or 0

            amount_eur = abs(amount) / fx if fx > 0 else abs(amount)
            pps_eur = pps / fx if fx > 0 else pps

            if "BUY" in tx_type and ticker:
                holdings[ticker] += qty
                cost_basis[ticker] += amount_eur
                fifo_lots[ticker].append((qty, pps_eur, tx["date"][:10]))
                cash_flows.append((date_str, -amount_eur))

                # Update price correction factor
                if pps > 0:
                    yf_data = _get_price(price_cache, ticker, date_str, conn)
                    if yf_data and yf_data[0] > 0:
                        price_correction[ticker] = pps / yf_data[0]

            elif "SELL" in tx_type and ticker:
                holdings[ticker] -= qty
                # FIFO: consume lots to compute realized gain
                remaining = qty
                sell_proceeds_eur = amount_eur
                cost_of_sold = 0.0
                new_lots = []
                for lot_qty, lot_cost, lot_date in fifo_lots.get(ticker, []):
                    if remaining <= 0:
                        new_lots.append((lot_qty, lot_cost, lot_date))
                        continue
                    if lot_qty <= remaining:
                        cost_of_sold += lot_qty * lot_cost
                        remaining -= lot_qty
                    else:
                        cost_of_sold += remaining * lot_cost
                        new_lots.append((lot_qty - remaining, lot_cost, lot_date))
                        remaining = 0
                fifo_lots[ticker] = new_lots
                cost_basis[ticker] -= cost_of_sold
                total_realized_gain += sell_proceeds_eur - cost_of_sold
                cash_flows.append((date_str, sell_proceeds_eur))

                # Update price correction factor
                if pps > 0:
                    yf_data = _get_price(price_cache, ticker, date_str, conn)
                    if yf_data and yf_data[0] > 0:
                        price_correction[ticker] = pps / yf_data[0]

            elif "STOCK SPLIT" in tx_type and ticker:
                # Adjust holdings in original terms (CSV records the change)
                old_qty = holdings[ticker]
                if old_qty > 0 and qty != 0:
                    ratio = (old_qty + qty) / old_qty
                    holdings[ticker] = old_qty + qty
                    # Adjust FIFO lots
                    fifo_lots[ticker] = [
                        (lq * ratio, lc / ratio, ld)
                        for lq, lc, ld in fifo_lots[ticker]
                    ]
                    # After a split, yfinance prices change by 1/ratio,
                    # so the correction factor also changes by ratio
                    if ticker in price_correction:
                        price_correction[ticker] /= ratio

            elif tx_type in ("DIVIDEND", "BOND COUPON") and amount:
                total_dividends += amount_eur

            elif tx_type == "RETURN OF CAPITAL" and ticker and amount:
                cost_basis[ticker] -= amount_eur

            elif "MERGER" in tx_type and ticker:
                if "CASH" in tx_type:
                    # Treat as forced sale
                    sell_proceeds = amount_eur
                    cost_of_sold = cost_basis.get(ticker, 0)
                    total_realized_gain += sell_proceeds - cost_of_sold
                    cash_flows.append((date_str, sell_proceeds))
                holdings[ticker] = 0
                cost_basis[ticker] = 0
                fifo_lots[ticker] = []

            elif tx_type == "POSITION CLOSURE" and ticker:
                cost_of_sold = cost_basis.get(ticker, 0)
                total_realized_gain -= cost_of_sold  # total loss
                holdings[ticker] = 0
                cost_basis[ticker] = 0
                fifo_lots[ticker] = []

            elif tx_type == "CASH TOP-UP" and amount:
                total_invested += amount_eur
                cash_flows.append((date_str, -amount_eur))

            elif tx_type == "CASH WITHDRAWAL" and amount:
                total_invested -= amount_eur
                cash_flows.append((date_str, amount_eur))

        # Compute portfolio value for this date
        portfolio_value = 0.0
        fx_rate = _get_fx_rate(fx_cache, date_str, conn)

        for ticker, qty in holdings.items():
            if qty <= 1e-10:
                continue
            price_data = _get_price(price_cache, ticker, date_str, conn)
            if price_data:
                yf_close, currency = price_data
                # Apply correction factor: yfinance prices are fully
                # split-adjusted, so multiply by our correction factor
                # to get the actual price matching our original quantities.
                correction = price_correction.get(ticker, 1.0)
                actual_close = yf_close * correction
                if currency == "EUR":
                    portfolio_value += qty * actual_close
                else:
                    portfolio_value += qty * actual_close / fx_rate
            else:
                # Use cost basis as fallback
                portfolio_value += cost_basis.get(ticker, 0)

        if date_str >= period_start:
            daily_records.append({
                "date": date_str,
                "value_eur": portfolio_value,
                "invested_eur": total_invested,
                "dividends_eur": total_dividends,
                "realized_gain_eur": total_realized_gain,
            })

        current += timedelta(days=1)

    # Build daily DataFrame
    daily_df = pd.DataFrame(daily_records)
    if daily_df.empty:
        raise ValueError("No data for the requested period.")
    daily_df.set_index("date", inplace=True)

    # Current state
    current_value = daily_df["value_eur"].iloc[-1]
    current_invested = daily_df["invested_eur"].iloc[-1]
    absolute_gain = current_value - current_invested + total_dividends + total_realized_gain
    total_return_pct = (absolute_gain / current_invested * 100) if current_invested > 0 else 0.0

    # CAGR
    n_days = len(daily_df)
    years = n_days / 365.25
    if years > 0 and current_invested > 0 and current_value > 0:
        cagr = ((current_value / current_invested) ** (1 / years) - 1) * 100
    else:
        cagr = None

    # TWR (time-weighted return)
    twr = _compute_twr(daily_df, cash_flows, period_start)

    # Max drawdown
    values = daily_df["value_eur"]
    peak = values.expanding().max()
    drawdown = (values - peak) / peak
    max_dd = drawdown.min() * 100
    trough_idx = drawdown.idxmin()
    peak_idx = values.loc[:trough_idx].idxmax()

    # Unrealized gains
    total_unrealized = 0.0
    for ticker, qty in holdings.items():
        if qty <= 1e-10:
            continue
        total_unrealized += (qty * _get_current_value_eur(
            ticker, period_end if period_end <= today else today, conn, fx_cache, price_cache
        )) - cost_basis.get(ticker, 0)

    # Position details
    positions = []
    total_val = current_value if current_value > 0 else 1
    for ticker, qty in sorted(holdings.items()):
        if qty <= 1e-10:
            continue
        mv = qty * _get_current_value_eur(
            ticker, period_end if period_end <= today else today, conn, fx_cache, price_cache,
            per_share=True
        )
        cb = cost_basis.get(ticker, 0)
        ug = mv - cb
        ug_pct = (ug / cb * 100) if cb > 0 else 0.0
        positions.append(PositionDetail(
            ticker=ticker,
            quantity=qty,
            cost_basis_eur=cb,
            market_value_eur=mv,
            unrealized_gain_eur=ug,
            unrealized_gain_pct=ug_pct,
            weight_pct=mv / total_val * 100,
        ))

    # Benchmark comparisons
    benchmarks, benchmark_series = _compute_benchmarks(conn, daily_df, period_start, period_end, fx_cache, price_cache)

    return AnalyticsResult(
        portfolio_value_eur=current_value,
        total_invested_eur=current_invested,
        absolute_gain_eur=absolute_gain,
        total_return_pct=total_return_pct,
        cagr_pct=cagr,
        twr_pct=twr,
        max_drawdown_pct=max_dd,
        max_drawdown_peak_date=peak_idx,
        max_drawdown_trough_date=trough_idx,
        total_dividends_eur=total_dividends,
        total_realized_gain_eur=total_realized_gain,
        total_unrealized_gain_eur=total_unrealized,
        positions=positions,
        benchmarks=benchmarks,
        daily_series=daily_df,
        benchmark_series=benchmark_series,
        start_date=period_start,
        end_date=period_end,
    )


def _get_current_value_eur(ticker: str, date_str: str, conn: sqlite3.Connection,
                           fx_cache: dict, price_cache: dict,
                           per_share: bool = False) -> float:
    """Get a ticker's current value in EUR (total or per-share)."""
    price_data = _get_price(price_cache, ticker, date_str, conn)
    if not price_data:
        return 0.0
    close, currency = price_data
    fx_rate = _get_fx_rate(fx_cache, date_str, conn)
    if currency == "EUR":
        return close
    return close / fx_rate


def _compute_twr(daily_df: pd.DataFrame, cash_flows: list, period_start: str) -> float | None:
    """Compute time-weighted return by chaining sub-period returns."""
    values = daily_df["value_eur"]
    if len(values) < 2:
        return None

    # Group cash flows by date within the period
    cf_by_date = defaultdict(float)
    for date, amount in cash_flows:
        if date >= period_start:
            cf_by_date[date] += amount

    # Chain sub-period returns
    product = 1.0
    dates = list(values.index)
    for i in range(1, len(dates)):
        v_prev = values.iloc[i - 1]
        v_curr = values.iloc[i]
        cf = cf_by_date.get(dates[i], 0)

        # sub-period return: (V_end) / (V_start + cash_flow)
        denominator = v_prev - cf  # cf is negative for inflows
        if abs(denominator) > 1e-6:
            product *= v_curr / denominator

    return (product - 1) * 100


def _compute_benchmarks(conn: sqlite3.Connection, daily_df: pd.DataFrame,
                        period_start: str, period_end: str,
                        fx_cache: dict, price_cache: dict) -> tuple[list[BenchmarkComparison], dict]:
    """Compare portfolio to benchmark indexes. Returns (comparisons, daily_series_dict)."""
    from .price_fetcher import BENCHMARKS

    portfolio_values = daily_df["value_eur"]
    if len(portfolio_values) < 2:
        return [], {}

    # Find first non-zero value for rebasing
    first_nonzero = portfolio_values[portfolio_values > 0]
    if first_nonzero.empty:
        return [], {}
    portfolio_return = (portfolio_values.iloc[-1] / first_nonzero.iloc[0] - 1) * 100

    results = []
    bench_daily = {}

    for ticker, name in BENCHMARKS.items():
        # Get full daily series for this benchmark
        rows = conn.execute(
            "SELECT date, close FROM daily_prices WHERE ticker = ? AND date >= ? AND date <= ? ORDER BY date",
            (ticker, period_start, period_end)
        ).fetchall()

        if not rows:
            continue

        dates = [r[0] for r in rows]
        closes = [r[1] for r in rows]
        start_price = closes[0]
        end_price = closes[-1]

        if start_price > 0:
            bench_return = (end_price / start_price - 1) * 100
            results.append(BenchmarkComparison(
                name=name,
                ticker=ticker,
                return_pct=bench_return,
                portfolio_return_pct=portfolio_return,
                alpha_pct=portfolio_return - bench_return,
            ))
            # Rebase to 100
            rebased = pd.Series(
                [c / start_price * 100 for c in closes],
                index=pd.Index(dates, name="date"),
                name=name,
            )
            bench_daily[ticker] = rebased

    return results, bench_daily
