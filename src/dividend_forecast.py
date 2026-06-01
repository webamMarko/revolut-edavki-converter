"""Dividend calendar and income forecasting based on historical payout patterns."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class DividendEvent:
    ticker: str
    ex_date: str
    amount_per_share: float
    currency: str
    shares_held: float
    projected_income_eur: float
    frequency: str | None
    is_projected: bool


@dataclass
class DividendForecast:
    upcoming_events: list[DividendEvent]
    projected_annual_income_eur: float
    projected_monthly_income_eur: float
    monthly_breakdown: dict[str, float]
    by_ticker: list[dict]
    yield_on_cost: float | None
    dividend_changes: list[dict]


def _get_held_positions(conn: sqlite3.Connection, portfolio_id: int | None = None) -> dict[str, float]:
    """Get current share count per ticker using FIFO from transactions."""
    if portfolio_id:
        rows = conn.execute("""
            SELECT ticker, type, quantity FROM transactions
            WHERE ticker IS NOT NULL AND asset_class = 'stock'
              AND type IN ('BUY', 'SELL', 'STOCK SPLIT')
              AND portfolio_id = ?
            ORDER BY date, id
        """, (portfolio_id,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT ticker, type, quantity FROM transactions
            WHERE ticker IS NOT NULL AND asset_class = 'stock'
              AND type IN ('BUY', 'SELL', 'STOCK SPLIT')
            ORDER BY date, id
        """).fetchall()

    holdings: dict[str, float] = {}
    for row in rows:
        ticker = row["ticker"]
        qty = row["quantity"] or 0
        if row["type"] == "BUY":
            holdings[ticker] = holdings.get(ticker, 0) + qty
        elif row["type"] == "SELL":
            holdings[ticker] = holdings.get(ticker, 0) - qty
        elif row["type"] == "STOCK SPLIT":
            holdings[ticker] = holdings.get(ticker, 0) + qty

    return {t: q for t, q in holdings.items() if q > 0.001}


def _get_latest_fx_rate(conn: sqlite3.Connection) -> float:
    """Get most recent EUR/USD rate."""
    row = conn.execute("SELECT rate FROM fx_rates WHERE from_currency = 'USD' AND to_currency = 'EUR' ORDER BY date DESC LIMIT 1").fetchone()
    return row[0] if row else 0.91


def _project_next_dates(historical_dates: list[str], frequency: str | None,
                        horizon_days: int = 365) -> list[str]:
    """Project future ex-dividend dates based on historical pattern."""
    if not historical_dates:
        return []

    dates = sorted(datetime.fromisoformat(d) for d in historical_dates)
    today = datetime.now()
    horizon_end = today + timedelta(days=horizon_days)

    if len(dates) < 2:
        if frequency == "quarterly":
            gap = timedelta(days=91)
        elif frequency == "monthly":
            gap = timedelta(days=30)
        elif frequency == "semi-annual":
            gap = timedelta(days=182)
        else:
            gap = timedelta(days=365)
        projected = []
        next_date = dates[-1] + gap
        while next_date <= horizon_end:
            if next_date > today:
                projected.append(next_date.strftime("%Y-%m-%d"))
            next_date += gap
        return projected

    # Use last N gaps to estimate interval
    recent = dates[-8:] if len(dates) >= 8 else dates
    gaps = [(recent[i] - recent[i - 1]).days for i in range(1, len(recent))]
    avg_gap = sum(gaps) / len(gaps) if gaps else 365

    projected = []
    next_date = dates[-1] + timedelta(days=avg_gap)
    while next_date <= horizon_end:
        if next_date > today:
            projected.append(next_date.strftime("%Y-%m-%d"))
        next_date += timedelta(days=avg_gap)

    return projected


def _detect_dividend_changes(conn: sqlite3.Connection, ticker: str) -> dict | None:
    """Detect if the most recent dividend was a cut or increase vs prior."""
    rows = conn.execute(
        "SELECT amount, ex_date FROM dividend_schedule WHERE ticker = ? ORDER BY ex_date DESC LIMIT 5",
        (ticker,)
    ).fetchall()

    if len(rows) < 2:
        return None

    latest = rows[0]["amount"]
    previous = rows[1]["amount"]
    if previous == 0:
        return None

    pct_change = (latest - previous) / previous * 100
    if abs(pct_change) < 1:
        return None

    return {
        "ticker": ticker,
        "latest_amount": latest,
        "previous_amount": previous,
        "change_pct": round(pct_change, 1),
        "date": rows[0]["ex_date"],
        "type": "increase" if pct_change > 0 else "cut",
    }


