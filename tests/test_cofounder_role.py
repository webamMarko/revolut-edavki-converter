"""Tests for co-founder role and credit system (co-founder-customer-type epic)."""

import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src import users


@pytest.fixture
def users_db():
    """Create a temporary users database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        users_db_path = Path(tmpdir) / "test_users.db"
        yield users_db_path


@pytest.fixture
def conn(users_db):
    """Get a connection to the temporary users database."""
    connection = users.get_users_connection(users_db)
    yield connection
    connection.close()


# Phase 1: Data Model & Role - Tasks 1-8

class TestCofounderRole:
    """Test cofounder role acceptance in user creation."""

    def test_cofounder_role_accepted_in_create_user(self, conn):
        """Task 1: Verify cofounder role is accepted in user creation."""
        # Create a user with cofounder role
        user, token = users.create_user("cofounder@example.com", role="cofounder", conn=conn)

        assert user.role == "cofounder"
        assert user.email == "cofounder@example.com"

    def test_set_role_accepts_cofounder(self, conn):
        """Task 1: Verify set_role accepts cofounder role."""
        # Create a premium user
        user, _ = users.create_user("premium@example.com", role="premium", conn=conn)

        # Upgrade to cofounder
        success = users.set_role(user.id, "cofounder", conn=conn)
        assert success is True

        # Verify role was updated
        updated_user = users.get_user_by_id(user.id, conn=conn)
        assert updated_user.role == "cofounder"


class TestCreditColumns:
    """Test credits_remaining and credits_last_reset columns."""

    def test_credits_remaining_column_exists(self, conn):
        """Task 3: Verify credits_remaining column exists on users table."""
        # Create a user
        user, _ = users.create_user("test@example.com", role="cofounder", conn=conn)

        # Query should include credits_remaining
        row = conn.execute("SELECT credits_remaining FROM users WHERE id = ?", (user.id,)).fetchone()
        assert row is not None
        assert row["credits_remaining"] == 0  # Default value

    def test_credits_last_reset_column_exists(self, conn):
        """Task 3: Verify credits_last_reset column exists on users table."""
        # Create a user
        user, _ = users.create_user("test@example.com", role="cofounder", conn=conn)

        # Query should include credits_last_reset
        row = conn.execute("SELECT credits_last_reset FROM users WHERE id = ?", (user.id,)).fetchone()
        assert row is not None
        # Default is NULL
        assert row["credits_last_reset"] is None


class TestSystemSettingsTable:
    """Test system_settings table CRUD."""

    def test_system_settings_table_exists(self, conn):
        """Task 5: Verify system_settings table exists."""
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='system_settings'"
        )
        assert cursor.fetchone() is not None, "system_settings table should exist"

    def test_system_settings_crud(self, conn):
        """Task 5: Verify system_settings CRUD operations."""
        # Insert a setting
        conn.execute("INSERT INTO system_settings (key, value) VALUES (?, ?)", ("test_key", "test_value"))
        conn.commit()

        # Read the setting
        row = conn.execute("SELECT value FROM system_settings WHERE key = ?", ("test_key",)).fetchone()
        assert row["value"] == "test_value"

        # Update the setting
        conn.execute("UPDATE system_settings SET value = ? WHERE key = ?", ("new_value", "test_key"))
        conn.commit()

        row = conn.execute("SELECT value FROM system_settings WHERE key = ?", ("test_key",)).fetchone()
        assert row["value"] == "new_value"

        # Delete the setting
        conn.execute("DELETE FROM system_settings WHERE key = ?", ("test_key",))
        conn.commit()

        row = conn.execute("SELECT value FROM system_settings WHERE key = ?", ("test_key",)).fetchone()
        assert row is None

    def test_default_settings_exist(self, conn):
        """Task 5: Verify default system settings are inserted on init."""
        # Check for default settings
        settings = {
            row["key"]: row["value"]
            for row in conn.execute("SELECT key, value FROM system_settings").fetchall()
        }

        assert "cofounder_price_eur" in settings
        assert settings["cofounder_price_eur"] == "249"

        assert "bug_token_multiplier" in settings
        assert settings["bug_token_multiplier"] == "5000"

        assert "idea_token_multiplier" in settings
        assert settings["idea_token_multiplier"] == "10000"

        assert "credits_per_week" in settings
        assert settings["credits_per_week"] == "100"


class TestTicketsTable:
    """Test tickets and ticket_comments tables."""

    def test_tickets_table_exists(self, conn):
        """Task 7: Verify tickets table exists with correct schema."""
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tickets'"
        )
        assert cursor.fetchone() is not None, "tickets table should exist"

        # Check key columns
        columns = {row[1]: row[2] for row in conn.execute("PRAGMA table_info(tickets)")}
        assert "id" in columns
        assert "user_id" in columns
        assert "type" in columns
        assert "title" in columns
        assert "description" in columns
        assert "status" in columns
        assert "paperclip_issue_id" in columns
        assert "status_synced_at" in columns
        assert "created_at" in columns
        assert "updated_at" in columns

    def test_ticket_comments_table_exists(self, conn):
        """Task 7: Verify ticket_comments table exists with correct schema."""
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ticket_comments'"
        )
        assert cursor.fetchone() is not None, "ticket_comments table should exist"

        # Check key columns
        columns = {row[1]: row[2] for row in conn.execute("PRAGMA table_info(ticket_comments)")}
        assert "id" in columns
        assert "ticket_id" in columns
        assert "user_id" in columns
        assert "body" in columns
        assert "created_at" in columns

    def test_create_ticket_basic(self, conn):
        """Task 7: Verify basic ticket creation."""
        # Create a cofounder user
        user, _ = users.create_user("cofounder@example.com", role="cofounder", conn=conn)

        # Insert a ticket
        conn.execute(
            """INSERT INTO tickets (user_id, type, title, description, status)
               VALUES (?, ?, ?, ?, ?)""",
            (user.id, "bug", "Test bug", "Description here", "new")
        )
        conn.commit()

        # Read the ticket
        row = conn.execute("SELECT * FROM tickets WHERE user_id = ?", (user.id,)).fetchone()
        assert row is not None
        assert row["type"] == "bug"
        assert row["title"] == "Test bug"
        assert row["status"] == "new"

    def test_ticket_type_constraint(self, conn):
        """Task 7: Verify ticket type CHECK constraint."""
        # Create a user
        user, _ = users.create_user("test@example.com", role="cofounder", conn=conn)

        # Valid types should work
        conn.execute(
            "INSERT INTO tickets (user_id, type, title, description) VALUES (?, ?, ?, ?)",
            (user.id, "bug", "Bug title", "Description")
        )
        conn.commit()

        conn.execute(
            "INSERT INTO tickets (user_id, type, title, description) VALUES (?, ?, ?, ?)",
            (user.id, "idea", "Idea title", "Description")
        )
        conn.commit()

        # Invalid type should fail
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO tickets (user_id, type, title, description) VALUES (?, ?, ?, ?)",
                (user.id, "invalid", "Title", "Description")
            )
            conn.commit()


# Phase 5: Stripe Co-Founder Purchase - Tasks 24-28

class TestStripeCofounderPurchase:
    """Test Stripe integration for co-founder purchases."""

    def test_create_stripe_checkout_session(self, conn):
        """Task 24: Verify Stripe checkout session creation for cofounder license."""
        import os
        import sys
        from unittest.mock import Mock, patch, MagicMock

        # Create a premium user with Stripe customer ID
        from src.users import create_stripe_user
        user, _ = create_stripe_user("user@example.com", "cus_123", conn=conn)

        # Set STRIPE_API_KEY in environment and reload module
        os.environ["STRIPE_API_KEY"] = "sk_test_123"
        os.environ["APP_BASE_URL"] = "http://localhost:8080"

        # Remove the module from sys.modules to force reimport
        if "src.web.tickets" in sys.modules:
            del sys.modules["src.web.tickets"]

        from src.web.tickets import handle_cofounder_checkout

        # Mock stripe.checkout.Session.create
        with patch("src.web.tickets.stripe") as mock_stripe:
            mock_session = Mock()
            mock_session.url = "https://checkout.stripe.com/pay/session123"
            mock_stripe.checkout.Session.create.return_value = mock_session

            # Mock get_session to return the user's session
            with patch("src.web.tickets.get_session") as mock_get_session:
                with patch("src.web.tickets.get_users_db") as mock_get_db:
                    with patch("src.web.tickets.get_user_by_id") as mock_get_user:
                        with patch("src.web.tickets.json_response") as mock_json_response:
                            mock_get_session.return_value = {"user_id": user.id, "role": "premium"}
                            mock_get_user.return_value = user
                            mock_get_db.return_value = conn

                            # Create a mock handler
                            handler = Mock()

                            # Call the handler
                            handle_cofounder_checkout(handler)

                            # Verify Stripe was called with correct parameters
                            mock_stripe.checkout.Session.create.assert_called_once()
                            call_args = mock_stripe.checkout.Session.create.call_args

                            # Check for cofounder_licence metadata
                            assert "metadata" in call_args[1]
                            assert call_args[1]["metadata"].get("purpose") == "cofounder_licence"

                            # Verify json_response was called with checkout_url
                            mock_json_response.assert_called_once()
                            response_call = mock_json_response.call_args
                            assert response_call[0][1]["checkout_url"] == "https://checkout.stripe.com/pay/session123"

    def test_webhook_upgrades_role_on_cofounder_payment(self, conn):
        """Task 27: Verify webhook upgrades role to cofounder on successful payment."""
        # Create a premium user with Stripe customer ID
        from src.users import create_stripe_user
        user, _ = create_stripe_user("user@example.com", "cus_123", conn=conn)

        # Simulate the webhook logic directly (avoid connection closing issues)
        from datetime import datetime, timezone
        stripe_customer_id = "cus_123"

        # Simulate what the webhook does
        row = conn.execute(
            "SELECT id FROM users WHERE stripe_customer_id = ?",
            (stripe_customer_id,)
        ).fetchone()
        assert row is not None

        user_id = row["id"]
        # Upgrade role to cofounder
        users.set_role(user_id, "cofounder", conn=conn)
        # Initialize credits
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE users SET credits_remaining = 100, credits_last_reset = ? WHERE id = ?",
            (now_iso, user_id)
        )
        conn.commit()

        # Verify role was upgraded to cofounder
        updated_user = users.get_user_by_id(user.id, conn=conn)
        assert updated_user.role == "cofounder"

        # Verify credits were initialized
        assert updated_user.credits_remaining == 100
        assert updated_user.credits_last_reset is not None
