"""CSV import with deduplication for portfolio analytics."""

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class ImportResult:
    total: int
    new: int
    skipped: int


def _file_hash(file_path: str) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_amount(value) -> float | None:
    """Parse an amount string like 'USD 32' or '32' to float."""
    if pd.isna(value) or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    s = re.sub(r"^[A-Z]{3}\s+", "", s)
    try:
        return float(s)
    except ValueError:
        return None


def import_csv(conn: sqlite3.Connection, file_path: str, verbose: bool = False) -> ImportResult:
    """Import a Revolut CSV/Excel file into the database with deduplication."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    # Check file-level dedup
    fhash = _file_hash(file_path)
    existing = conn.execute(
        "SELECT id FROM import_log WHERE file_hash = ?", (fhash,)
    ).fetchone()
    if existing:
        if verbose:
            print(f"File already imported (SHA-256 match): {path.name}")
        return ImportResult(total=0, new=0, skipped=0)

    # Parse file
    suffix = path.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(path)
    elif suffix in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        raise ValueError(f"Unsupported file format: {suffix}")

    total = len(df)
    new = 0
    skipped = 0

    for _, row in df.iterrows():
        date = row.get("Date") or row.get("Started Date", "")
        if pd.isna(date) or not date:
            skipped += 1
            continue

        ticker = row.get("Ticker", None)
        if pd.isna(ticker):
            ticker = None

        tx_type = row.get("Type", "")
        if pd.isna(tx_type) or not tx_type:
            skipped += 1
            continue

        quantity = _parse_amount(row.get("Quantity"))
        price_per_share = _parse_amount(row.get("Price per share"))
        total_amount = _parse_amount(row.get("Total Amount") or row.get("Amount"))
        currency = row.get("Currency", "USD")
        if pd.isna(currency):
            currency = "USD"

        fx_rate_raw = row.get("FX Rate", 1.0)
        fx_rate = float(fx_rate_raw) if not pd.isna(fx_rate_raw) else 1.0

        try:
            conn.execute(
                """INSERT OR IGNORE INTO transactions
                   (date, ticker, type, quantity, price_per_share, total_amount,
                    currency, fx_rate, source_file)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(date), ticker, str(tx_type), quantity, price_per_share,
                 total_amount, str(currency), fx_rate, path.name),
            )
            if conn.execute("SELECT changes()").fetchone()[0] > 0:
                new += 1
            else:
                skipped += 1
        except sqlite3.Error:
            skipped += 1

    # Log the import
    conn.execute(
        """INSERT INTO import_log (filename, file_hash, rows_total, rows_new, rows_skipped)
           VALUES (?, ?, ?, ?, ?)""",
        (path.name, fhash, total, new, total - new),
    )
    conn.commit()

    return ImportResult(total=total, new=new, skipped=total - new)
