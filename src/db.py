"""SQLite database layer for portfolio analytics."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

DB_DIR = Path.home() / ".revolut-edavki"
DB_PATH = DB_DIR / "portfolio.db"

SCHEMA_VERSION = 13

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
    commission      REAL,
    withholding_tax REAL,
    broker_source   TEXT,
    correlation_id  TEXT,
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
    date          TEXT NOT NULL,
    from_currency TEXT NOT NULL,
    to_currency   TEXT NOT NULL,
    rate          REAL NOT NULL,
    PRIMARY KEY (date, from_currency, to_currency)
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

CREATE TABLE IF NOT EXISTS portfolios (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    slug       TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(slug)
);

CREATE TABLE IF NOT EXISTS real_estate_properties (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker                  TEXT NOT NULL UNIQUE,
    name                    TEXT NOT NULL,
    address                 TEXT,
    municipality            TEXT NOT NULL DEFAULT '',
    cadastral_municipality  TEXT,
    property_type           TEXT NOT NULL DEFAULT 'other',
    area_m2                 REAL,
    purchase_price_eur      REAL NOT NULL DEFAULT 0,
    purchase_date           TEXT NOT NULL DEFAULT '',
    notes                   TEXT,
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    country                 TEXT NOT NULL DEFAULT 'SI',
    currency                TEXT NOT NULL DEFAULT 'EUR',
    address_line_1          TEXT,
    address_line_2          TEXT,
    city                    TEXT,
    state_province          TEXT,
    postal_code             TEXT,
    property_name           TEXT,
    acquisition_price       REAL,
    acquisition_fx_rate     REAL NOT NULL DEFAULT 1.0,
    current_market_value    REAL,
    current_market_value_date TEXT,
    ownership_percentage    REAL DEFAULT 100.0,
    tax_id                  TEXT,
    status                  TEXT NOT NULL DEFAULT 'active',
    description             TEXT,
    property_manager_name   TEXT,
    property_manager_email  TEXT,
    agent_name              TEXT,
    agent_email             TEXT,
    updated_at              TEXT,
    deleted_at              TEXT
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

CREATE TABLE IF NOT EXISTS cached_analytics (
    scope       TEXT PRIMARY KEY,
    data_hash   TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS dividend_schedule (
    ticker          TEXT NOT NULL,
    ex_date         TEXT NOT NULL,
    payment_date    TEXT,
    amount          REAL NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'USD',
    frequency       TEXT,
    fetched_at      TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (ticker, ex_date)
);

CREATE INDEX IF NOT EXISTS idx_dividend_schedule_date ON dividend_schedule(ex_date);

CREATE TABLE IF NOT EXISTS goals (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    target_amount_eur   REAL NOT NULL,
    target_date         TEXT NOT NULL,
    monthly_contribution REAL NOT NULL DEFAULT 0,
    scope               TEXT NOT NULL DEFAULT 'all',
    tickers             TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transaction_audit (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id  INTEGER NOT NULL,
    action          TEXT NOT NULL,
    field_name      TEXT,
    old_value       TEXT,
    new_value       TEXT,
    changed_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_audit_txn ON transaction_audit(transaction_id);
"""


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Get a database connection, creating the DB directory and schema if needed.

    db_path: explicit path (used by web layer for per-user DBs).
             Falls back to REVOLUT_DB_PATH env var, then the default DB_PATH.
    """
    if db_path is not None:
        path = Path(db_path)
    elif "REVOLUT_DB_PATH" in os.environ:
        path = Path(os.environ["REVOLUT_DB_PATH"])
    else:
        path = DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
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

    if current_version < 6:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS cached_analytics (
                scope       TEXT PRIMARY KEY,
                data_hash   TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)

    if current_version < 7:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS cached_tax_reports (
                year        INTEGER NOT NULL,
                scope       TEXT NOT NULL,
                country     TEXT NOT NULL DEFAULT 'SI',
                data_hash   TEXT NOT NULL,
                result_json TEXT NOT NULL,
                is_immutable INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (year, scope, country)
            );
        """)

    if current_version < 8:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS dividend_schedule (
                ticker          TEXT NOT NULL,
                ex_date         TEXT NOT NULL,
                payment_date    TEXT,
                amount          REAL NOT NULL,
                currency        TEXT NOT NULL DEFAULT 'USD',
                frequency       TEXT,
                fetched_at      TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (ticker, ex_date)
            );
            CREATE INDEX IF NOT EXISTS idx_dividend_schedule_date ON dividend_schedule(ex_date);
        """)

    if current_version < 9:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS goals (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                name                TEXT NOT NULL,
                target_amount_eur   REAL NOT NULL,
                target_date         TEXT NOT NULL,
                monthly_contribution REAL NOT NULL DEFAULT 0,
                scope               TEXT NOT NULL DEFAULT 'all',
                tickers             TEXT NOT NULL DEFAULT '',
                created_at          TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)

    if current_version < 10:
        # Multi-portfolio support: add portfolios table and portfolio_id to scoped tables
        # Insert default "Main" portfolio if it doesn't exist
        default_exists = conn.execute("SELECT 1 FROM portfolios WHERE id = 1").fetchone()
        if not default_exists:
            conn.execute("""
                INSERT INTO portfolios (id, name, slug, is_default)
                VALUES (1, 'Main', 'main', 1)
            """)

        # Add portfolio_id column to scoped tables
        scoped_tables = [
            "transactions",
            "import_log",
            "real_estate_properties",
            "investment_notes",
            "cached_analytics",
            "dividend_schedule",
            "goals",
        ]

        for table in scoped_tables:
            # Check if column already exists
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if "portfolio_id" not in columns:
                conn.execute(f"""
                    ALTER TABLE {table}
                    ADD COLUMN portfolio_id INTEGER NOT NULL DEFAULT 1
                """)

        # Add portfolio_id to cached_tax_reports if it exists
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "cached_tax_reports" in tables:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(cached_tax_reports)")}
            if "portfolio_id" not in columns:
                conn.execute("""
                    ALTER TABLE cached_tax_reports
                    ADD COLUMN portfolio_id INTEGER NOT NULL DEFAULT 1
                """)

        conn.commit()

    if current_version < 11:
        # Add new columns to transactions (Phase 1 plugin architecture)
        tx_cols = {row[1] for row in conn.execute("PRAGMA table_info(transactions)")}
        for col, ddl in [
            ("commission",      "REAL"),
            ("withholding_tax", "REAL"),
            ("broker_source",   "TEXT"),
            ("correlation_id",  "TEXT"),
        ]:
            if col not in tx_cols:
                conn.execute(f"ALTER TABLE transactions ADD COLUMN {col} {ddl}")

        # Migrate fx_rates: old schema had (date PK, eur_usd); new schema is
        # (date, from_currency, to_currency, rate) with composite PK.
        # Detect old schema by checking for eur_usd column.
        fx_cols = {row[1] for row in conn.execute("PRAGMA table_info(fx_rates)")}
        if "eur_usd" in fx_cols:
            # Migrate existing EUR/USD rows
            old_rows = conn.execute("SELECT date, eur_usd FROM fx_rates").fetchall()
            conn.execute("DROP TABLE fx_rates")
            conn.execute("""
                CREATE TABLE fx_rates (
                    date          TEXT NOT NULL,
                    from_currency TEXT NOT NULL,
                    to_currency   TEXT NOT NULL,
                    rate          REAL NOT NULL,
                    PRIMARY KEY (date, from_currency, to_currency)
                )
            """)
            if old_rows:
                conn.executemany(
                    "INSERT OR IGNORE INTO fx_rates (date, from_currency, to_currency, rate) "
                    "VALUES (?, 'USD', 'EUR', ?)",
                    [(r[0], r[1]) for r in old_rows],
                )
        conn.commit()

    if current_version < 12:
        # Extend real_estate_properties with new fields for international + financial data.
        # All defaults must be constants (no function calls) because ALTER TABLE ADD COLUMN
        # does not allow non-constant defaults in SQLite.
        re_cols = {row[1] for row in conn.execute("PRAGMA table_info(real_estate_properties)")}
        new_cols = [
            ("country",                    "TEXT NOT NULL DEFAULT 'SI'"),
            ("currency",                   "TEXT NOT NULL DEFAULT 'EUR'"),
            ("address_line_1",             "TEXT"),
            ("address_line_2",             "TEXT"),
            ("city",                       "TEXT"),
            ("state_province",             "TEXT"),
            ("postal_code",                "TEXT"),
            ("property_name",              "TEXT"),
            ("acquisition_price",          "REAL"),
            ("acquisition_fx_rate",        "REAL NOT NULL DEFAULT 1.0"),
            ("current_market_value",       "REAL"),
            ("current_market_value_date",  "TEXT"),
            ("ownership_percentage",       "REAL DEFAULT 100.0"),
            ("tax_id",                     "TEXT"),
            ("status",                     "TEXT NOT NULL DEFAULT 'active'"),
            ("description",                "TEXT"),
            ("property_manager_name",      "TEXT"),
            ("property_manager_email",     "TEXT"),
            ("agent_name",                 "TEXT"),
            ("agent_email",                "TEXT"),
            ("updated_at",                 "TEXT"),
            ("deleted_at",                 "TEXT"),
        ]
        for col, ddl in new_cols:
            if col not in re_cols:
                conn.execute(f"ALTER TABLE real_estate_properties ADD COLUMN {col} {ddl}")

        # Backfill new columns from legacy columns where data exists
        conn.execute("""
            UPDATE real_estate_properties
            SET address_line_1 = address
            WHERE address IS NOT NULL AND address_line_1 IS NULL
        """)
        conn.execute("""
            UPDATE real_estate_properties
            SET city = municipality
            WHERE municipality IS NOT NULL AND city IS NULL
        """)
        conn.execute("""
            UPDATE real_estate_properties
            SET acquisition_price = purchase_price_eur
            WHERE purchase_price_eur IS NOT NULL AND acquisition_price IS NULL
        """)
        conn.commit()

    if current_version < 13:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS transaction_audit (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id  INTEGER NOT NULL,
                action          TEXT NOT NULL,
                field_name      TEXT,
                old_value       TEXT,
                new_value       TEXT,
                changed_at      TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_audit_txn ON transaction_audit(transaction_id);
        """)

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


