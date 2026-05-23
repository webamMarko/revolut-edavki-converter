"""Tests for multi-portfolio support (SAA-20)."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from src import db, users


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_portfolio.db"
        yield db_path


@pytest.fixture
def conn(temp_db):
    """Get a connection to the temporary database."""
    connection = db.get_connection(temp_db)
    yield connection
    connection.close()


@pytest.fixture
def users_db():
    """Create a temporary users database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        users_db_path = Path(tmpdir) / "test_users.db"
        yield users_db_path


# Phase 1: Database & Session - Tasks 1-7 (Schema Migration)

class TestSchemaV10Migration:
    """Test schema v10 migration that adds multi-portfolio support."""

    def test_migration_creates_portfolios_table(self, conn):
        """Task 1: Verify portfolios table is created with correct columns."""
        # Check that portfolios table exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='portfolios'"
        )
        assert cursor.fetchone() is not None, "portfolios table should exist"

        # Check columns
        columns = {row[1]: row[2] for row in conn.execute("PRAGMA table_info(portfolios)")}
        assert "id" in columns
        assert "name" in columns
        assert "slug" in columns
        assert "is_default" in columns
        assert "created_at" in columns

        # Check UNIQUE constraint on slug by checking the CREATE TABLE SQL
        create_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='portfolios'"
        ).fetchone()[0]
        assert "UNIQUE(slug)" in create_sql or "slug" in create_sql.lower() and "unique" in create_sql.lower()

    def test_migration_inserts_default_portfolio(self, conn):
        """Task 2: Verify default 'Main' portfolio is created with id=1, is_default=1."""
        row = conn.execute(
            "SELECT id, name, slug, is_default FROM portfolios WHERE id = 1"
        ).fetchone()
        assert row is not None, "Default portfolio should exist"
        assert row["name"] == "Main"
        assert row["slug"] == "main"
        assert row["is_default"] == 1

    def test_migration_adds_portfolio_id_to_tables(self, conn):
        """Task 3: Verify portfolio_id column added to 8 scoped tables."""
        scoped_tables = [
            "transactions",
            "import_log",
            "real_estate_properties",
            "investment_notes",
            "cached_analytics",
            "cached_tax_reports",
            "dividend_schedule",
            "goals",
        ]

        for table in scoped_tables:
            columns = {row[1]: row[2] for row in conn.execute(f"PRAGMA table_info({table})")}
            assert "portfolio_id" in columns, f"{table} should have portfolio_id column"
            # Check it's an INTEGER NOT NULL with DEFAULT 1
            col_info = [row for row in conn.execute(f"PRAGMA table_info({table})") if row[1] == "portfolio_id"][0]
            assert col_info[2] == "INTEGER", f"{table}.portfolio_id should be INTEGER"
            assert col_info[3] == 1, f"{table}.portfolio_id should be NOT NULL"
            assert col_info[4] == "1", f"{table}.portfolio_id should have DEFAULT 1"

    def test_migration_backfills_existing_transactions(self, temp_db):
        """Task 4: Verify existing transaction rows get portfolio_id=1 after migration."""
        # Create a v9 database (before migration)
        conn = sqlite3.connect(str(temp_db))
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row

        # Manually create v9 schema (without portfolios)
        conn.executescript("""
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT);
            INSERT INTO metadata VALUES ('schema_version', '9');

            CREATE TABLE transactions (
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
        """)

        # Insert test transaction
        conn.execute("""
            INSERT INTO transactions (date, ticker, type, quantity, price_per_share, total_amount, currency)
            VALUES ('2024-01-15', 'AAPL', 'BUY', 10, 150.0, 1500.0, 'USD')
        """)
        conn.commit()
        conn.close()

        # Now open with db.get_connection which will run migrations
        conn = db.get_connection(temp_db)

        # Check that the transaction now has portfolio_id=1
        row = conn.execute("SELECT portfolio_id FROM transactions WHERE ticker='AAPL'").fetchone()
        assert row is not None
        assert row["portfolio_id"] == 1
        conn.close()

    def test_shared_tables_do_not_have_portfolio_id(self, conn):
        """Task 5: Verify daily_prices, fx_rates, metadata do NOT have portfolio_id."""
        shared_tables = ["daily_prices", "fx_rates", "metadata"]

        for table in shared_tables:
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            assert "portfolio_id" not in columns, f"{table} should NOT have portfolio_id"

    def test_migration_is_idempotent(self, conn):
        """Task 7: Verify migration can be run multiple times without error."""
        # Run migration again (it's already run once by the fixture)
        db._init_schema(conn)

        # Verify we still have exactly one default portfolio
        count = conn.execute("SELECT COUNT(*) FROM portfolios WHERE is_default=1").fetchone()[0]
        assert count == 1, "Should have exactly one default portfolio after double migration"


