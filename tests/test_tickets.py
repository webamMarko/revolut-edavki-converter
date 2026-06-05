"""Tests for ticket system and credit management (co-founder-customer-type epic)."""

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


# Phase 2: Credit System - Tasks 9-12

class TestCreditSystem:
    """Test credit management functions."""

    def test_ensure_credits_resets_after_7_days(self, conn):
        """Task 9: Verify ensure_credits() resets to 100 if last_reset > 7 days ago."""
        from src import tickets

        # Create a cofounder user with stale credits
        user, _ = users.create_user("cofounder@example.com", role="cofounder", conn=conn)

        # Set credits_remaining to 0 and credits_last_reset to 8 days ago
        eight_days_ago = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        conn.execute(
            "UPDATE users SET credits_remaining = 0, credits_last_reset = ? WHERE id = ?",
            (eight_days_ago, user.id)
        )
        conn.commit()

        # Call ensure_credits
        tickets.ensure_credits(user.id, conn=conn)

        # Verify credits were reset to 100
        row = conn.execute("SELECT credits_remaining, credits_last_reset FROM users WHERE id = ?", (user.id,)).fetchone()
        assert row["credits_remaining"] == 100
        # Verify last_reset was updated (should be recent)
        last_reset = datetime.fromisoformat(row["credits_last_reset"])
        now = datetime.now(timezone.utc)
        assert (now - last_reset).total_seconds() < 60  # Should be within the last minute

    def test_ensure_credits_no_reset_if_recent(self, conn):
        """Task 9: Verify ensure_credits() does not reset if last_reset is recent."""
        from src import tickets

        # Create a cofounder user with recent credits
        user, _ = users.create_user("cofounder@example.com", role="cofounder", conn=conn)

        # Set credits_remaining to 50 and credits_last_reset to 2 days ago
        two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        conn.execute(
            "UPDATE users SET credits_remaining = 50, credits_last_reset = ? WHERE id = ?",
            (two_days_ago, user.id)
        )
        conn.commit()

        # Call ensure_credits
        tickets.ensure_credits(user.id, conn=conn)

        # Verify credits were NOT reset (still 50)
        row = conn.execute("SELECT credits_remaining FROM users WHERE id = ?", (user.id,)).fetchone()
        assert row["credits_remaining"] == 50

    def test_ensure_credits_initializes_null_last_reset(self, conn):
        """Task 9: Verify ensure_credits() initializes credits if last_reset is NULL."""
        from src import tickets

        # Create a cofounder user with NULL last_reset
        user, _ = users.create_user("cofounder@example.com", role="cofounder", conn=conn)

        # Ensure credits_last_reset is NULL (default state)
        row = conn.execute("SELECT credits_last_reset FROM users WHERE id = ?", (user.id,)).fetchone()
        assert row["credits_last_reset"] is None

        # Call ensure_credits
        tickets.ensure_credits(user.id, conn=conn)

        # Verify credits were initialized to 100
        row = conn.execute("SELECT credits_remaining, credits_last_reset FROM users WHERE id = ?", (user.id,)).fetchone()
        assert row["credits_remaining"] == 100
        assert row["credits_last_reset"] is not None

    def test_deduct_credit_reduces_balance(self, conn):
        """Task 11: Verify deduct_credit() reduces balance by 1."""
        from src import tickets

        # Create a cofounder user with credits
        user, _ = users.create_user("cofounder@example.com", role="cofounder", conn=conn)
        conn.execute(
            "UPDATE users SET credits_remaining = 10 WHERE id = ?",
            (user.id,)
        )
        conn.commit()

        # Deduct 1 credit
        new_balance = tickets.deduct_credit(user.id, conn=conn)

        # Verify balance is now 9
        assert new_balance == 9
        row = conn.execute("SELECT credits_remaining FROM users WHERE id = ?", (user.id,)).fetchone()
        assert row["credits_remaining"] == 9

    def test_deduct_credit_fails_at_zero(self, conn):
        """Task 11: Verify deduct_credit() raises exception at 0 balance."""
        from src import tickets

        # Create a cofounder user with 0 credits
        user, _ = users.create_user("cofounder@example.com", role="cofounder", conn=conn)
        conn.execute(
            "UPDATE users SET credits_remaining = 0 WHERE id = ?",
            (user.id,)
        )
        conn.commit()

        # Attempt to deduct should raise exception
        with pytest.raises(tickets.InsufficientCreditsError):
            tickets.deduct_credit(user.id, conn=conn)

        # Verify balance is still 0
        row = conn.execute("SELECT credits_remaining FROM users WHERE id = ?", (user.id,)).fetchone()
        assert row["credits_remaining"] == 0

    def test_deduct_credit_fails_at_negative(self, conn):
        """Task 11: Verify deduct_credit() prevents negative balance."""
        from src import tickets

        # Create a cofounder user with 0 credits
        user, _ = users.create_user("cofounder@example.com", role="cofounder", conn=conn)
        conn.execute(
            "UPDATE users SET credits_remaining = 0 WHERE id = ?",
            (user.id,)
        )
        conn.commit()

        # Try to deduct twice
        with pytest.raises(tickets.InsufficientCreditsError):
            tickets.deduct_credit(user.id, conn=conn)

        # Balance should still be 0
        row = conn.execute("SELECT credits_remaining FROM users WHERE id = ?", (user.id,)).fetchone()
        assert row["credits_remaining"] == 0


# Phase 3: Ticket CRUD - Tasks 13-18

