"""SQLite database layer for portfolio analytics."""

import sqlite3
from pathlib import Path

DB_DIR = Path.home() / ".revolut-edavki"
DB_PATH = DB_DIR / "portfolio.db"

SCHEMA_VERSION = 2

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,
    ticker          TEXT,
    type            TEXT NOT NULL,
    quantity        REAL,
    price_per_share REAL,
    total_amount    REAL,
    currency        TEXT NOT NULL,
    fx_rate         REAL NOT NULL DEFAULT 1.0,
    asset_class     TEXT NOT NULL DEFAULT 'stock',
    source_file     TEXT,
    imported_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, ticker, type, quantity, total_amount, currency)
);

CREATE INDEX IF NOT EXISTS idx_transactions_ticker ON transactions(ticker);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type);

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

CREATE TABLE IF NOT EXISTS import_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    filename     TEXT NOT NULL,
    file_hash    TEXT NOT NULL,
    rows_total   INTEGER NOT NULL,
    rows_new     INTEGER NOT NULL,
    rows_skipped INTEGER NOT NULL,
    imported_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS metadata (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def get_connection() -> sqlite3.Connection:
    """Get a database connection, creating the DB directory and schema if needed."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    _init_schema(conn)
    return conn


def _init_schema(conn: sqlite3.Connection):
    """Create tables if they don't exist and handle migrations."""
    conn.executescript(SCHEMA_SQL)

    row = conn.execute("SELECT value FROM metadata WHERE key = 'schema_version'").fetchone()
    current_version = int(row["value"]) if row else 0

    if current_version < 2:
        # Add asset_class column if missing (migration from v1)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(transactions)").fetchall()]
        if "asset_class" not in cols:
            conn.execute("ALTER TABLE transactions ADD COLUMN asset_class TEXT NOT NULL DEFAULT 'stock'")

    if current_version < SCHEMA_VERSION:
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),)
        )
        conn.commit()
