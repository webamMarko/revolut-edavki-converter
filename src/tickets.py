"""Ticket and credit management for co-founder role.

Handles ticket CRUD operations, credit system (weekly reset), and Paperclip integration.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

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

    Also attempts to create a Paperclip issue (async). If Paperclip API call
    fails, the ticket is still created locally.

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
        ticket_id = cursor.lastrowid

        # Attempt to create Paperclip issue (non-blocking)
        paperclip_issue_id = create_paperclip_issue(ticket_id, title, description)
        if paperclip_issue_id:
            conn.execute(
                "UPDATE tickets SET paperclip_issue_id = ?, status_synced_at = datetime('now') WHERE id = ?",
                (paperclip_issue_id, ticket_id)
            )
            conn.commit()

        return ticket_id
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


# ---------------------------------------------------------------------------
# Paperclip integration
# ---------------------------------------------------------------------------

def create_paperclip_issue(ticket_id: int, ticket_title: str, ticket_description: str) -> str | None:
    """Create a Paperclip issue for a ticket.

    Calls Paperclip API to create an issue and returns the issue ID.
    If API call fails, returns None and logs the error.

    Args:
        ticket_id: Internal ticket ID (for reference)
        ticket_title: Ticket title
        ticket_description: Ticket description

    Returns:
        Paperclip issue ID if successful, None if failed
    """
    import os
    import requests

    paperclip_url = os.environ.get("PAPERCLIP_API_URL")
    paperclip_key = os.environ.get("PAPERCLIP_API_KEY")
    paperclip_company_id = os.environ.get("PAPERCLIP_COMPANY_ID")
    agent_id = os.environ.get("PAPERCLIP_AGENT_ID")

    if not (paperclip_url and paperclip_key and paperclip_company_id and agent_id):
        # Paperclip not configured; silently skip
        return None

    try:
        headers = {
            "Authorization": f"Bearer {paperclip_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "title": f"[{('Bug' if 'bug' in ticket_title.lower() else 'Idea')}] {ticket_title}",
            "description": ticket_description,
            "assigneeAgentId": agent_id,
            "status": "todo",
        }

        response = requests.post(
            f"{paperclip_url}/api/companies/{paperclip_company_id}/issues",
            headers=headers,
            json=payload,
            timeout=10,
        )

        if response.status_code == 201:
            data = response.json()
            return data.get("id")
        else:
            # API error; log and return None
            return None
    except Exception:
        # Network error, timeout, etc.; silently skip
        return None


def sync_ticket_status_from_paperclip(ticket_id: int, conn: sqlite3.Connection | None = None) -> bool:
    """Sync ticket status from Paperclip (if status_synced_at is stale, >60s).

    Returns True if status was updated, False otherwise.
    """
    import os
    import requests

    close = conn is None
    if conn is None:
        conn = users.get_users_db()

    try:
        # Get ticket with paperclip_issue_id
        ticket = conn.execute(
            "SELECT id, paperclip_issue_id, status_synced_at FROM tickets WHERE id = ?",
            (ticket_id,)
        ).fetchone()

        if not ticket or not ticket["paperclip_issue_id"]:
            return False

        # Check if sync is needed (>60 seconds old)
        if ticket["status_synced_at"]:
            last_sync = datetime.fromisoformat(ticket["status_synced_at"])
            if (datetime.now(timezone.utc) - last_sync).total_seconds() < 60:
                return False

        paperclip_url = os.environ.get("PAPERCLIP_API_URL")
        paperclip_key = os.environ.get("PAPERCLIP_API_KEY")

        if not (paperclip_url and paperclip_key):
            return False

        headers = {"Authorization": f"Bearer {paperclip_key}"}

        response = requests.get(
            f"{paperclip_url}/api/issues/{ticket['paperclip_issue_id']}",
            headers=headers,
            timeout=10,
        )

        if response.status_code == 200:
            data = response.json()
            paperclip_status = data.get("status", "todo")

            # Map Paperclip status to local status
            local_status = "done" if paperclip_status == "done" else "in_progress" if paperclip_status == "in_progress" else "new"

            # Update ticket status and sync timestamp
            conn.execute(
                """UPDATE tickets SET status = ?, status_synced_at = datetime('now') WHERE id = ?""",
                (local_status, ticket_id)
            )
            conn.commit()
            return True
    finally:
        if close:
            conn.close()

    return False