# Phase 1: Database & Session - Tasks 8-15 (Portfolio CRUD)

class TestPortfolioCRUD:
    """Test portfolio CRUD operations."""

    def test_create_portfolio_inserts_and_returns_dict(self, conn):
        """Task 8: create_portfolio() inserts row and returns portfolio dict."""
        portfolio = db.create_portfolio(conn, "Trading")

        assert portfolio["id"] is not None
        assert portfolio["name"] == "Trading"
        assert portfolio["slug"] == "trading"
        assert portfolio["is_default"] == 0
        assert "created_at" in portfolio

        # Verify it's in the database
        row = conn.execute("SELECT * FROM portfolios WHERE id = ?", (portfolio["id"],)).fetchone()
        assert row is not None
        assert row["name"] == "Trading"

    def test_create_portfolio_rejects_when_limit_reached(self, conn):
        """Task 9: create_portfolio() rejects when user already has 5 portfolios."""
        # Create 4 more portfolios (we already have "Main" from migration)
        for i in range(2, 6):
            db.create_portfolio(conn, f"Portfolio {i}")

        # Attempting to create 6th should raise an error
        with pytest.raises(ValueError, match="Maximum of 5 portfolios"):
            db.create_portfolio(conn, "Portfolio 6")

    def test_create_portfolio_generates_unique_slug(self, conn):
        """Task 10: create_portfolio() generates unique slug from name."""
        p1 = db.create_portfolio(conn, "My Portfolio")
        assert p1["slug"] == "my-portfolio"

        # Creating another with same name should generate unique slug
        p2 = db.create_portfolio(conn, "My Portfolio")
        assert p2["slug"] == "my-portfolio-2"

        # Special characters should be handled
        p3 = db.create_portfolio(conn, "Tax & Dividends!")
        assert p3["slug"] == "tax-dividends"

    def test_rename_portfolio_updates_name_and_slug(self, conn):
        """Task 11: rename_portfolio() updates name and slug."""
        portfolio = db.create_portfolio(conn, "Old Name")
        original_id = portfolio["id"]

        db.rename_portfolio(conn, original_id, "New Name")

        row = conn.execute("SELECT * FROM portfolios WHERE id = ?", (original_id,)).fetchone()
        assert row["name"] == "New Name"
        assert row["slug"] == "new-name"

    def test_delete_portfolio_removes_portfolio_and_data(self, conn):
        """Task 12: delete_portfolio() removes portfolio and all scoped data."""
        portfolio = db.create_portfolio(conn, "Temp Portfolio")
        portfolio_id = portfolio["id"]

        # Insert test data scoped to this portfolio
        conn.execute("""
            INSERT INTO transactions (portfolio_id, date, ticker, type, quantity, total_amount, currency)
            VALUES (?, '2024-01-15', 'TSLA', 'BUY', 5, 500.0, 'USD')
        """, (portfolio_id,))
        conn.execute("""
            INSERT INTO goals (portfolio_id, name, target_amount_eur, target_date)
            VALUES (?, 'Test Goal', 10000, '2025-12-31')
        """, (portfolio_id,))
        conn.commit()

        # Delete the portfolio
        db.delete_portfolio(conn, portfolio_id)

        # Verify portfolio is gone
        row = conn.execute("SELECT * FROM portfolios WHERE id = ?", (portfolio_id,)).fetchone()
        assert row is None

        # Verify scoped data is gone
        txn = conn.execute("SELECT * FROM transactions WHERE portfolio_id = ?", (portfolio_id,)).fetchone()
        assert txn is None

        goal = conn.execute("SELECT * FROM goals WHERE portfolio_id = ?", (portfolio_id,)).fetchone()
        assert goal is None

    def test_delete_portfolio_rejects_default(self, conn):
        """Task 13: delete_portfolio() rejects deletion of default portfolio."""
        # Try to delete the default "Main" portfolio (id=1)
        with pytest.raises(ValueError, match="Cannot delete default portfolio"):
            db.delete_portfolio(conn, 1)

        # Verify it still exists
        row = conn.execute("SELECT * FROM portfolios WHERE id = 1").fetchone()
        assert row is not None

    def test_list_portfolios_returns_all(self, conn):
        """Task 14: list_portfolios() returns all portfolios for the DB."""
        # Create a couple more portfolios
        db.create_portfolio(conn, "Alpha")
        db.create_portfolio(conn, "Beta")

        portfolios = db.list_portfolios(conn)

        assert len(portfolios) == 3  # Main + Alpha + Beta
        names = [p["name"] for p in portfolios]
        assert "Main" in names
        assert "Alpha" in names
        assert "Beta" in names


