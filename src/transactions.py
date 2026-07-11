"""Manual transaction validation and audit logging."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date

ALLOWED_TYPES: dict[str, set[str]] = {
    'stock':   {'BUY', 'SELL', 'DIVIDEND', 'STOCK SPLIT'},
    'cfd':     {'BUY', 'SELL'},
    'crypto':  {'BUY', 'SELL', 'Staking reward'},
    'savings': {'BUY', 'SELL', 'Interest PAID'},
}

ASSET_CLASSES = frozenset(ALLOWED_TYPES)

_TICKER_RE = re.compile(r'^[A-Z0-9][A-Z0-9.]*$')
_SPLIT_RATIO_RE = re.compile(r'^(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)$')


def parse_split_ratio(raw) -> float | None:
    """Parse split ratio string ('4:1', '4', '3.5:1') → float or None on error."""
    s = str(raw).strip()
    m = _SPLIT_RATIO_RE.match(s)
    if m:
        try:
            num = float(m.group(1))
            den = float(m.group(2))
            return num / den if den != 0 else None
        except (ValueError, ZeroDivisionError):
            return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def get_held_shares(conn: sqlite3.Connection, ticker: str, asset_class: str,
                    portfolio_id: int, as_of_date: str, *,
                    exclude_id: int | None = None) -> float:
    """Return net shares held for ticker as of a date (BUY - SELL + SPLITS)."""
    exclude_clause = "AND id != ?" if exclude_id is not None else ""
    params: list = [ticker, asset_class, portfolio_id, as_of_date]
    if exclude_id is not None:
        params.append(exclude_id)
    row = conn.execute(
        f"""
        SELECT
          COALESCE(SUM(CASE WHEN type = 'BUY' THEN quantity ELSE 0 END), 0) -
          COALESCE(SUM(CASE WHEN type = 'SELL' THEN quantity ELSE 0 END), 0) +
          COALESCE(SUM(CASE WHEN type = 'STOCK SPLIT' THEN quantity ELSE 0 END), 0)
        FROM transactions
        WHERE UPPER(ticker) = UPPER(?) AND asset_class = ? AND portfolio_id = ?
          AND date <= ? {exclude_clause}
        """,
        params,
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


def validate_transaction(data: dict, asset_class: str) -> tuple[dict, dict]:
    """Validate manual transaction data.

    Returns (clean_data, errors). errors is empty on success.
    """
    errors: dict[str, str] = {}
    clean: dict = {}

    # asset_class
    if asset_class not in ASSET_CLASSES:
        errors['asset_class'] = f"Must be one of: {', '.join(sorted(ASSET_CLASSES))}"
    else:
        clean['asset_class'] = asset_class

    # date: required, ISO format, not in future
    raw_date = str(data.get('date') or '').strip()
    if not raw_date:
        errors['date'] = 'Required'
    else:
        try:
            parsed = date.fromisoformat(raw_date)
            if parsed > date.today():
                errors['date'] = 'Cannot be in the future'
            else:
                clean['date'] = str(parsed)
        except ValueError:
            errors['date'] = 'Must be ISO format (YYYY-MM-DD)'

    # ticker: required, uppercase alphanumeric + dots
    raw_ticker = str(data.get('ticker') or '').strip().upper()
    if not raw_ticker:
        errors['ticker'] = 'Required'
    elif not _TICKER_RE.match(raw_ticker):
        errors['ticker'] = 'Uppercase alphanumeric and dots only'
    else:
        clean['ticker'] = raw_ticker

    # type: must be in allowed list per asset_class
    raw_type = str(data.get('type') or '').strip()
    if not raw_type:
        errors['type'] = 'Required'
    elif asset_class in ALLOWED_TYPES and raw_type not in ALLOWED_TYPES[asset_class]:
        allowed = ', '.join(sorted(ALLOWED_TYPES[asset_class]))
        errors['type'] = f"Must be one of: {allowed}"
    else:
        clean['type'] = raw_type

    tx_type = clean.get('type', raw_type)

    if tx_type == 'STOCK SPLIT':
        # split_ratio: required, must parse to > 1
        raw_ratio = data.get('split_ratio')
        if raw_ratio is None or str(raw_ratio).strip() == '':
            errors['split_ratio'] = 'Required for STOCK SPLIT (e.g. 4:1)'
        else:
            ratio = parse_split_ratio(raw_ratio)
            if ratio is None:
                errors['split_ratio'] = 'Must be a valid ratio (e.g. 4:1)'
            elif ratio <= 1.0:
                errors['split_ratio'] = 'Must be > 1'
            else:
                clean['split_ratio'] = ratio
    else:
        # quantity: required for BUY/SELL, > 0
        raw_qty = data.get('quantity')
        if tx_type in ('BUY', 'SELL'):
            if raw_qty is None or raw_qty == '':
                errors['quantity'] = 'Required for BUY/SELL'
            else:
                try:
                    qty = float(raw_qty)
                    if qty <= 0:
                        errors['quantity'] = 'Must be > 0'
                    else:
                        clean['quantity'] = qty
                except (ValueError, TypeError):
                    errors['quantity'] = 'Must be a number'
        elif raw_qty is not None and raw_qty != '':
            try:
                clean['quantity'] = float(raw_qty)
            except (ValueError, TypeError):
                errors['quantity'] = 'Must be a number'

        # price_per_share: required for BUY/SELL, >= 0
        raw_price = data.get('price_per_share')
        if tx_type in ('BUY', 'SELL'):
            if raw_price is None or raw_price == '':
                errors['price_per_share'] = 'Required for BUY/SELL'
            else:
                try:
                    price = float(raw_price)
                    if price < 0:
                        errors['price_per_share'] = 'Must be >= 0'
                    else:
                        clean['price_per_share'] = price
                except (ValueError, TypeError):
                    errors['price_per_share'] = 'Must be a number'
        elif raw_price is not None and raw_price != '':
            try:
                clean['price_per_share'] = float(raw_price)
            except (ValueError, TypeError):
                errors['price_per_share'] = 'Must be a number'

    # currency (default EUR)
    currency = str(data.get('currency') or 'EUR').strip().upper()
    if not currency:
        currency = 'EUR'
    clean['currency'] = currency

    # fx_rate: required when currency != 'EUR', > 0
    raw_fx = data.get('fx_rate')
    if currency != 'EUR':
        if raw_fx is None or raw_fx == '':
            errors['fx_rate'] = 'Required when currency is not EUR'
        else:
            try:
                fx = float(raw_fx)
                if fx <= 0:
                    errors['fx_rate'] = 'Must be > 0'
                else:
                    clean['fx_rate'] = fx
            except (ValueError, TypeError):
                errors['fx_rate'] = 'Must be a number'
    else:
        clean['fx_rate'] = 1.0
        if raw_fx is not None and raw_fx != '':
            try:
                clean['fx_rate'] = float(raw_fx)
            except (ValueError, TypeError):
                pass

    # optional numeric fields
    for field in ('total_amount', 'commission', 'withholding_tax'):
        raw = data.get(field)
        if raw is not None and raw != '':
            try:
                clean[field] = float(raw)
            except (ValueError, TypeError):
                errors[field] = 'Must be a number'

    return clean, errors


# ------------------------------------------------------------------
# Audit helpers
# ------------------------------------------------------------------

def _audit(conn: sqlite3.Connection, transaction_id: int, action: str,
           field_name: str | None = None,
           old_value: str | None = None,
           new_value: str | None = None):
    conn.execute(
        "INSERT INTO transaction_audit (transaction_id, action, field_name, old_value, new_value) "
        "VALUES (?, ?, ?, ?, ?)",
        (transaction_id, action, field_name, old_value, new_value),
    )


def create_manual_transaction(conn: sqlite3.Connection, clean: dict,
                               portfolio_id: int = 1) -> dict:
    """Insert a validated manual transaction and write a 'create' audit entry.

    Returns the newly-created transaction as a dict.
    """
    cursor = conn.execute(
        """
        INSERT INTO transactions
            (date, ticker, type, quantity, price_per_share, total_amount,
             currency, fx_rate, asset_class, commission, withholding_tax,
             broker_source, source_file, portfolio_id)
        VALUES
            (:date, :ticker, :type, :quantity, :price_per_share, :total_amount,
             :currency, :fx_rate, :asset_class, :commission, :withholding_tax,
             'manual', NULL, :portfolio_id)
        """,
        {
            'date':            clean['date'],
            'ticker':          clean.get('ticker'),
            'type':            clean['type'],
            'quantity':        clean.get('quantity'),
            'price_per_share': clean.get('price_per_share'),
            'total_amount':    clean.get('total_amount'),
            'currency':        clean['currency'],
            'fx_rate':         clean.get('fx_rate', 1.0),
            'asset_class':     clean['asset_class'],
            'commission':      clean.get('commission'),
            'withholding_tax': clean.get('withholding_tax'),
            'portfolio_id':    portfolio_id,
        }
    )
    tx_id = cursor.lastrowid
    row = conn.execute(
        "SELECT * FROM transactions WHERE id = ?", (tx_id,)
    ).fetchone()
    row_dict = dict(row)
    _audit(conn, tx_id, 'create', new_value=json.dumps(row_dict, default=str))
    conn.commit()
    return row_dict


_UPDATABLE = {
    'date', 'ticker', 'type', 'quantity', 'price_per_share', 'total_amount',
    'currency', 'fx_rate', 'commission', 'withholding_tax',
}


def update_manual_transaction(conn: sqlite3.Connection, tx_id: int,
                               fields: dict, portfolio_id: int = 1) -> dict | None:
    """Partial-update a manual transaction; one audit row per changed field.

    Returns updated row dict, or None if not found / not owned by portfolio.
    """
    old_row = conn.execute(
        "SELECT * FROM transactions WHERE id = ? AND portfolio_id = ? AND broker_source = 'manual'",
        (tx_id, portfolio_id)
    ).fetchone()
    if old_row is None:
        return None

    old = dict(old_row)
    updates = {}
    for k, v in fields.items():
        if k not in _UPDATABLE:
            continue
        try:
            if k in ('quantity', 'price_per_share', 'total_amount', 'fx_rate',
                     'commission', 'withholding_tax'):
                v = float(v) if v is not None else None
            else:
                v = str(v) if v is not None else None
        except (ValueError, TypeError):
            continue
        if str(old.get(k)) != str(v):
            updates[k] = v

    if not updates:
        return old

    set_clause = ', '.join(f"{k} = ?" for k in updates)
    conn.execute(
        f"UPDATE transactions SET {set_clause} WHERE id = ?",
        [*updates.values(), tx_id]
    )
    for field, new_val in updates.items():
        _audit(conn, tx_id, 'update', field_name=field,
               old_value=str(old.get(field)), new_value=str(new_val))
    conn.commit()

    return dict(conn.execute(
        "SELECT * FROM transactions WHERE id = ?", (tx_id,)
    ).fetchone())


def delete_manual_transaction(conn: sqlite3.Connection, tx_id: int,
                               portfolio_id: int = 1) -> bool:
    """Delete a manual transaction; audit 'delete' with full row snapshot.

    Returns True if deleted, False if not found.
    """
    row = conn.execute(
        "SELECT * FROM transactions WHERE id = ? AND portfolio_id = ? AND broker_source = 'manual'",
        (tx_id, portfolio_id)
    ).fetchone()
    if row is None:
        return False

    _audit(conn, tx_id, 'delete', old_value=json.dumps(dict(row), default=str))
    conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    conn.commit()
    return True


def get_transaction(conn: sqlite3.Connection, tx_id: int,
                    portfolio_id: int = 1) -> dict | None:
    row = conn.execute(
        "SELECT * FROM transactions WHERE id = ? AND portfolio_id = ?",
        (tx_id, portfolio_id)
    ).fetchone()
    return dict(row) if row else None


def list_transactions(conn: sqlite3.Connection, portfolio_id: int = 1,
                      ticker: str | None = None,
                      asset_class: str | None = None,
                      tx_type: str | None = None,
                      date_from: str | None = None,
                      date_to: str | None = None,
                      page: int = 1, per_page: int = 50) -> dict:
    """List transactions with optional filters and pagination."""
    per_page = min(max(1, per_page), 200)
    page = max(1, page)
    offset = (page - 1) * per_page

    where = ["portfolio_id = ?"]
    params: list = [portfolio_id]

    if ticker:
        where.append("UPPER(ticker) = UPPER(?)")
        params.append(ticker)
    if asset_class:
        where.append("asset_class = ?")
        params.append(asset_class)
    if tx_type:
        where.append("type = ?")
        params.append(tx_type)
    if date_from:
        where.append("date >= ?")
        params.append(date_from)
    if date_to:
        where.append("date <= ?")
        params.append(date_to)

    where_sql = " AND ".join(where)
    total = conn.execute(
        f"SELECT COUNT(*) FROM transactions WHERE {where_sql}", params
    ).fetchone()[0]

    rows = conn.execute(
        f"SELECT * FROM transactions WHERE {where_sql} ORDER BY date DESC, id DESC LIMIT ? OFFSET ?",
        [*params, per_page, offset]
    ).fetchall()

    return {
        'transactions': [dict(r) for r in rows],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page if total else 0,
    }
