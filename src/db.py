"""SQLite database layer for portfolio analytics."""

import hashlib
import sqlite3
from pathlib import Path

DB_DIR = Path.home() / ".revolut-edavki"
DB_PATH = DB_DIR / "portfolio.db"

SCHEMA_VERSION = 5

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
    row_hash        TEXT UNIQUE
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

CREATE TABLE IF NOT EXISTS real_estate_properties (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker                  TEXT NOT NULL UNIQUE,
    name                    TEXT NOT NULL,
    address                 TEXT,
    municipality            TEXT NOT NULL,
    cadastral_municipality  TEXT,
    property_type           TEXT NOT NULL,
    area_m2                 REAL NOT NULL,
    purchase_price_eur      REAL NOT NULL,
    purchase_date           TEXT NOT NULL,
    notes                   TEXT,
    created_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS investment_notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    summary     TEXT NOT NULL,
    body        TEXT NOT NULL DEFAULT '',
    tickers     TEXT NOT NULL DEFAULT '',
    conviction  TEXT NOT NULL DEFAULT 'medium' CHECK(conviction IN ('high','medium','low')),
    action      TEXT NOT NULL DEFAULT 'watch'  CHECK(action IN ('buy','watch','avoid','sell')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
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

    if current_version < 3:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS real_estate_properties (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker                  TEXT NOT NULL UNIQUE,
                name                    TEXT NOT NULL,
                address                 TEXT,
                municipality            TEXT NOT NULL,
                cadastral_municipality  TEXT,
                property_type           TEXT NOT NULL,
                area_m2                 REAL NOT NULL,
                purchase_price_eur      REAL NOT NULL,
                purchase_date           TEXT NOT NULL,
                notes                   TEXT,
                created_at              TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)

    if current_version < 4:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS investment_notes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                summary     TEXT NOT NULL,
                body        TEXT NOT NULL DEFAULT '',
                tickers     TEXT NOT NULL DEFAULT '',
                conviction  TEXT NOT NULL DEFAULT 'medium' CHECK(conviction IN ('high','medium','low')),
                action      TEXT NOT NULL DEFAULT 'watch'  CHECK(action IN ('buy','watch','avoid','sell')),
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)

    if current_version < 5:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(transactions)").fetchall()]
        if "row_hash" not in cols:
            conn.execute("ALTER TABLE transactions ADD COLUMN row_hash TEXT")

        # Remove duplicates created before row_hash existed (keep lowest id per group)
        conn.execute("""
            DELETE FROM transactions WHERE id NOT IN (
                SELECT MIN(id) FROM transactions
                GROUP BY date, COALESCE(ticker,''), type,
                         COALESCE(CAST(quantity AS TEXT),''),
                         COALESCE(CAST(total_amount AS TEXT),''),
                         currency
            )
        """)

        # Backfill row_hash for existing rows
        rows = conn.execute(
            "SELECT id, date, ticker, type, quantity, total_amount, currency "
            "FROM transactions WHERE row_hash IS NULL"
        ).fetchall()
        for row in rows:
            h = transaction_row_hash(row["date"], row["ticker"], row["type"],
                                     row["quantity"], row["total_amount"], row["currency"])
            conn.execute("UPDATE transactions SET row_hash = ? WHERE id = ?", (h, row["id"]))

        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_transactions_row_hash ON transactions(row_hash)"
        )

    if current_version < SCHEMA_VERSION:
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),)
        )
        conn.commit()


def transaction_row_hash(date, ticker, type_, quantity, total_amount, currency) -> str:
    """Deterministic hash of transaction key fields; NULLs treated as empty string."""
    parts = [
        str(date or ''),
        str(ticker or ''),
        str(type_ or ''),
        str(quantity if quantity is not None else ''),
        str(total_amount if total_amount is not None else ''),
        str(currency or ''),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()