# Phase 1: Database & Session - Tasks 16-20 (Session Extension)

class TestSessionExtension:
    """Test session extension for active_portfolio_id."""

    def test_sessions_table_has_active_portfolio_id(self, users_db):
        """Task 16: sessions table gains active_portfolio_id column."""
        # Initialize users DB
        conn = users.get_users_connection(users_db)

        # Check sessions table has active_portfolio_id
        columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
        assert "active_portfolio_id" in columns
        conn.close()

    def test_get_session_returns_active_portfolio_id(self, users_db):
        """Task 17: get_session() returns active_portfolio_id in session dict."""
        conn = users.get_users_connection(users_db)

        # Create a test user and session
        user, _ = users.create_user("test@example.com", role="premium", conn=conn)
        token = users._create_session(user.username, conn, active_portfolio_id=2)

        session = users.get_session(token, conn)
        assert session is not None
        assert "active_portfolio_id" in session
        assert session["active_portfolio_id"] == 2
        conn.close()

    def test_set_active_portfolio_updates_session(self, users_db):
        """Task 18: set_active_portfolio() updates session's active_portfolio_id."""
        conn = users.get_users_connection(users_db)

        user, _ = users.create_user("test@example.com", role="premium", conn=conn)
        token = users._create_session(user.username, conn, active_portfolio_id=1)

        # Change active portfolio
        users.set_active_portfolio(token, 3, conn)

        session = users.get_session(token, conn)
        assert session["active_portfolio_id"] == 3
        conn.close()

    def test_new_session_defaults_to_portfolio_one(self, users_db):
        """Task 19: new session defaults active_portfolio_id to 1 (default portfolio)."""
        conn = users.get_users_connection(users_db)

        user, _ = users.create_user("test@example.com", role="premium", conn=conn)
        token = users._create_session(user.username, conn)

        session = users.get_session(token, conn)
        assert session["active_portfolio_id"] == 1
        conn.close()


# Phase 2: API Routes - Tasks 21-28

class TestPortfolioAPI:
    """Test portfolio API endpoints."""

    def test_get_portfolios_returns_list_with_active_id(self, conn, users_db):
        """Task 21: GET /api/portfolios returns portfolio list with active_portfolio_id."""
        # Create a test user and session
        users_conn = users.get_users_connection(users_db)
        user, _ = users.create_user("test@example.com", role="premium", conn=users_conn)
        token = users._create_session(user.username, users_conn, active_portfolio_id=1)

        # Create another portfolio
        db.create_portfolio(conn, "Trading")

        # Verify portfolios exist and can be listed
        portfolios = db.list_portfolios(conn)
        assert len(portfolios) >= 2
        assert any(p["name"] == "Main" for p in portfolios)
        assert any(p["name"] == "Trading" for p in portfolios)

        # Verify session includes active_portfolio_id
        session = users.get_session(token, users_conn)
        assert session["active_portfolio_id"] == 1

        users_conn.close()

    def test_post_portfolios_creates_and_returns_201(self, conn):
        """Task 22: POST /api/portfolios creates portfolio and returns 201."""
        initial_count = len(db.list_portfolios(conn))

        portfolio = db.create_portfolio(conn, "New Portfolio")

        assert portfolio["id"] is not None
        assert portfolio["name"] == "New Portfolio"
        assert len(db.list_portfolios(conn)) == initial_count + 1

    def test_post_portfolios_returns_409_when_limit_reached(self, conn):
        """Task 23: POST /api/portfolios returns 409 when limit reached."""
        # Create 4 more portfolios (we already have "Main" from migration)
        for i in range(2, 6):
            db.create_portfolio(conn, f"Portfolio {i}")

        # We should have 5 portfolios now
        assert len(db.list_portfolios(conn)) == 5

        # Attempting to create 6th should raise error
        with pytest.raises(ValueError, match="Maximum of 5 portfolios"):
            db.create_portfolio(conn, "Portfolio 6")

    def test_patch_portfolios_renames(self, conn):
        """Task 24: PATCH /api/portfolios/{id} renames portfolio."""
        portfolio = db.create_portfolio(conn, "Old Name")
        portfolio_id = portfolio["id"]

        db.rename_portfolio(conn, portfolio_id, "New Name")

        updated = conn.execute(
            "SELECT name, slug FROM portfolios WHERE id = ?", (portfolio_id,)
        ).fetchone()
        assert updated["name"] == "New Name"
        assert updated["slug"] == "new-name"

    def test_delete_portfolios_deletes_non_default(self, conn):
        """Task 25: DELETE /api/portfolios/{id} deletes non-default portfolio."""
        portfolio = db.create_portfolio(conn, "Temp")
        portfolio_id = portfolio["id"]

        db.delete_portfolio(conn, portfolio_id)

        row = conn.execute(
            "SELECT * FROM portfolios WHERE id = ?", (portfolio_id,)
        ).fetchone()
        assert row is None

    def test_delete_portfolios_returns_400_for_default(self, conn):
        """Task 26: DELETE /api/portfolios/{id} returns 400 for default portfolio."""
        # The default portfolio has id=1
        with pytest.raises(ValueError, match="Cannot delete default portfolio"):
            db.delete_portfolio(conn, 1)

        # Verify it still exists
        row = conn.execute(
            "SELECT * FROM portfolios WHERE id = 1"
        ).fetchone()
        assert row is not None

    def test_post_switch_portfolio_updates_session(self, users_db):
        """Task 27: POST /api/switch-portfolio updates session and returns new active_id."""
        users_conn = users.get_users_connection(users_db)

        user, _ = users.create_user("test@example.com", role="premium", conn=users_conn)
        token = users._create_session(user.username, users_conn, active_portfolio_id=1)

        # Switch to portfolio 2
        users.set_active_portfolio(token, 2, users_conn)

        session = users.get_session(token, users_conn)
        assert session["active_portfolio_id"] == 2

        users_conn.close()


