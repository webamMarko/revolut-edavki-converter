"""CSV/XML import with deduplication for portfolio analytics.

The import pipeline is now plugin-based:
  BrokerRegistry.detect_and_parse(file) -> list[ParsedTrade]
  -> validate, deduplicate, insert into DB

All broker-specific parsing logic lives in src/parsers/*.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .db import transaction_row_hash
from .parsers.base import ParsedTrade, UnknownFormatError
from .parsers.default_registry import build_default_registry

# Re-export utilities still used by external callers
from .parsers.utils import (
    _parse_amount,
    _parse_eur_amount,
    _parse_crypto_date,
    _file_hash,
)


@dataclass
class ImportResult:
    total: int
    new: int
    skipped: int
    warnings: list = None
    skipped_types: list = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
        if self.skipped_types is None:
            self.skipped_types = []


# Asset classes that are stored with their own asset_class value
_BROKER_ASSET_CLASS = {
    "revolut_stock":  "stock",
    "revolut_cfd":    "cfd",
    "revolut_crypto": "crypto",
    "revolut_savings": "savings",
    "ilirika":        "stock",
    "ibkr":           "stock",
    "trading212":     "stock",
    "degiro":         "stock",
}


def _insert_trade(conn: sqlite3.Connection, trade: ParsedTrade, source_file: str,
                  portfolio_id: int | None) -> bool:
    """Insert a ParsedTrade into the transactions table. Returns True if inserted (new row)."""
    rh = transaction_row_hash(
        trade.date, trade.ticker, trade.type,
        trade.quantity, trade.total_amount, trade.currency,
    )

    params = (
        trade.date, trade.ticker, trade.type,
        trade.quantity, trade.price_per_share, trade.total_amount,
        trade.currency, trade.fx_rate, trade.asset_class,
        trade.commission, trade.withholding_tax, trade.broker_source,
        trade.correlation_id, source_file, rh,
    )

    if portfolio_id is not None:
        conn.execute(
            """INSERT OR IGNORE INTO transactions
               (date, ticker, type, quantity, price_per_share, total_amount,
                currency, fx_rate, asset_class,
                commission, withholding_tax, broker_source, correlation_id,
                source_file, row_hash, portfolio_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            params + (portfolio_id,),
        )
    else:
        conn.execute(
            """INSERT OR IGNORE INTO transactions
               (date, ticker, type, quantity, price_per_share, total_amount,
                currency, fx_rate, asset_class,
                commission, withholding_tax, broker_source, correlation_id,
                source_file, row_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            params,
        )

    return conn.execute("SELECT changes()").fetchone()[0] > 0


def import_csv(conn: sqlite3.Connection, file_path: str, verbose: bool = False,
               portfolio_id: int | None = None) -> ImportResult:
    """Import a broker CSV/XML file into the database with deduplication.

    Auto-detects the broker format via BrokerRegistry. Supports all registered
    adapters: Revolut (stock/CFD/crypto/savings), Ilirika, IBKR, Trading 212, Degiro.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    fhash = _file_hash(file_path)

    # File-level dedup check
    existing = conn.execute(
        "SELECT id FROM import_log WHERE file_hash = ?", (fhash,)
    ).fetchone()
    if existing:
        if verbose:
            print(f"File already imported (SHA-256 match): {path.name}")
        return ImportResult(total=0, new=0, skipped=0)

    # Parse
    registry = build_default_registry()
    try:
        trades = registry.detect_and_parse(file_path)
    except UnknownFormatError as exc:
        raise ValueError(str(exc)) from exc

    total = len(trades)

    if verbose and trades:
        broker = trades[0].broker_source or "unknown"
        print(f"  Detected format: {broker} ({total} rows)")

    new = 0
    skipped = 0
    warnings = []
    dup_count = 0
    failed_count = 0

    for trade in trades:
        try:
            inserted = _insert_trade(conn, trade, path.name, portfolio_id)
            if inserted:
                new += 1
            else:
                skipped += 1
                dup_count += 1
        except sqlite3.Error as exc:
            skipped += 1
            failed_count += 1
            if failed_count <= 5:
                warnings.append(f"DB error inserting row: {exc}")

    if failed_count > 5:
        warnings.append(f"...and {failed_count - 5} more DB errors")
    if dup_count > 0:
        warnings.append(f"{dup_count} duplicate rows skipped")

    # Log the import
    if portfolio_id is not None:
        conn.execute(
            """INSERT INTO import_log (filename, file_hash, rows_total, rows_new, rows_skipped, portfolio_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (path.name, fhash, total, new, total - new, portfolio_id),
        )
    else:
        conn.execute(
            """INSERT INTO import_log (filename, file_hash, rows_total, rows_new, rows_skipped)
               VALUES (?, ?, ?, ?, ?)""",
            (path.name, fhash, total, new, total - new),
        )
    conn.commit()

    return ImportResult(total=total, new=new, skipped=total - new, warnings=warnings)


def import_csv_mapped(
    conn: sqlite3.Connection,
    file_path: str,
    asset_class: str,
    column_map: dict,
    filename_hint: str = "",
    verbose: bool = False,
    portfolio_id: int | None = None,
) -> ImportResult:
    """Import a CSV using an explicit user-supplied column mapping.

    This path bypasses the BrokerRegistry and is used for custom CSV mappings
    via the web UI column mapper.

    asset_class: "stock" | "cfd" | "crypto" | "savings"
    column_map: {db_field: csv_header_name}
    """
    import pandas as pd

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    fhash = _file_hash(file_path)

    df = pd.read_csv(path)
    if len(df.columns) == 1 or (len(df.columns) < 3 and ";" in df.columns[0]):
        df = pd.read_csv(path, sep=";")

    total = len(df)

    existing = conn.execute(
        "SELECT id FROM import_log WHERE file_hash = ?", (fhash,)
    ).fetchone()
    if existing:
        if verbose:
            print(f"File already imported (SHA-256 match): {filename_hint or path.name}")
        return ImportResult(total=total, new=0, skipped=total)

    new = 0
    skipped = 0

    for _, row in df.iterrows():
        parsed = _apply_map(row, column_map, asset_class)
        if parsed is None:
            skipped += 1
            continue

        trade = ParsedTrade(
            date=parsed["date"],
            ticker=parsed["ticker"],
            type=parsed["type"],
            quantity=parsed["quantity"],
            price_per_share=parsed["price_per_share"],
            total_amount=parsed["total_amount"],
            currency=parsed["currency"],
            fx_rate=parsed["fx_rate"],
            asset_class=asset_class,
        )

        try:
            inserted = _insert_trade(conn, trade, filename_hint or path.name, portfolio_id)
            if inserted:
                new += 1
            else:
                skipped += 1
        except sqlite3.Error:
            skipped += 1

    display_name = filename_hint or path.name
    if portfolio_id is not None:
        conn.execute(
            """INSERT INTO import_log (filename, file_hash, rows_total, rows_new, rows_skipped, portfolio_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (display_name, fhash, total, new, total - new, portfolio_id),
        )
    else:
        conn.execute(
            """INSERT INTO import_log (filename, file_hash, rows_total, rows_new, rows_skipped)
               VALUES (?, ?, ?, ?, ?)""",
            (display_name, fhash, total, new, total - new),
        )
    conn.commit()

    return ImportResult(total=total, new=new, skipped=total - new)


def _apply_map(row, column_map: dict, asset_class: str) -> dict | None:
    """Map a raw CSV row to a transaction dict using the user-supplied column mapping."""
    import pandas as pd

    def get(field):
        header = column_map.get(field)
        if not header:
            return None
        val = row.get(header)
        if pd.isna(val) if not isinstance(val, str) else (not val):
            return None
        return val

    raw_date = get("date")
    if not raw_date:
        return None
    if asset_class == "crypto":
        date = _parse_crypto_date(str(raw_date))
    else:
        date = str(raw_date)
    if not date:
        return None

    raw_type = get("type")
    if not raw_type:
        return None
    tx_type = str(raw_type)

    raw_ticker = get("ticker")
    ticker = str(raw_ticker) if raw_ticker is not None else None

    raw_qty = get("quantity")
    quantity = _parse_amount(raw_qty) if raw_qty is not None else None

    raw_pps = get("price_per_share")
    if raw_pps is not None:
        price_per_share = (
            _parse_eur_amount(raw_pps)
            if asset_class in ("crypto", "savings")
            else _parse_amount(raw_pps)
        )
    else:
        price_per_share = None

    raw_total = get("total_amount")
    if raw_total is not None:
        total_amount = (
            _parse_eur_amount(raw_total)
            if asset_class in ("crypto", "savings")
            else _parse_amount(raw_total)
        )
    else:
        total_amount = None

    raw_currency = get("currency")
    currency = str(raw_currency) if raw_currency is not None else (
        "EUR" if asset_class in ("crypto", "savings") else "USD"
    )

    raw_fx = get("fx_rate")
    try:
        fx_rate = float(raw_fx) if raw_fx is not None else 1.0
    except (ValueError, TypeError):
        fx_rate = 1.0

    return {
        "date": date,
        "ticker": ticker,
        "type": tx_type,
        "quantity": quantity,
        "price_per_share": price_per_share,
        "total_amount": total_amount,
        "currency": currency,
        "fx_rate": fx_rate,
    }


# Legacy compatibility: _detect_asset_class still needed by import_validator
def _detect_asset_class(df) -> str:
    """Detect broker/asset class from DataFrame column headers.

    Kept for backward-compatibility with import_validator.py.
    New code should use BrokerRegistry instead.
    """
    from .parsers.default_registry import build_default_registry as _build
    reg = _build()
    for adapter in reg.csv_adapters:
        if adapter.detect(df):
            return adapter.broker_name
    return "stock"