class TestTicketCRUD:
    """Test ticket creation and query functions."""

    def test_create_ticket_deducts_credit(self, conn):
        """Task 13: Verify create_ticket() creates row and deducts credit."""
        from src import tickets

        # Create a cofounder user with credits
        user, _ = users.create_user("cofounder@example.com", role="cofounder", conn=conn)
        conn.execute("UPDATE users SET credits_remaining = 10 WHERE id = ?", (user.id,))
        conn.commit()

        # Create a ticket
        ticket_id = tickets.create_ticket(
            user_id=user.id,
            ticket_type="bug",
            title="Test bug",
            description="Bug description here",
            conn=conn
        )

        # Verify ticket was created
        assert ticket_id is not None
        ticket_row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        assert ticket_row is not None
        assert ticket_row["user_id"] == user.id
        assert ticket_row["type"] == "bug"
        assert ticket_row["title"] == "Test bug"
        assert ticket_row["description"] == "Bug description here"
        assert ticket_row["status"] == "new"

        # Verify credit was deducted
        user_row = conn.execute("SELECT credits_remaining FROM users WHERE id = ?", (user.id,)).fetchone()
        assert user_row["credits_remaining"] == 9

    def test_create_ticket_fails_with_zero_credits(self, conn):
        """Task 13: Verify create_ticket() fails when user has 0 credits."""
        from src import tickets

        # Create a cofounder user with 0 credits
        user, _ = users.create_user("cofounder@example.com", role="cofounder", conn=conn)
        conn.execute("UPDATE users SET credits_remaining = 0 WHERE id = ?", (user.id,))
        conn.commit()

        # Attempt to create ticket should raise exception
        with pytest.raises(tickets.InsufficientCreditsError):
            tickets.create_ticket(
                user_id=user.id,
                ticket_type="bug",
                title="Test bug",
                description="Description",
                conn=conn
            )

    def test_get_tickets_returns_own(self, conn):
        """Task 15: Verify get_tickets(user_id) returns only user's own tickets."""
        from src import tickets

        # Create two users
        user1, _ = users.create_user("user1@example.com", role="cofounder", conn=conn)
        user2, _ = users.create_user("user2@example.com", role="cofounder", conn=conn)

        # Give them credits
        conn.execute("UPDATE users SET credits_remaining = 10 WHERE id IN (?, ?)", (user1.id, user2.id))
        conn.commit()

        # Create tickets for each user
        ticket1_id = tickets.create_ticket(user1.id, "bug", "User 1 bug", "Description", conn=conn)
        ticket2_id = tickets.create_ticket(user2.id, "idea", "User 2 idea", "Description", conn=conn)

        # Get tickets for user1
        user1_tickets = tickets.get_tickets(user1.id, conn=conn)

        # Verify user1 only sees their own ticket
        assert len(user1_tickets) == 1
        assert user1_tickets[0]["id"] == ticket1_id
        assert user1_tickets[0]["title"] == "User 1 bug"

    def test_get_all_tickets_returns_all(self, conn):
        """Task 15: Verify get_all_tickets() returns all tickets."""
        from src import tickets

        # Create two users
        user1, _ = users.create_user("user1@example.com", role="cofounder", conn=conn)
        user2, _ = users.create_user("user2@example.com", role="cofounder", conn=conn)

        # Give them credits
        conn.execute("UPDATE users SET credits_remaining = 10 WHERE id IN (?, ?)", (user1.id, user2.id))
        conn.commit()

        # Create tickets for each user
        ticket1_id = tickets.create_ticket(user1.id, "bug", "User 1 bug", "Description", conn=conn)
        ticket2_id = tickets.create_ticket(user2.id, "idea", "User 2 idea", "Description", conn=conn)

        # Get all tickets
        all_tickets = tickets.get_all_tickets(conn=conn)

        # Verify both tickets are returned
        assert len(all_tickets) == 2
        ticket_ids = {t["id"] for t in all_tickets}
        assert ticket1_id in ticket_ids
        assert ticket2_id in ticket_ids

    def test_add_comment(self, conn):
        """Task 17: Verify add_comment() creates a comment."""
        from src import tickets

        # Create a user and ticket
        user, _ = users.create_user("cofounder@example.com", role="cofounder", conn=conn)
        conn.execute("UPDATE users SET credits_remaining = 10 WHERE id = ?", (user.id,))
        conn.commit()

        ticket_id = tickets.create_ticket(user.id, "bug", "Test bug", "Description", conn=conn)

        # Add a comment
        comment_id = tickets.add_comment(
            ticket_id=ticket_id,
            user_id=user.id,
            body="This is a comment",
            conn=conn
        )

        # Verify comment was created
        assert comment_id is not None
        comment_row = conn.execute("SELECT * FROM ticket_comments WHERE id = ?", (comment_id,)).fetchone()
        assert comment_row is not None
        assert comment_row["ticket_id"] == ticket_id
        assert comment_row["user_id"] == user.id
        assert comment_row["body"] == "This is a comment"

    def test_get_comments(self, conn):
        """Task 17: Verify get_comments() returns all comments for a ticket."""
        from src import tickets

        # Create a user and ticket
        user, _ = users.create_user("cofounder@example.com", role="cofounder", conn=conn)
        conn.execute("UPDATE users SET credits_remaining = 10 WHERE id = ?", (user.id,))
        conn.commit()

        ticket_id = tickets.create_ticket(user.id, "bug", "Test bug", "Description", conn=conn)

        # Add multiple comments
        comment1_id = tickets.add_comment(ticket_id, user.id, "First comment", conn=conn)
        comment2_id = tickets.add_comment(ticket_id, user.id, "Second comment", conn=conn)

        # Get comments
        comments = tickets.get_comments(ticket_id, conn=conn)

        # Verify both comments are returned
        assert len(comments) == 2
        assert comments[0]["body"] == "First comment"
        assert comments[1]["body"] == "Second comment"