# Portfolio CRUD functions

def _generate_slug(conn: sqlite3.Connection, name: str) -> str:
    """Generate a unique slug from a portfolio name."""
    import re
    # Convert to lowercase, replace non-alphanumeric with hyphens, strip leading/trailing hyphens
    base_slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    if not base_slug:
        base_slug = "portfolio"

    # Check for uniqueness, append -2, -3, etc. if needed
    slug = base_slug
    counter = 2
    while True:
        existing = conn.execute("SELECT 1 FROM portfolios WHERE slug = ?", (slug,)).fetchone()
        if not existing:
            break
        slug = f"{base_slug}-{counter}"
        counter += 1

    return slug


def list_portfolios(conn: sqlite3.Connection) -> list[dict]:
    """Return all portfolios as a list of dicts."""
    rows = conn.execute("""
        SELECT id, name, slug, is_default, created_at
        FROM portfolios
        ORDER BY is_default DESC, created_at ASC
    """).fetchall()
    return [dict(row) for row in rows]


def create_portfolio(conn: sqlite3.Connection, name: str) -> dict:
    """Create a new portfolio. Raises ValueError if limit of 5 is reached."""
    # Check portfolio limit
    count = conn.execute("SELECT COUNT(*) FROM portfolios").fetchone()[0]
    if count >= 5:
        raise ValueError("Maximum of 5 portfolios reached")

    slug = _generate_slug(conn, name)
    cursor = conn.execute("""
        INSERT INTO portfolios (name, slug, is_default)
        VALUES (?, ?, 0)
    """, (name, slug))
    conn.commit()

    # Return the created portfolio
    row = conn.execute("SELECT * FROM portfolios WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


def rename_portfolio(conn: sqlite3.Connection, portfolio_id: int, new_name: str):
    """Rename a portfolio and regenerate its slug."""
    new_slug = _generate_slug(conn, new_name)
    conn.execute("""
        UPDATE portfolios
        SET name = ?, slug = ?
        WHERE id = ?
    """, (new_name, new_slug, portfolio_id))
    conn.commit()


def delete_portfolio(conn: sqlite3.Connection, portfolio_id: int):
    """Delete a portfolio and all its scoped data. Raises ValueError for default portfolio."""
    # Check if it's the default portfolio
    row = conn.execute("SELECT is_default FROM portfolios WHERE id = ?", (portfolio_id,)).fetchone()
    if not row:
        raise ValueError("Portfolio not found")
    if row["is_default"]:
        raise ValueError("Cannot delete default portfolio")

    # Delete scoped data
    scoped_tables = [
        "transactions",
        "import_log",
        "real_estate_properties",
        "investment_notes",
        "cached_analytics",
        "dividend_schedule",
        "goals",
    ]

    for table in scoped_tables:
        conn.execute(f"DELETE FROM {table} WHERE portfolio_id = ?", (portfolio_id,))

    # Delete cached_tax_reports if table exists
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    if "cached_tax_reports" in tables:
        conn.execute("DELETE FROM cached_tax_reports WHERE portfolio_id = ?", (portfolio_id,))

    # Delete the portfolio itself
    conn.execute("DELETE FROM portfolios WHERE id = ?", (portfolio_id,))
    conn.commit()
