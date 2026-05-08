"""Investment notes CRUD for portfolio analytics."""

import sqlite3
from datetime import datetime


def add_note(
    conn: sqlite3.Connection,
    title: str,
    summary: str,
    body: str = "",
    tickers: str = "",
    conviction: str = "medium",
    action: str = "watch",
) -> int:
    """Insert a new investment note. Returns the new row id."""
    cur = conn.execute(
        """INSERT INTO investment_notes (title, summary, body, tickers, conviction, action)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (title, summary, body, tickers, conviction, action),
    )
    conn.commit()
    return cur.lastrowid


def list_notes(conn: sqlite3.Connection) -> list[dict]:
    """Return all notes ordered by newest first."""
    rows = conn.execute(
        "SELECT * FROM investment_notes ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_note(conn: sqlite3.Connection, note_id: int) -> dict | None:
    """Return a single note by id, or None if not found."""
    row = conn.execute(
        "SELECT * FROM investment_notes WHERE id = ?", (note_id,)
    ).fetchone()
    return dict(row) if row else None


def edit_note(conn: sqlite3.Connection, note_id: int, **kwargs) -> bool:
    """Update fields of an existing note. Returns True if a row was updated."""
    allowed = {"title", "summary", "body", "tickers", "conviction", "action"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return False
    updates["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [note_id]
    cur = conn.execute(
        f"UPDATE investment_notes SET {set_clause} WHERE id = ?", values
    )
    conn.commit()
    return cur.rowcount > 0


def delete_note(conn: sqlite3.Connection, note_id: int) -> bool:
    """Delete a note by id. Returns True if a row was deleted."""
    cur = conn.execute("DELETE FROM investment_notes WHERE id = ?", (note_id,))
    conn.commit()
    return cur.rowcount > 0


def query_notes_for_report(conn: sqlite3.Connection, prices_conn: sqlite3.Connection | None = None) -> list[dict]:
    """Return all notes enriched with live ticker data for the HTML report."""
    notes = list_notes(conn)
    if not notes:
        return []

    _pconn = prices_conn if prices_conn is not None else conn

    # Collect all unique tickers mentioned across notes
    all_tickers = set()
    for note in notes:
        for t in _parse_tickers(note["tickers"]):
            all_tickers.add(t)

    # Latest price per ticker
    prices: dict[str, dict] = {}
    for ticker in all_tickers:
        row = _pconn.execute(
            """SELECT close, currency, date FROM daily_prices
               WHERE ticker = ? ORDER BY date DESC LIMIT 1""",
            (ticker,),
        ).fetchone()
        if row:
            prices[ticker] = {"price": row[0], "currency": row[1], "date": row[2]}

    # Current positions (held tickers with cost basis)
    held: dict[str, dict] = {}
    for row in conn.execute(
        """SELECT ticker,
                  SUM(CASE WHEN type='BUY'  THEN quantity      ELSE -quantity     END) AS qty,
                  SUM(CASE WHEN type='BUY'  THEN total_amount  ELSE -total_amount END) AS cost
           FROM transactions
           WHERE ticker IS NOT NULL AND asset_class = 'stock'
           GROUP BY ticker
           HAVING qty > 0.0001"""
    ).fetchall():
        held[row["ticker"]] = {
            "quantity": round(row["qty"], 4),
            "cost_basis_eur": round(row["cost"] or 0, 2),
        }

    # Build enriched ticker objects
    ticker_info: dict[str, dict] = {}
    for ticker in all_tickers:
        info: dict = {"ticker": ticker}
        if ticker in prices:
            info.update(prices[ticker])
        if ticker in held:
            info["held"] = True
            info["quantity"] = held[ticker]["quantity"]
            info["cost_basis_eur"] = held[ticker]["cost_basis_eur"]
            qty = held[ticker]["quantity"]
            price = prices.get(ticker, {}).get("price")
            if price and qty:
                market_val = price * qty
                cost = held[ticker]["cost_basis_eur"]
                info["unrealized_gain_pct"] = round((market_val - cost) / cost * 100, 2) if cost else None
        else:
            info["held"] = False
        ticker_info[ticker] = info

    # Attach per-note ticker details
    result = []
    for note in notes:
        tickers_list = _parse_tickers(note["tickers"])
        result.append({
            **note,
            "ticker_details": [ticker_info[t] for t in tickers_list if t in ticker_info],
        })
    return result


def _parse_tickers(raw: str) -> list[str]:
    """Split comma/space-separated ticker string into a clean list."""
    if not raw:
        return []
    return [t.strip().upper() for t in raw.replace(",", " ").split() if t.strip()]