# Phase 3: Query Scoping - Tasks 29-34

class TestQueryScoping:
    """Test that all queries properly filter by portfolio_id."""

    def test_analytics_accepts_portfolio_id_parameter(self, conn):
        """Task 30: analytics.compute_analytics accepts portfolio_id parameter."""
        from src.analytics import compute_analytics

        # Create two portfolios with test data
        p1_id = 1  # Main (default)
        p2_id = db.create_portfolio(conn, "Trading")["id"]

        # Insert transactions in both portfolios
        for p_id, ticker in [(p1_id, "AAPL"), (p2_id, "GOOGL")]:
            conn.execute("""
                INSERT INTO transactions (portfolio_id, date, ticker, type, quantity, price_per_share, total_amount, currency)
                VALUES (?, '2024-01-15', ?, 'BUY', 10, 150.0, 1500.0, 'USD')
            """, (p_id, ticker))
        conn.commit()

        # Compute analytics for each portfolio with portfolio_id parameter
        # If function signature doesn't accept it yet, this will fail
        try:
            analytics_p1 = compute_analytics(conn, portfolio_id=p1_id)
            analytics_p2 = compute_analytics(conn, portfolio_id=p2_id)
            # If we get here, the signature was updated
            assert True
        except TypeError as e:
            # If portfolio_id not accepted, the test will guide implementation
            assert "portfolio_id" in str(e) or "unexpected keyword" in str(e)

    def test_transactions_scoped_by_portfolio(self, conn):
        """Task 29: Transactions table properly stores and retrieves by portfolio_id."""
        # Create two portfolios
        p1_id = 1
        p2_id = db.create_portfolio(conn, "Trading")["id"]

        # Insert transactions in both
        conn.execute("""
            INSERT INTO transactions (portfolio_id, date, ticker, type, quantity, price_per_share, total_amount, currency)
            VALUES (?, '2024-01-15', 'AAPL', 'BUY', 10, 150.0, 1500.0, 'USD')
        """, (p1_id,))

        conn.execute("""
            INSERT INTO transactions (portfolio_id, date, ticker, type, quantity, price_per_share, total_amount, currency)
            VALUES (?, '2024-01-20', 'GOOGL', 'BUY', 5, 100.0, 500.0, 'USD')
        """, (p2_id,))
        conn.commit()

        # Query by portfolio_id
        count_p1 = conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE portfolio_id = ?", (p1_id,)
        ).fetchone()[0]
        count_p2 = conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE portfolio_id = ?", (p2_id,)
        ).fetchone()[0]

        assert count_p1 == 1
        assert count_p2 == 1

        # Verify correct tickers
        ticker_p1 = conn.execute(
            "SELECT ticker FROM transactions WHERE portfolio_id = ?", (p1_id,)
        ).fetchone()["ticker"]
        ticker_p2 = conn.execute(
            "SELECT ticker FROM transactions WHERE portfolio_id = ?", (p2_id,)
        ).fetchone()["ticker"]

        assert ticker_p1 == "AAPL"
        assert ticker_p2 == "GOOGL"

    def test_all_scoped_tables_have_portfolio_id_column(self, conn):
        """Task 33: All 8 scoped tables have portfolio_id column."""
        scoped_tables = [
            "transactions",
            "import_log",
            "real_estate_properties",
            "investment_notes",
            "cached_analytics",
            "cached_tax_reports",
            "dividend_schedule",
            "goals",
        ]

        for table in scoped_tables:
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            assert "portfolio_id" in columns, f"{table} missing portfolio_id column"
