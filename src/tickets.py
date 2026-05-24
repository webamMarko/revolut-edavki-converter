"""Ticket and credit management for co-founder role.

Handles ticket CRUD operations, credit system (weekly reset), and Paperclip integration.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from . import users


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class InsufficientCreditsError(Exception):
    """Raised when a user tries to create a ticket but has 0 credits."""
    pass


# ---------------------------------------------------------------------------
# Credit management
# ---------------------------------------------------------------------------

def ensure_credits(user_id: int, conn: sqlite3.Connection | None = None) -> int:
    """Ensure user has fresh credits. Reset to 100 if last_reset > 7 days ago or NULL.

    Returns the current credit balance after any reset.
    """
    close = conn is None
    if conn is None:
        conn = users.get_users_db()
    try:
        # Get user's current credit state
        row = conn.execute(
            "SELECT credits_remaining, credits_last_reset FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()

        if not row:
            raise ValueError(f"User {user_id} not found")

        credits_remaining = row["credits_remaining"]
        credits_last_reset = row["credits_last_reset"]

        # Determine if reset is needed
        needs_reset = False

        if credits_last_reset is None:
            # Never reset before — initialize
            needs_reset = True
        else:
            try:
                last_reset_dt = datetime.fromisoformat(credits_last_reset)
                now = datetime.now(timezone.utc)
                days_since_reset = (now - last_reset_dt).total_seconds() / 86400
                if days_since_reset >= 7:
                    needs_reset = True
            except ValueError:
                # Invalid datetime format — treat as needing reset
                needs_reset = True

        if needs_reset:
            # Get credits_per_week from system_settings (default 100)
            settings_row = conn.execute(
                "SELECT value FROM system_settings WHERE key = 'credits_per_week'"
            ).fetchone()
            credits_per_week = int(settings_row["value"]) if settings_row else 100

            # Reset credits
            now_iso = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "UPDATE users SET credits_remaining = ?, credits_last_reset = ? WHERE id = ?",
                (credits_per_week, now_iso, user_id)
            )
            conn.commit()
            return credits_per_week
        else:
            return credits_remaining
    finally:
        if close:
            conn.close()


def deduct_credit(user_id: int, conn: sqlite3.Connection | None = None) -> int:
    """Deduct 1 credit from user's balance.

    Raises InsufficientCreditsError if balance is 0.
    Returns new balance after deduction.
    """
    close = conn is None
    if conn is None:
        conn = users.get_users_db()
    try:
        # Get current balance
        row = conn.execute(
            "SELECT credits_remaining FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()

        if not row:
            raise ValueError(f"User {user_id} not found")

        current_balance = row["credits_remaining"]

        if current_balance <= 0:
            raise InsufficientCreditsError("No credits remaining")

        # Deduct 1 credit
        new_balance = current_balance - 1
        conn.execute(
            "UPDATE users SET credits_remaining = ? WHERE id = ?",
            (new_balance, user_id)
        )
        conn.commit()
        return new_balance
    finally:
        if close:
            conn.close()


# ---------------------------------------------------------------------------
# Ticket CRUD
# ---------------------------------------------------------------------------

def create_ticket(
    user_id: int,
    ticket_type: str,
    title: str,
    description: str,
    conn: sqlite3.Connection | None = None,
) -> int:
    """Create a new ticket and deduct 1 credit from the user.

    Args:
        user_id: ID of the user creating the ticket
        ticket_type: 'bug' or 'idea'
        title: Ticket title
        description: Ticket description
        conn: Database connection (optional)

    Returns:
        The ID of the created ticket

    Raises:
        InsufficientCreditsError: If user has 0 credits
        ValueError: If ticket_type is invalid
    """
    if ticket_type not in ("bug", "idea"):
        raise ValueError(f"Invalid ticket type: {ticket_type}")

    close = conn is None
    if conn is None:
        conn = users.get_users_db()
    try:
        # Deduct credit first (will raise InsufficientCreditsError if balance is 0)
        deduct_credit(user_id, conn=conn)

        # Create the ticket
        cursor = conn.execute(
            """INSERT INTO tickets (user_id, type, title, description, status)
               VALUES (?, ?, ?, ?, 'new')""",
            (user_id, ticket_type, title, description)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        if close:
            conn.close()


def get_tickets(user_id: int, conn: sqlite3.Connection | None = None) -> list[dict]:
    """Get all tickets for a specific user.

    Returns list of ticket dicts with keys: id, user_id, type, title, description,
    status, paperclip_issue_id, status_synced_at, created_at, updated_at
    """
    close = conn is None
    if conn is None:
        conn = users.get_users_db()
    try:
        rows = conn.execute(
            "SELECT * FROM tickets WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        if close:
            conn.close()


def get_all_tickets(conn: sqlite3.Connection | None = None) -> list[dict]:
    """Get all tickets (admin view).

    Returns list of ticket dicts with keys: id, user_id, type, title, description,
    status, paperclip_issue_id, status_synced_at, created_at, updated_at
    """
    close = conn is None
    if conn is None:
        conn = users.get_users_db()
    try:
        rows = conn.execute(
            "SELECT * FROM tickets ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        if close:
            conn.close()


def add_comment(
    ticket_id: int,
    user_id: int,
    body: str,
    conn: sqlite3.Connection | None = None,
) -> int:
    """Add a comment to a ticket.

    Returns the ID of the created comment.
    """
    close = conn is None
    if conn is None:
        conn = users.get_users_db()
    try:
        cursor = conn.execute(
            """INSERT INTO ticket_comments (ticket_id, user_id, body)
               VALUES (?, ?, ?)""",
            (ticket_id, user_id, body)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        if close:
            conn.close()


def get_comments(ticket_id: int, conn: sqlite3.Connection | None = None) -> list[dict]:
    """Get all comments for a ticket, ordered by creation time.

    Returns list of comment dicts with keys: id, ticket_id, user_id, body, created_at
    """
    close = conn is None
    if conn is None:
        conn = users.get_users_db()
    try:
        rows = conn.execute(
            "SELECT * FROM ticket_comments WHERE ticket_id = ? ORDER BY created_at ASC",
            (ticket_id,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        if close:
            conn.close()
