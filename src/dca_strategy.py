"""DCA Strategy Tracker — detects dollar-cost-averaging patterns and compares vs lump-sum."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime
from statistics import median


def compute_dca_analysis(conn: sqlite3.Connection,
                         prices_conn: sqlite3.Connection | None = None) -> dict | None:
    """Detect DCA patterns and compute per-ticker DCA metrics.

    Returns None if no DCA patterns are found (fewer than 3 regular purchases).
    """
    if conn is None:
        return None

    _pconn = prices_conn if prices_conn is not None else conn

    buys = conn.execute("""
        SELECT date, ticker, quantity, price_per_share, total_amount, fx_rate, currency
        FROM transactions
        WHERE type IN ('BUY', 'BUY - MARKET') AND ticker IS NOT NULL AND quantity > 0
          AND asset_class IN ('stock', 'crypto')
        ORDER BY ticker, date
    """).fetchall()

    if not buys:
        return None

    by_ticker = defaultdict(list)
    for row in buys:
        by_ticker[row[1]].append({
            "date": row[0][:10],
            "quantity": row[2],
            "price_per_share": row[3],
            "total_amount": row[4],
            "fx_rate": row[5],
            "currency": row[6],
        })

    results = []
    for ticker, purchases in by_ticker.items():
        if len(purchases) < 3:
            continue

        analysis = _analyze_ticker_dca(ticker, purchases, _pconn)
        if analysis:
            results.append(analysis)

    if not results:
        return None

    results.sort(key=lambda x: x["consistency_score"], reverse=True)
    return {"tickers": results}


def _analyze_ticker_dca(ticker: str, purchases: list[dict],
                        prices_conn: sqlite3.Connection) -> dict | None:
    """Analyze DCA pattern for a single ticker."""
    dates = [datetime.strptime(p["date"], "%Y-%m-%d") for p in purchases]

    intervals = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
    if not intervals:
        return None

    med_interval = median(intervals)
    if med_interval < 7 or med_interval > 120:
        return None

    consistency_score = _compute_consistency(intervals, med_interval)
    if consistency_score < 30:
        return None

    amounts_eur = []
    for p in purchases:
        amt = abs(p["total_amount"]) if p["total_amount"] else 0
        if p["currency"] != "EUR" and p["fx_rate"] and p["fx_rate"] > 0:
            amt = amt / p["fx_rate"]
        amounts_eur.append(amt)

    total_invested_eur = sum(amounts_eur)
    total_shares = sum(p["quantity"] for p in purchases)
    avg_cost_eur = total_invested_eur / total_shares if total_shares > 0 else 0

    current_price_eur = _get_current_price_eur(ticker, prices_conn)
    if current_price_eur is None or current_price_eur <= 0:
        last_purchase = purchases[-1]
        price = last_purchase["price_per_share"] or 0
        fx = last_purchase["fx_rate"] or 1
        if last_purchase["currency"] != "EUR" and fx > 0:
            current_price_eur = price / fx
        else:
            current_price_eur = price

    dca_value_eur = total_shares * current_price_eur
    dca_return_pct = ((dca_value_eur / total_invested_eur) - 1) * 100 if total_invested_eur > 0 else 0

    lump_sum = _compute_lump_sum_comparison(
        ticker, purchases, total_invested_eur, current_price_eur, prices_conn
    )

    optimal_day = _compute_optimal_day(purchases)

    purchase_history = [
        {
            "date": p["date"],
            "amount_eur": round(amounts_eur[i], 2),
            "price_eur": round(
                (p["price_per_share"] / p["fx_rate"]) if p["currency"] != "EUR" and p["fx_rate"] and p["fx_rate"] > 0
                else (p["price_per_share"] or 0), 4
            ),
            "shares": round(p["quantity"], 4),
        }
        for i, p in enumerate(purchases)
    ]

    cumulative_avg = []
    running_cost = 0.0
    running_shares = 0.0
    for i, p in enumerate(purchase_history):
        running_cost += p["amount_eur"]
        running_shares += p["shares"]
        cumulative_avg.append(round(running_cost / running_shares, 4) if running_shares > 0 else 0)

    freq_label = _interval_label(med_interval)

    return {
        "ticker": ticker,
        "purchase_count": len(purchases),
        "first_purchase": purchases[0]["date"],
        "last_purchase": purchases[-1]["date"],
        "frequency": freq_label,
        "median_interval_days": round(med_interval, 1),
        "consistency_score": round(consistency_score, 1),
        "total_invested_eur": round(total_invested_eur, 2),
        "total_shares": round(total_shares, 4),
        "avg_cost_eur": round(avg_cost_eur, 4),
        "current_price_eur": round(current_price_eur, 4),
        "dca_value_eur": round(dca_value_eur, 2),
        "dca_return_eur": round(dca_value_eur - total_invested_eur, 2),
        "dca_return_pct": round(dca_return_pct, 2),
        "lump_sum": lump_sum,
        "optimal_day_of_month": optimal_day,
        "purchase_history": purchase_history,
        "cumulative_avg_cost": cumulative_avg,
    }


def _compute_consistency(intervals: list[int], med_interval: float) -> float:
    """Score 0-100 measuring how consistent the DCA schedule is.

    100 = perfectly regular intervals, 0 = completely random.
    """
    if len(intervals) < 2:
        return 100.0

    deviations = [abs(i - med_interval) / med_interval for i in intervals]
    avg_deviation = sum(deviations) / len(deviations)
    score = max(0, 100 * (1 - avg_deviation))
    return score


def _compute_lump_sum_comparison(ticker: str, purchases: list[dict],
                                 total_invested_eur: float,
                                 current_price_eur: float,
                                 prices_conn: sqlite3.Connection) -> dict:
    """Compare DCA outcome vs hypothetical lump-sum on day one."""
    first_date = purchases[0]["date"]

    first_price_eur = _get_price_on_date(ticker, first_date, prices_conn)
    if first_price_eur is None or first_price_eur <= 0:
        p = purchases[0]
        price = p["price_per_share"] or 0
        fx = p["fx_rate"] or 1
        if p["currency"] != "EUR" and fx > 0:
            first_price_eur = price / fx
        else:
            first_price_eur = price

    if first_price_eur <= 0:
        return {"value_eur": 0, "return_pct": 0, "dca_advantage_pct": 0}

    lump_shares = total_invested_eur / first_price_eur
    lump_value_eur = lump_shares * current_price_eur
    lump_return_pct = ((lump_value_eur / total_invested_eur) - 1) * 100 if total_invested_eur > 0 else 0

    dca_return_pct = ((sum(p["quantity"] for p in purchases) * current_price_eur / total_invested_eur) - 1) * 100 if total_invested_eur > 0 else 0
    dca_advantage_pct = dca_return_pct - lump_return_pct

    return {
        "value_eur": round(lump_value_eur, 2),
        "return_pct": round(lump_return_pct, 2),
        "dca_advantage_pct": round(dca_advantage_pct, 2),
    }


def _compute_optimal_day(purchases: list[dict]) -> int | None:
    """Find the day of month with historically lowest average price."""
    day_prices = defaultdict(list)
    for p in purchases:
        day = int(p["date"].split("-")[2])
        price = p["price_per_share"] or 0
        fx = p["fx_rate"] or 1
        if p["currency"] != "EUR" and fx > 0:
            price = price / fx
        day_prices[day].append(price)

    if not day_prices:
        return None

    avg_by_day = {day: sum(prices) / len(prices) for day, prices in day_prices.items()}
    return min(avg_by_day, key=avg_by_day.get)


def _get_current_price_eur(ticker: str, prices_conn: sqlite3.Connection) -> float | None:
    """Get the most recent price in EUR for a ticker."""
    row = prices_conn.execute("""
        SELECT dp.close, COALESCE(fx.rate, 1.0)
        FROM daily_prices dp
        LEFT JOIN fx_rates fx ON fx.date = dp.date
            AND fx.from_currency = dp.currency AND fx.to_currency = 'EUR'
        WHERE dp.ticker = ?
        ORDER BY dp.date DESC LIMIT 1
    """, (ticker,)).fetchone()

    if row and row[0]:
        return row[0] / row[1] if row[1] > 0 else row[0]
    return None


def _get_price_on_date(ticker: str, date: str, prices_conn: sqlite3.Connection) -> float | None:
    """Get price in EUR on a specific date (or nearest before)."""
    row = prices_conn.execute("""
        SELECT dp.close, COALESCE(fx.rate, 1.0)
        FROM daily_prices dp
        LEFT JOIN fx_rates fx ON fx.date = dp.date
            AND fx.from_currency = dp.currency AND fx.to_currency = 'EUR'
        WHERE dp.ticker = ? AND dp.date <= ?
        ORDER BY dp.date DESC LIMIT 1
    """, (ticker, date)).fetchone()

    if row and row[0]:
        return row[0] / row[1] if row[1] > 0 else row[0]
    return None


def _interval_label(days: float) -> str:
    """Convert median interval in days to a human-readable frequency label."""
    if days <= 10:
        return "Weekly"
    elif days <= 21:
        return "Bi-weekly"
    elif days <= 45:
        return "Monthly"
    elif days <= 75:
        return "Bi-monthly"
    elif days <= 120:
        return "Quarterly"
    return "Irregular"
