"""Close phantom crypto positions (dust) by inserting zero-profit SELL transactions.

Affected tickers: ETH, LTC, LINK, SAND — all should have 0 holdings but have
small residual quantities from daily auto-invest buys that weren't fully covered
by the final sell orders.

For each ticker, computes the FIFO cost basis of remaining shares and inserts
a SELL at that exact cost so profit/loss = 0.

Usage:
    python scripts/close_crypto_dust.py [--db PATH] [--dry-run]
"""

import argparse
import hashlib
import sqlite3
from collections import deque
from datetime import datetime

TICKERS = ["ETH", "LTC", "LINK", "SAND"]
BUY_TYPES = ("BUY", "Receive", "Staking reward", "Learn reward")
SELL_TYPES = ("SELL", "Payment")


def compute_residual(cur, ticker):
    rows = cur.execute(
        "SELECT date, type, quantity, price_per_share, currency, fx_rate "
        "FROM transactions WHERE ticker=? AND asset_class='crypto' ORDER BY date",
        (ticker,),
    ).fetchall()

    lots = deque()
    last_sell_date = None

    for r in rows:
        qty = r[2] or 0
        price = r[3] or 0
        fx = r[5] or 1.0
        currency = r[4] or "EUR"

        price_eur = price / fx if currency != "EUR" and fx > 0 else price

        if r[1] in BUY_TYPES:
            lots.append([qty, price_eur])
        elif r[1] in SELL_TYPES:
            last_sell_date = r[0]
            remaining = qty
            while remaining > 1e-12 and lots:
                if lots[0][0] <= remaining:
                    remaining -= lots[0][0]
                    lots.popleft()
                else:
                    lots[0][0] -= remaining
                    remaining = 0

    total_qty = sum(l[0] for l in lots)
    if total_qty < 1e-12:
        return None

    avg_cost_eur = sum(l[0] * l[1] for l in lots) / total_qty
    total_cost_eur = sum(l[0] * l[1] for l in lots)

    return {
        "ticker": ticker,
        "quantity": total_qty,
        "price_per_share": round(avg_cost_eur, 4),
        "total_amount": round(total_cost_eur, 4),
        "last_sell_date": last_sell_date,
    }


def make_row_hash(ticker, date, qty, price):
    raw = f"{ticker}|{date}|SELL|{qty}|{price}"
    return hashlib.sha256(raw.encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Close crypto dust positions")
    parser.add_argument("--db", default=None, help="Path to portfolio.db")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be inserted")
    args = parser.parse_args()

    import os
    db_path = args.db or os.path.expanduser("~/.revolut-edavki/portfolio.db")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    for ticker in TICKERS:
        res = compute_residual(cur, ticker)
        if not res:
            print(f"{ticker}: no residual, skipping")
            continue

        sell_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row_hash = make_row_hash(ticker, sell_date, res["quantity"], res["price_per_share"])

        print(
            f"{ticker}: closing {res['quantity']:.8f} @ €{res['price_per_share']:.4f} "
            f"= €{res['total_amount']:.4f} (zero profit)"
        )

        if args.dry_run:
            print("  [dry-run] would insert SELL transaction")
            continue

        cur.execute(
            """INSERT INTO transactions
               (date, ticker, type, quantity, price_per_share, total_amount,
                currency, fx_rate, asset_class, source_file, row_hash, portfolio_id)
               VALUES (?, ?, 'SELL', ?, ?, ?, 'EUR', 1.0, 'crypto', 'manual-dust-close', ?, 1)""",
            (sell_date, ticker, res["quantity"], res["price_per_share"],
             res["total_amount"], row_hash),
        )
        print(f"  inserted closing SELL (id={cur.lastrowid})")

    if not args.dry_run:
        conn.commit()
        print("\nCommitted.")
    else:
        print("\n[dry-run] No changes made.")

    conn.close()


if __name__ == "__main__":
    main()
