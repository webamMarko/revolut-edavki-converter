"""Shared price/FX database — single system-level store for all users."""

import os
import sqlite3
from pathlib import Path


PRICES_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS daily_prices (
    ticker   TEXT NOT NULL,
    date     TEXT NOT NULL,
    close    REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS fx_rates (
    date    TEXT NOT NULL PRIMARY KEY,
    eur_usd REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS metadata (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def _default_prices_db_path() -> Path:
    if "REVOLUT_DATA_DIR" in os.environ:
        base = Path(os.environ["REVOLUT_DATA_DIR"])
    else:
        project_data = Path(__file__).resolve().parent.parent / "data"
        if project_data.is_dir():
            base = project_data
        else:
            base = Path.home() / ".revolut-edavki"
    return base / "_system" / "prices.db"


def get_prices_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Open (or create) the shared prices database."""
    if db_path is not None:
        path = Path(db_path)
    elif "REVOLUT_PRICES_DB_PATH" in os.environ:
        path = Path(os.environ["REVOLUT_PRICES_DB_PATH"])
    else:
        path = _default_prices_db_path()

    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    conn.executescript(PRICES_SCHEMA_SQL)
    return conn


def get_prices_conn_or_none() -> sqlite3.Connection | None:
    """Try to open the shared prices DB; return None if unavailable or empty.

    Used by read-path code for backward-compatible fallback.
    """
    try:
        path = _default_prices_db_path()
        if "REVOLUT_PRICES_DB_PATH" in os.environ:
            path = Path(os.environ["REVOLUT_PRICES_DB_PATH"])
        if not path.exists():
            return None
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        has_data = conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
        if not has_data:
            conn.close()
            return None
        return conn
    except Exception:
        return None


def migrate_prices_from_user_db(user_conn: sqlite3.Connection,
                                prices_conn: sqlite3.Connection,
                                drop_from_user: bool = False) -> int:
    """Copy daily_prices and fx_rates from a user DB into the shared prices DB.

    Returns the number of rows migrated. Skips if shared DB already has data
    (idempotent — safe to call multiple times).
    """
    migrated = 0

    # Copy daily_prices
    try:
        rows = user_conn.execute(
            "SELECT ticker, date, close, currency FROM daily_prices"
        ).fetchall()
        if rows:
            prices_conn.executemany(
                "INSERT OR IGNORE INTO daily_prices (ticker, date, close, currency) VALUES (?, ?, ?, ?)",
                [(r[0], r[1], r[2], r[3]) for r in rows],
            )
            migrated += len(rows)
    except Exception:
        pass

    # Copy fx_rates
    try:
        rows = user_conn.execute("SELECT date, eur_usd FROM fx_rates").fetchall()
        if rows:
            prices_conn.executemany(
                "INSERT OR IGNORE INTO fx_rates (date, eur_usd) VALUES (?, ?)",
                [(r[0], r[1]) for r in rows],
            )
            migrated += len(rows)
    except Exception:
        pass

    # Copy delisted metadata
    try:
        rows = user_conn.execute(
            "SELECT key, value FROM metadata WHERE key LIKE 'delisted:%'"
        ).fetchall()
        if rows:
            prices_conn.executemany(
                "INSERT OR IGNORE INTO metadata (key, value) VALUES (?, ?)",
                [(r[0], r[1]) for r in rows],
            )
    except Exception:
        pass

    prices_conn.commit()

    if drop_from_user and migrated > 0:
        user_conn.execute("DELETE FROM daily_prices")
        user_conn.execute("DELETE FROM fx_rates")
        user_conn.commit()

    return migrated