def build_dividend_forecast(conn: sqlite3.Connection,
                            prices_conn: sqlite3.Connection | None = None,
                            portfolio_id: int | None = None) -> DividendForecast | None:
    """Build forward-looking dividend calendar and income projections."""
    holdings = _get_held_positions(conn, portfolio_id=portfolio_id)
    if not holdings:
        return None

    _pconn = prices_conn if prices_conn is not None else conn
    fx_rate = _get_latest_fx_rate(_pconn)

    if portfolio_id:
        tickers_with_divs = conn.execute(
            "SELECT DISTINCT ticker FROM dividend_schedule WHERE portfolio_id = ? AND ticker IN ({})".format(
                ",".join("?" for _ in holdings)
            ),
            [portfolio_id] + list(holdings.keys())
        ).fetchall()
    else:
        tickers_with_divs = conn.execute(
            "SELECT DISTINCT ticker FROM dividend_schedule WHERE ticker IN ({})".format(
                ",".join("?" for _ in holdings)
            ),
            list(holdings.keys())
        ).fetchall()
    div_tickers = {row[0] for row in tickers_with_divs}

    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    horizon_str = (today + timedelta(days=365)).strftime("%Y-%m-%d")

    upcoming_events: list[DividendEvent] = []
    annual_by_ticker: dict[str, float] = {}
    monthly_income: dict[str, float] = {}
    dividend_changes: list[dict] = []

    for ticker in sorted(holdings.keys()):
        shares = holdings[ticker]
        if ticker not in div_tickers:
            continue

        # Get historical schedule
        rows = conn.execute(
            "SELECT ex_date, amount, currency, frequency FROM dividend_schedule "
            "WHERE ticker = ? ORDER BY ex_date",
            (ticker,)
        ).fetchall()

        if not rows:
            continue

        historical_dates = [r["ex_date"] for r in rows]
        latest_amount = rows[-1]["amount"]
        currency = rows[-1]["currency"]
        frequency = rows[-1]["frequency"]

        # Confirmed upcoming (already in schedule, after today)
        for row in rows:
            if row["ex_date"] > today_str:
                amt_eur = row["amount"] * shares * fx_rate if currency != "EUR" else row["amount"] * shares
                event = DividendEvent(
                    ticker=ticker,
                    ex_date=row["ex_date"],
                    amount_per_share=row["amount"],
                    currency=currency,
                    shares_held=shares,
                    projected_income_eur=round(amt_eur, 2),
                    frequency=frequency,
                    is_projected=False,
                )
                upcoming_events.append(event)
                month_key = row["ex_date"][:7]
                monthly_income[month_key] = monthly_income.get(month_key, 0) + amt_eur

        # Project future dates
        projected_dates = _project_next_dates(historical_dates, frequency)
        for proj_date in projected_dates:
            if proj_date > horizon_str:
                break
            amt_eur = latest_amount * shares * fx_rate if currency != "EUR" else latest_amount * shares
            event = DividendEvent(
                ticker=ticker,
                ex_date=proj_date,
                amount_per_share=latest_amount,
                currency=currency,
                shares_held=shares,
                projected_income_eur=round(amt_eur, 2),
                frequency=frequency,
                is_projected=True,
            )
            upcoming_events.append(event)
            month_key = proj_date[:7]
            monthly_income[month_key] = monthly_income.get(month_key, 0) + amt_eur

        # Annual income estimate for this ticker
        if frequency == "monthly":
            annual_est = latest_amount * shares * 12
        elif frequency == "quarterly":
            annual_est = latest_amount * shares * 4
        elif frequency == "semi-annual":
            annual_est = latest_amount * shares * 2
        else:
            annual_est = latest_amount * shares

        annual_eur = annual_est * fx_rate if currency != "EUR" else annual_est
        annual_by_ticker[ticker] = round(annual_eur, 2)

        # Detect changes
        change = _detect_dividend_changes(conn, ticker)
        if change:
            dividend_changes.append(change)

    upcoming_events.sort(key=lambda e: e.ex_date)

    total_annual = sum(annual_by_ticker.values())
    total_monthly = total_annual / 12 if total_annual > 0 else 0

    # Yield on cost
    if portfolio_id:
        total_invested_row = conn.execute("""
            SELECT SUM(
                CASE WHEN fx_rate > 0 AND currency != 'EUR' THEN ABS(total_amount) / fx_rate
                     ELSE ABS(total_amount) END
            ) FROM transactions
            WHERE type = 'BUY' AND asset_class = 'stock' AND portfolio_id = ? AND ticker IN ({})
        """.format(",".join("?" for _ in holdings)), [portfolio_id] + list(holdings.keys())).fetchone()
    else:
        total_invested_row = conn.execute("""
            SELECT SUM(
                CASE WHEN fx_rate > 0 AND currency != 'EUR' THEN ABS(total_amount) / fx_rate
                     ELSE ABS(total_amount) END
            ) FROM transactions
            WHERE type = 'BUY' AND asset_class = 'stock' AND ticker IN ({})
        """.format(",".join("?" for _ in holdings)), list(holdings.keys())).fetchone()
    total_invested = total_invested_row[0] if total_invested_row and total_invested_row[0] else 0
    yield_on_cost = (total_annual / total_invested * 100) if total_invested > 0 else None

    by_ticker_list = [
        {"ticker": t, "annual_income_eur": v, "shares": holdings[t],
         "frequency": conn.execute(
             "SELECT frequency FROM dividend_schedule WHERE ticker = ? ORDER BY ex_date DESC LIMIT 1",
             (t,)).fetchone()[0]}
        for t, v in sorted(annual_by_ticker.items(), key=lambda x: -x[1])
    ]

    return DividendForecast(
        upcoming_events=upcoming_events[:50],
        projected_annual_income_eur=round(total_annual, 2),
        projected_monthly_income_eur=round(total_monthly, 2),
        monthly_breakdown={k: round(v, 2) for k, v in sorted(monthly_income.items())},
        by_ticker=by_ticker_list,
        yield_on_cost=round(yield_on_cost, 2) if yield_on_cost else None,
        dividend_changes=dividend_changes,
    )
