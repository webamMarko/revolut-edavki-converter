"""Portfolio analytics engine — daily portfolio reconstruction and metric computation."""

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd

from .importer import normalize_date


@dataclass
class PositionDetail:
    ticker: str
    quantity: float
    cost_basis_eur: float
    market_value_eur: float
    unrealized_gain_eur: float
    unrealized_gain_pct: float
    weight_pct: float
    realized_gain_eur: float = 0.0


@dataclass
class ClosedPositionDetail:
    ticker: str
    total_cost_eur: float
    total_proceeds_eur: float
    realized_gain_eur: float
    realized_gain_pct: float


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
    total_fees_eur: float
    # Positions
    positions: list[PositionDetail]
    closed_positions: list[ClosedPositionDetail]
    position_lots: dict  # ticker -> [(qty, cost_per_share_eur, date)]
    # Benchmarks
    benchmarks: list[BenchmarkComparison]
    # Daily series (for export and charting)
    daily_series: pd.DataFrame
    benchmark_series: dict  # ticker -> pd.Series of rebased values
    # Period
    start_date: str
    end_date: str
    # Scope
    scope: str


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


def _build_holdings_timeline(conn: sqlite3.Connection, scope: str = "all") -> list[dict]:
    """Query all transactions and return sorted list of dicts.

    scope: 'stock', 'cfd', 'crypto', or 'all'
    """
    if scope == "all":
        rows = conn.execute(
            """SELECT date, ticker, type, quantity, price_per_share, total_amount,
                      currency, fx_rate, asset_class, source_file
               FROM transactions WHERE asset_class != 'realestate' ORDER BY date"""
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT date, ticker, type, quantity, price_per_share, total_amount,
                      currency, fx_rate, asset_class, source_file
               FROM transactions WHERE asset_class = ? ORDER BY date""",
            (scope,)
        ).fetchall()
    return [dict(r) for r in rows]


def _sources_with_cash_events(conn: sqlite3.Connection) -> set[str]:
    """Return set of source_file names that contain CASH TOP-UP or CASH WITHDRAWAL events.

    Files with cash events track invested amounts via those events.
    Files without them (e.g. Ilirika) need BUY/SELL to track invested.
    """
    rows = conn.execute(
        "SELECT DISTINCT source_file FROM transactions WHERE type IN ('CASH TOP-UP', 'CASH WITHDRAWAL')"
    ).fetchall()
    return {r[0] for r in rows}


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
                      end_date: datetime | None = None,
                      scope: str = "all") -> AnalyticsResult:
    """Compute full portfolio analytics.

    Holdings are tracked in ORIGINAL CSV quantities (not split-adjusted).
    For daily valuation, we compute each ticker's adjustment factor by comparing
    the last known CSV trade price to yfinance's price on that date, then apply
    that factor to all yfinance prices for that ticker until the next trade.

    scope: 'stock', 'cfd', or 'all'
    """
    transactions = _build_holdings_timeline(conn, scope=scope)
    if not transactions:
        raise ValueError("No transactions in database. Run 'import' first.")

    # Detect which source files have cash events (CASH TOP-UP/WITHDRAWAL).
    # For sources without cash events (e.g. Ilirika broker), BUY/SELL amounts
    # are used to track invested capital instead.
    cash_event_sources = _sources_with_cash_events(conn)

    # Determine date range
    first_date = normalize_date(transactions[0]["date"])
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
    holdings = defaultdict(float)  # ticker -> signed quantity (positive=long, negative=short)
    cost_basis = defaultdict(float)  # ticker -> total cost in EUR (long lots only)
    fifo_lots = defaultdict(list)  # ticker -> [(qty, cost_per_share_eur, date)] for longs
    short_lots = defaultdict(list)  # ticker -> [(qty, entry_pps_eur, date)] for shorts (CFD)
    total_invested = 0.0
    total_dividends = 0.0
    total_realized_gain = 0.0
    per_ticker_realized = defaultdict(float)  # ticker -> cumulative realized gain EUR
    per_ticker_cost_sold = defaultdict(float)  # ticker -> total cost basis of sold shares
    per_ticker_proceeds = defaultdict(float)  # ticker -> total sale proceeds
    total_fees = 0.0  # commissions + overnight fees (CFD)
    cfd_cash = 0.0  # running cash balance for CFD account valuation
    stock_cash = 0.0  # uninvested cash from CASH TOP-UP (for sources with cash events)
    cash_flows = []  # (date, amount_eur) for TWR

    # Price correction: for each ticker, store the ratio actual_price / yfinance_price
    # computed at the last trade date. This corrects for yfinance's retroactive
    # split adjustments. Updated on every BUY/SELL with a known price.
    price_correction = {}  # ticker -> factor (multiply yfinance close by this)

    # CFD: track last known price per share in EUR for open position valuation
    last_known_price_eur = {}  # ticker -> price_per_share_eur

    is_cfd = scope == "cfd"
    is_crypto = scope == "crypto"
    is_savings = scope == "savings"
    is_realestate = scope == "realestate"

    fx_cache = {}
    price_cache = {}

    # Daily tracking
    daily_records = []
    tx_by_date = defaultdict(list)
    for tx in transactions:
        d = normalize_date(tx["date"])
        if d:
            tx_by_date[d].append(tx)

    # Generate date range from first transaction to today/period_end
    current = datetime.strptime(first_date, "%Y-%m-%d")
    end = datetime.strptime(min(period_end, today), "%Y-%m-%d")

    while current <= end:
        date_str = current.strftime("%Y-%m-%d")

        # Process transactions for this date
        for tx in tx_by_date.get(date_str, []):
            tx_type = tx["type"]
            ticker = tx["ticker"]
            qty = tx["quantity"] if tx["quantity"] is not None else 0
            qty_is_null = tx["quantity"] is None
            amount = tx["total_amount"] or 0
            fx = tx["fx_rate"] or 1.0
            pps = tx["price_per_share"] or 0
            currency = tx.get("currency", "USD")

            # If fx_rate is 1.0 but currency is not EUR, look up actual FX rate
            if fx == 1.0 and currency != "EUR" and amount > 0:
                db_fx = _get_fx_rate(fx_cache, date_str, conn)
                if db_fx > 0:
                    fx = db_fx

            # In 'all' scope, prefix CFD/crypto/savings tickers to avoid mixing with stocks
            is_cfd_tx = tx.get("asset_class") == "cfd"
            is_crypto_tx = tx.get("asset_class") == "crypto"
            is_savings_tx = tx.get("asset_class") == "savings"
            if scope == "all" and is_cfd_tx and ticker:
                ticker = f"CFD:{ticker}"
            elif scope == "all" and is_crypto_tx and ticker:
                ticker = f"CRYPTO:{ticker}"
            elif scope == "all" and is_savings_tx and ticker:
                ticker = f"SAVINGS:{ticker}"

            amount_eur = abs(amount) / fx if fx > 0 else abs(amount)
            pps_eur = pps / fx if fx > 0 else pps

            if "BUY" in tx_type and ticker and (is_cfd or is_cfd_tx):
                # CFD BUY: can close shorts and/or open longs
                cfd_cash -= amount_eur
                cash_flows.append((date_str, -amount_eur))
                if pps_eur > 0:
                    last_known_price_eur[ticker] = pps_eur

                remaining = qty
                # Close short positions first (FIFO)
                if holdings.get(ticker, 0) < 0:
                    new_shorts = []
                    for s_qty, s_pps, s_date in short_lots.get(ticker, []):
                        if remaining <= 0:
                            new_shorts.append((s_qty, s_pps, s_date))
                            continue
                        if s_qty <= remaining:
                            # Realized gain on short close: entry - exit
                            total_realized_gain += (s_pps - pps_eur) * s_qty
                            per_ticker_realized[ticker] += (s_pps - pps_eur) * s_qty
                            per_ticker_proceeds[ticker] += s_pps * s_qty
                            per_ticker_cost_sold[ticker] += pps_eur * s_qty
                            remaining -= s_qty
                            holdings[ticker] += s_qty
                        else:
                            total_realized_gain += (s_pps - pps_eur) * remaining
                            per_ticker_realized[ticker] += (s_pps - pps_eur) * remaining
                            per_ticker_proceeds[ticker] += s_pps * remaining
                            per_ticker_cost_sold[ticker] += pps_eur * remaining
                            new_shorts.append((s_qty - remaining, s_pps, s_date))
                            holdings[ticker] += remaining
                            remaining = 0
                    short_lots[ticker] = new_shorts

                # Open long with any remainder
                if remaining > 0:
                    holdings[ticker] += remaining
                    cost_basis[ticker] += remaining * pps_eur
                    fifo_lots[ticker].append((remaining, pps_eur, date_str))

            elif ("BUY" in tx_type or tx_type == "RECEIVE") and ticker and (is_crypto or is_crypto_tx):
                # Crypto BUY/RECEIVE: opens a long
                holdings[ticker] += qty
                cost_basis[ticker] += amount_eur
                fifo_lots[ticker].append((qty, pps_eur, date_str))
                cash_flows.append((date_str, -amount_eur))
                if "BUY" in tx_type and amount_eur > 0:
                    total_invested += amount_eur
                if pps_eur > 0:
                    last_known_price_eur[ticker] = pps_eur

            elif tx_type == "BUY" and ticker and (is_savings or is_savings_tx):
                # Savings BUY: deposit into money market fund (shares at 1.00)
                holdings[ticker] += qty
                cost_basis[ticker] += amount_eur
                fifo_lots[ticker].append((qty, pps_eur, date_str))
                cash_flows.append((date_str, -amount_eur))
                total_invested += amount_eur
                last_known_price_eur[ticker] = pps_eur if pps_eur > 0 else 1.0

            elif "BUY" in tx_type and ticker:
                # Stock BUY: always opens a long
                holdings[ticker] += qty
                cost_basis[ticker] += amount_eur
                fifo_lots[ticker].append((qty, pps_eur, date_str))

                # For sources without cash events, BUY is the external cash flow
                source = tx.get("source_file", "")
                if source not in cash_event_sources:
                    total_invested += amount_eur
                    cash_flows.append((date_str, -amount_eur))
                else:
                    stock_cash -= amount_eur  # cash moves into stock position

                # Track last known price (used as fallback for bonds/ISINs
                # that have no yfinance prices)
                if pps_eur > 0:
                    last_known_price_eur[ticker] = pps_eur

                # Update price correction factor
                if pps > 0:
                    yf_data = _get_price(price_cache, ticker, date_str, conn)
                    if yf_data and yf_data[0] > 0:
                        price_correction[ticker] = pps / yf_data[0]

            elif "SELL" in tx_type and ticker and (is_cfd or is_cfd_tx):
                # CFD SELL: can close longs and/or open shorts
                cfd_cash += amount_eur
                cash_flows.append((date_str, amount_eur))
                if pps_eur > 0:
                    last_known_price_eur[ticker] = pps_eur

                remaining = qty
                # Close long positions first (FIFO)
                if holdings.get(ticker, 0) > 0:
                    new_lots = []
                    for l_qty, l_pps, l_date in fifo_lots.get(ticker, []):
                        if remaining <= 0:
                            new_lots.append((l_qty, l_pps, l_date))
                            continue
                        if l_qty <= remaining:
                            # Realized gain on long close: exit - entry
                            total_realized_gain += (pps_eur - l_pps) * l_qty
                            per_ticker_realized[ticker] += (pps_eur - l_pps) * l_qty
                            per_ticker_cost_sold[ticker] += l_qty * l_pps
                            per_ticker_proceeds[ticker] += l_qty * pps_eur
                            cost_basis[ticker] -= l_qty * l_pps
                            remaining -= l_qty
                            holdings[ticker] -= l_qty
                        else:
                            total_realized_gain += (pps_eur - l_pps) * remaining
                            per_ticker_realized[ticker] += (pps_eur - l_pps) * remaining
                            per_ticker_cost_sold[ticker] += remaining * l_pps
                            per_ticker_proceeds[ticker] += remaining * pps_eur
                            cost_basis[ticker] -= remaining * l_pps
                            new_lots.append((l_qty - remaining, l_pps, l_date))
                            holdings[ticker] -= remaining
                            remaining = 0
                    fifo_lots[ticker] = new_lots

                # Open short with any remainder
                if remaining > 0:
                    holdings[ticker] -= remaining
                    short_lots[ticker].append((remaining, pps_eur, date_str))

            elif ("SELL" in tx_type or tx_type == "PAYMENT") and ticker and (is_crypto or is_crypto_tx):
                # Crypto SELL/PAYMENT: closes a long (FIFO)
                # NULL quantity means "sell all remaining" (full close-out)
                if qty_is_null and holdings.get(ticker, 0) > 0:
                    qty = holdings[ticker]
                holdings[ticker] -= qty
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
                per_ticker_realized[ticker] += sell_proceeds_eur - cost_of_sold
                per_ticker_cost_sold[ticker] += cost_of_sold
                per_ticker_proceeds[ticker] += sell_proceeds_eur
                cash_flows.append((date_str, sell_proceeds_eur))
                total_invested -= sell_proceeds_eur
                if pps_eur > 0:
                    last_known_price_eur[ticker] = pps_eur

            elif tx_type == "SELL" and ticker and (is_savings or is_savings_tx):
                # Savings SELL: withdrawal from money market fund (FIFO)
                holdings[ticker] -= qty
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
                per_ticker_realized[ticker] += sell_proceeds_eur - cost_of_sold
                per_ticker_cost_sold[ticker] += cost_of_sold
                per_ticker_proceeds[ticker] += sell_proceeds_eur
                cash_flows.append((date_str, sell_proceeds_eur))
                total_invested -= sell_proceeds_eur
                last_known_price_eur[ticker] = pps_eur if pps_eur > 0 else 1.0

            elif "SELL" in tx_type and ticker:
                # Stock SELL: always closes a long
                holdings[ticker] -= qty
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
                per_ticker_realized[ticker] += sell_proceeds_eur - cost_of_sold
                per_ticker_cost_sold[ticker] += cost_of_sold
                per_ticker_proceeds[ticker] += sell_proceeds_eur

                # Track last known price (fallback for bonds/ISINs)
                if pps_eur > 0:
                    last_known_price_eur[ticker] = pps_eur

                # For sources without cash events, SELL is the external cash flow
                source = tx.get("source_file", "")
                if source not in cash_event_sources:
                    total_invested -= sell_proceeds_eur
                    cash_flows.append((date_str, sell_proceeds_eur))
                else:
                    stock_cash += sell_proceeds_eur  # cash comes back from stock position

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
                source = tx.get("source_file", "")
                if source in cash_event_sources:
                    stock_cash += amount_eur

            elif tx_type in ("STAKING REWARD", "LEARN REWARD") and ticker:
                # Crypto rewards: add to holdings at zero cost (income recorded as dividend)
                if qty and qty > 0:
                    holdings[ticker] += qty
                    fifo_lots[ticker].append((qty, 0.0, date_str))
                if amount_eur > 0:
                    total_dividends += amount_eur

            elif tx_type == "INTEREST PAID" and (is_savings or is_savings_tx):
                # Savings interest: record as dividend income
                if amount_eur > 0:
                    total_dividends += amount_eur

            elif tx_type == "SERVICE FEE" and (is_savings or is_savings_tx):
                # Savings service fee: record as fee (negative amount = cost)
                total_fees -= amount_eur  # amount_eur is abs value, fees are costs

            elif tx_type == "INTEREST REINVESTED" and (is_savings or is_savings_tx):
                # Interest reinvested: the corresponding BUY adds to total_invested,
                # so subtract here to offset — reinvested interest is profit, not new cash.
                total_invested -= amount_eur

            elif tx_type == "INTEREST WITHDRAWN" and (is_savings or is_savings_tx):
                # Interest withdrawn: cash payout, already counted in INTEREST PAID.
                pass

            elif tx_type in ("COMMISSION CHARGE", "OVERNIGHT FEE"):
                # Use actual signed amount (negative = cost, positive = income)
                fee_eur = amount / fx if fx > 0 else amount
                total_fees += fee_eur
                cfd_cash += fee_eur

            elif tx_type == "RETURN OF CAPITAL" and ticker and amount:
                cost_basis[ticker] -= amount_eur

            elif "MERGER" in tx_type and ticker:
                if "CASH" in tx_type:
                    # Treat as forced sale
                    sell_proceeds = amount_eur
                    cost_of_sold = cost_basis.get(ticker, 0)
                    total_realized_gain += sell_proceeds - cost_of_sold
                    per_ticker_realized[ticker] += sell_proceeds - cost_of_sold
                    per_ticker_cost_sold[ticker] += cost_of_sold
                    per_ticker_proceeds[ticker] += sell_proceeds
                    # For sources without cash events, MERGER CASH is an external outflow
                    source = tx.get("source_file", "")
                    if source not in cash_event_sources:
                        total_invested -= sell_proceeds
                        cash_flows.append((date_str, sell_proceeds))
                holdings[ticker] = 0
                cost_basis[ticker] = 0
                fifo_lots[ticker] = []

            elif tx_type == "POSITION CLOSURE" and ticker:
                cost_of_sold = cost_basis.get(ticker, 0)
                total_realized_gain -= cost_of_sold  # total loss
                per_ticker_realized[ticker] -= cost_of_sold
                per_ticker_cost_sold[ticker] += cost_of_sold
                holdings[ticker] = 0
                cost_basis[ticker] = 0
                fifo_lots[ticker] = []

            elif tx_type == "CASH TOP-UP" and amount:
                total_invested += amount_eur
                if is_cfd or is_cfd_tx:
                    cfd_cash += amount_eur
                else:
                    stock_cash += amount_eur
                cash_flows.append((date_str, -amount_eur))

            elif tx_type == "CASH WITHDRAWAL" and amount:
                total_invested -= amount_eur
                if is_cfd or is_cfd_tx:
                    cfd_cash -= amount_eur
                else:
                    stock_cash -= amount_eur
                cash_flows.append((date_str, amount_eur))

        # Compute portfolio value for this date
        portfolio_value = 0.0
        fx_rate = _get_fx_rate(fx_cache, date_str, conn)

        # Include uninvested stock cash (from CASH TOP-UP not yet deployed)
        if stock_cash > 0:
            portfolio_value += stock_cash

        # CFD: portfolio value = cash balance + mark-to-market of open positions
        # cash balance already includes deposits, trade cash flows, and fees
        # mark-to-market: long positions add value, short positions subtract
        if is_cfd:
            portfolio_value = cfd_cash
            for ticker, qty in holdings.items():
                if abs(qty) < 1e-10:
                    continue
                price_eur = last_known_price_eur.get(ticker, 0)
                portfolio_value += qty * price_eur  # positive for longs, negative for shorts
        elif scope == "all":
            # In 'all' mode: add CFD cash component for CFD positions
            portfolio_value += cfd_cash

        for ticker, qty in holdings.items():
            if is_cfd:
                continue  # already handled above

            if ticker.startswith("CFD:") or ticker.startswith("CRYPTO:") or ticker.startswith("SAVINGS:"):
                # Mark-to-market using last known trade price
                if abs(qty) < 1e-10:
                    continue
                price_eur = last_known_price_eur.get(ticker, 0)
                portfolio_value += qty * price_eur
                continue

            if is_crypto or is_savings:
                # Crypto/savings scope: use last known trade price
                if qty <= 1e-10:
                    continue
                price_eur = last_known_price_eur.get(ticker, 0)
                portfolio_value += qty * price_eur
                continue

            if qty <= 1e-10:
                continue
            price_data = _get_price(price_cache, ticker, date_str, conn)
            if price_data:
                yf_close, currency = price_data
                correction = price_correction.get(ticker, 1.0)
                actual_close = yf_close * correction
                if currency == "EUR":
                    portfolio_value += qty * actual_close
                else:
                    portfolio_value += qty * actual_close / fx_rate
            elif ticker in last_known_price_eur:
                # No yfinance data (e.g. bonds/ISINs): use last trade price
                portfolio_value += qty * last_known_price_eur[ticker]
            else:
                portfolio_value += cost_basis.get(ticker, 0)

        if date_str >= period_start:
            daily_records.append({
                "date": date_str,
                "value_eur": portfolio_value,
                "invested_eur": total_invested,
                "dividends_eur": total_dividends,
                "realized_gain_eur": total_realized_gain,
            })

        prev_portfolio_value = portfolio_value
        current += timedelta(days=1)

    # Build daily DataFrame
    daily_df = pd.DataFrame(daily_records)
    if daily_df.empty:
        raise ValueError("No data for the requested period.")
    daily_df.set_index("date", inplace=True)

    # Compute chain-linked performance index (100-based).
    # Each day's return excludes the effect of cash flows, so deposits/withdrawals
    # don't cause jumps. Formula: daily_return = (value_today - cashflow_today) / value_yesterday - 1
    # Then compound: index[i] = index[i-1] * (1 + daily_return)
    cf_by_date = defaultdict(float)
    for cf_date, cf_amount in cash_flows:
        cf_by_date[cf_date] += cf_amount  # negative = inflow (buy/deposit), positive = outflow (sell/withdrawal)

    perf_index = []
    idx_val = 100.0
    values = daily_df["value_eur"].values
    dates = daily_df.index.tolist()
    for i in range(len(values)):
        if i == 0:
            perf_index.append(100.0 if values[0] > 0 else 0.0)
            continue
        prev_val = values[i - 1]
        cur_val = values[i]
        # Net cash flow on this date (negative = money in, positive = money out)
        net_cf = cf_by_date.get(dates[i], 0.0)
        if prev_val > 1e-6:
            # Daily return: (end_value - net_inflow) / start_value - 1
            # net_cf is negative for inflows, so subtracting it adds back the inflow
            daily_ret = (cur_val + net_cf) / prev_val - 1
            idx_val *= (1 + daily_ret)
        perf_index.append(idx_val)
    daily_df["perf_index"] = perf_index

    # Current state
    current_value = daily_df["value_eur"].iloc[-1]
    current_invested = daily_df["invested_eur"].iloc[-1]
    absolute_gain = current_value - current_invested + total_dividends + total_realized_gain
    total_return_pct = (absolute_gain / current_invested * 100) if current_invested > 0 else 0.0

    # CAGR — annualised TWR (DCA-aware: strips out effect of cash flow timing).
    # Falls back to simple value/invested CAGR when perf_index is unreliable
    # (e.g. CFDs, where leveraged swings corrupt the daily return chain).
    n_days = len(daily_df)
    years = n_days / 365.25
    cagr = None
    if years >= 0.1:
        pi = daily_df["perf_index"] if "perf_index" in daily_df.columns else pd.Series(dtype=float)
        pi_nonzero = pi[pi > 0]
        if not pi_nonzero.empty and pi.iloc[-1] > 0:
            ratio = pi.iloc[-1] / pi_nonzero.iloc[0]
            if 0 < ratio < 1e5:  # guard: reject perf_index when it has gone haywire
                cagr = (ratio ** (1 / years) - 1) * 100
        if cagr is None and current_value > 0 and current_invested > 0:
            cagr = ((current_value / current_invested) ** (1 / years) - 1) * 100

    # TWR (time-weighted return)
    twr = _compute_twr(daily_df, cash_flows, period_start)

    # Max drawdown — use perf_index (TWR-based) so that cash deposits/withdrawals
    # (including savings withdrawals) don't register as drawdowns.
    dd_series = daily_df["perf_index"] if "perf_index" in daily_df.columns else daily_df["value_eur"]
    dd_series = dd_series[dd_series > 0]  # ignore zero-value warmup days
    if dd_series.empty:
        dd_series = daily_df["value_eur"]
    peak = dd_series.expanding().max()
    drawdown = (dd_series - peak) / peak
    max_dd = drawdown.min() * 100
    trough_idx = drawdown.idxmin()
    peak_idx = dd_series.loc[:trough_idx].idxmax()

    # Unrealized gains
    total_unrealized = 0.0
    for ticker, qty in holdings.items():
        if abs(qty) < 1e-10:
            continue
        if is_cfd or ticker.startswith("CFD:"):
            price_eur = last_known_price_eur.get(ticker, 0)
            if qty > 0:
                # Long: unrealized = market_value - cost_basis
                total_unrealized += qty * price_eur - cost_basis.get(ticker, 0)
            else:
                # Short: unrealized = entry_value - current_liability
                entry_value = sum(sq * sp for sq, sp, _ in short_lots.get(ticker, []))
                total_unrealized += entry_value - abs(qty) * price_eur
        elif is_crypto or ticker.startswith("CRYPTO:"):
            price_eur = last_known_price_eur.get(ticker, 0)
            total_unrealized += qty * price_eur - cost_basis.get(ticker, 0)
        elif is_savings or ticker.startswith("SAVINGS:"):
            price_eur = last_known_price_eur.get(ticker, 0)
            total_unrealized += qty * price_eur - cost_basis.get(ticker, 0)
        else:
            if qty < 0:
                continue
            val_per_share = _get_current_value_eur(
                ticker, period_end if period_end <= today else today, conn, fx_cache, price_cache
            )
            # Fallback for bonds/ISINs with no yfinance prices
            if val_per_share == 0 and ticker in last_known_price_eur:
                val_per_share = last_known_price_eur[ticker]
            total_unrealized += (qty * val_per_share) - cost_basis.get(ticker, 0)

    # Position details
    positions = []
    total_val = max(current_value, 1)
    for ticker, qty in sorted(holdings.items()):
        if abs(qty) < 1e-10:
            continue
        if is_cfd or ticker.startswith("CFD:"):
            price_eur = last_known_price_eur.get(ticker, 0)
            if qty > 0:
                mv = qty * price_eur
                cb = cost_basis.get(ticker, 0)
            else:
                # Short position: entry value is what we sold for
                cb = sum(sq * sp for sq, sp, _ in short_lots.get(ticker, []))
                mv = abs(qty) * price_eur
        elif is_crypto or ticker.startswith("CRYPTO:"):
            price_eur = last_known_price_eur.get(ticker, 0)
            mv = qty * price_eur
            cb = cost_basis.get(ticker, 0)
        elif is_savings or ticker.startswith("SAVINGS:"):
            price_eur = last_known_price_eur.get(ticker, 0)
            mv = qty * price_eur
            cb = cost_basis.get(ticker, 0)
        else:
            if qty < 0:
                continue
            val_per_share = _get_current_value_eur(
                ticker, period_end if period_end <= today else today, conn, fx_cache, price_cache,
                per_share=True
            )
            # Fallback for bonds/ISINs with no yfinance prices
            if val_per_share == 0 and ticker in last_known_price_eur:
                val_per_share = last_known_price_eur[ticker]
            mv = qty * val_per_share
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
            realized_gain_eur=per_ticker_realized.get(ticker, 0.0),
        ))

    # Closed positions: tickers with realized gains but no current holdings
    open_tickers = {p.ticker for p in positions}
    closed_positions = []
    for ticker in sorted(per_ticker_realized):
        if ticker in open_tickers:
            continue
        realized = per_ticker_realized[ticker]
        cost = per_ticker_cost_sold.get(ticker, 0.0)
        proceeds = per_ticker_proceeds.get(ticker, 0.0)
        gain_pct = (realized / cost * 100) if cost > 0 else 0.0
        closed_positions.append(ClosedPositionDetail(
            ticker=ticker,
            total_cost_eur=cost,
            total_proceeds_eur=proceeds,
            realized_gain_eur=realized,
            realized_gain_pct=gain_pct,
        ))

    # Benchmark comparisons (skip for CFD/savings/realestate scope)
    if is_cfd or is_savings or is_realestate:
        benchmarks, benchmark_series = [], {}
    else:
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
        total_fees_eur=total_fees,
        positions=positions,
        closed_positions=closed_positions,
        position_lots={t: list(lots) for t, lots in fifo_lots.items() if lots and abs(holdings.get(t, 0)) > 1e-10},
        benchmarks=benchmarks,
        daily_series=daily_df,
        benchmark_series=benchmark_series,
        start_date=period_start,
        end_date=period_end,
        scope=scope,
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

    # Use perf_index (TWR) for portfolio return so it matches the benchmark chart,
    # which strips out cash flows. Raw value ratio would be inflated by deposits.
    perf = daily_df["perf_index"] if "perf_index" in daily_df.columns else pd.Series(dtype=float)
    first_nonzero_perf = perf[perf > 0]
    if first_nonzero_perf.empty:
        return [], {}
    portfolio_return = (perf.iloc[-1] / first_nonzero_perf.iloc[0] - 1) * 100

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
