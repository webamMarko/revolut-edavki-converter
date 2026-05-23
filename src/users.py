"""User registry for multi-user deployment.

Stores users in a separate SQLite database at $REVOLUT_DATA_DIR/_system/users.db.
Handles authentication, invite tokens, role management, and Stripe customer linking.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

def _default_data_dir() -> str:
    project_data = Path(__file__).resolve().parent.parent / "data"
    if project_data.is_dir():
        return str(project_data)
    return str(Path.home() / ".revolut-edavki")

_DATA_DIR = Path(os.environ.get("REVOLUT_DATA_DIR", _default_data_dir()))
_USERS_DB_PATH = _DATA_DIR / "_system" / "users.db"

INVITE_TTL_HOURS = 24
PBKDF2_ITERATIONS = 260_000


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class User:
    id: int
    username: str
    email: str
    role: str                     # 'guest', 'premium', 'admin', 'cofounder'
    password_hash: str | None
    invite_token: str | None
    invite_expires: str | None
    stripe_customer_id: str | None
    stripe_subscription_status: str | None
    credits_remaining: int = 0
    credits_last_reset: str | None = None
    created_at: str = ""
    last_login: str | None = None
    onboarding_completed: int = 0     # 0=not completed, 1=completed


# ---------------------------------------------------------------------------
# DB connection + schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    username           TEXT NOT NULL UNIQUE,
    email              TEXT NOT NULL UNIQUE,
    password_hash      TEXT,
    role               TEXT NOT NULL DEFAULT 'premium'
                       CHECK(role IN ('guest', 'premium', 'admin', 'cofounder')),
    invite_token       TEXT UNIQUE,
    invite_expires     TEXT,
    stripe_customer_id TEXT UNIQUE,
    stripe_subscription_status TEXT,
    credits_remaining  INTEGER NOT NULL DEFAULT 0,
    credits_last_reset TEXT,
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    last_login         TEXT
);

CREATE TABLE IF NOT EXISTS portfolio_shares (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    share_token     TEXT NOT NULL UNIQUE,
    label           TEXT,
    scope           TEXT NOT NULL DEFAULT 'all',
    percentage_only INTEGER NOT NULL DEFAULT 1,
    include_holdings INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at      TEXT,
    access_count    INTEGER NOT NULL DEFAULT 0,
    last_accessed_at TEXT
);

CREATE TABLE IF NOT EXISTS magic_login_tokens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token       TEXT NOT NULL UNIQUE,
    expires_at  TEXT NOT NULL,
    used_at     TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    token               TEXT PRIMARY KEY,
    user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    username            TEXT NOT NULL,
    role                TEXT NOT NULL,
    active_portfolio_id INTEGER NOT NULL DEFAULT 1,
    expires_at          TEXT NOT NULL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token      TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    used_at    TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS system_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tickets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    type            TEXT NOT NULL CHECK(type IN ('bug', 'idea')),
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new', 'in_progress', 'done')),
    paperclip_issue_id TEXT,
    status_synced_at TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ticket_comments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id   INTEGER NOT NULL REFERENCES tickets(id),
    user_id     INTEGER NOT NULL REFERENCES users(id),
    body        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Migration: add columns that may not exist in older DBs
_MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN stripe_subscription_status TEXT",
    "ALTER TABLE users ADD COLUMN onboarding_completed INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE sessions ADD COLUMN active_portfolio_id INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE users ADD COLUMN credits_remaining INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE users ADD COLUMN credits_last_reset TEXT",
]

# Default system settings
_DEFAULT_SETTINGS = {
    "cofounder_price_eur": "249",
    "bug_token_multiplier": "5000",
    "idea_token_multiplier": "10000",
    "credits_per_week": "100",
}


def _init_default_settings(conn: sqlite3.Connection) -> None:
    """Initialize default system settings if they don't exist."""
    for key, value in _DEFAULT_SETTINGS.items():
        try:
            conn.execute(
                "INSERT OR IGNORE INTO system_settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        except sqlite3.OperationalError:
            # system_settings table might not exist in older schemas
            pass
    conn.commit()


def get_users_db() -> sqlite3.Connection:
    """Return a connection to the user registry database, creating it if needed."""
    path = _users_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    # Apply additive migrations (ignore errors for already-existing columns)
    for sql in _MIGRATIONS:
        try:
            conn.execute(sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass
    # Initialize default system settings
    _init_default_settings(conn)
    return conn


def get_users_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Return a connection to a users database (for testing with custom paths)."""
    if db_path is None:
        return get_users_db()

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    # Apply additive migrations (ignore errors for already-existing columns)
    for sql in _MIGRATIONS:
        try:
            conn.execute(sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass
    return conn


def _users_db_path() -> Path:
    """Return path to users.db, respecting REVOLUT_DATA_DIR env var."""
    return _DATA_DIR / "_system" / "users.db"


def _user_db_path(username: str) -> Path:
    """Return path to a user's portfolio.db."""
    return _DATA_DIR / username / "portfolio.db"


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        email=row["email"],
        role=row["role"],
        password_hash=row["password_hash"],
        invite_token=row["invite_token"],
        invite_expires=row["invite_expires"],
        stripe_customer_id=row["stripe_customer_id"],
        stripe_subscription_status=row["stripe_subscription_status"] if "stripe_subscription_status" in row.keys() else None,
        created_at=row["created_at"],
        last_login=row["last_login"],
        onboarding_completed=row["onboarding_completed"] if "onboarding_completed" in row.keys() else 0,
    )


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Return a storable PBKDF2 hash string: base64salt:hexhash"""
    import base64
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return base64.b64encode(salt).decode() + ":" + digest.hex()


def verify_password(stored_hash: str, provided: str) -> bool:
    """Constant-time PBKDF2 verification."""
    import base64
    try:
        salt_b64, hex_hash = stored_hash.split(":", 1)
        salt = base64.b64decode(salt_b64)
        check = hashlib.pbkdf2_hmac("sha256", provided.encode(), salt, PBKDF2_ITERATIONS).hex()
        return secrets.compare_digest(check, hex_hash)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# User creation
# ---------------------------------------------------------------------------

def _generate_username(email: str, conn: sqlite3.Connection) -> str:
    """Derive a unique username from the email local part."""
    base = email.split("@")[0].lower()
    # Keep only alphanumeric + underscore
    base = "".join(c if c.isalnum() or c == "_" else "_" for c in base)
    base = base[:30] or "user"
    candidate = base
    suffix = 2
    while conn.execute("SELECT 1 FROM users WHERE username = ?", (candidate,)).fetchone():
        candidate = f"{base}{suffix}"
        suffix += 1
    return candidate


def create_user(
    email: str,
    role: str = "premium",
    conn: sqlite3.Connection | None = None,
) -> tuple[User, str]:
    """Create a new user account and return (User, raw_invite_token).

    The invite token is returned raw (unhashed) so it can be emailed.
    It is stored as-is in the DB (it's a cryptographically random token,
    not a secret that needs hashing).
    """
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        username = _generate_username(email, conn)
        raw_token = secrets.token_urlsafe(32)
        expires = (datetime.now(timezone.utc) + timedelta(hours=INVITE_TTL_HOURS)).isoformat()
        conn.execute(
            """INSERT INTO users (username, email, role, invite_token, invite_expires)
               VALUES (?, ?, ?, ?, ?)""",
            (username, email, role, raw_token, expires),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return _row_to_user(row), raw_token
    finally:
        if close:
            conn.close()


def create_stripe_user(
    email: str,
    stripe_customer_id: str,
    conn: sqlite3.Connection | None = None,
) -> tuple[User, str]:
    """Create a premium user from a Stripe checkout event. Returns (User, raw_invite_token)."""
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        # Idempotent: if the stripe_customer_id already exists, just return the existing user
        existing = conn.execute(
            "SELECT * FROM users WHERE stripe_customer_id = ?", (stripe_customer_id,)
        ).fetchone()
        if existing:
            user = _row_to_user(existing)
            # Re-issue an invite token if they haven't set a password yet
            if not user.password_hash:
                raw_token = secrets.token_urlsafe(32)
                expires = (datetime.now(timezone.utc) + timedelta(hours=INVITE_TTL_HOURS)).isoformat()
                conn.execute(
                    "UPDATE users SET invite_token = ?, invite_expires = ? WHERE id = ?",
                    (raw_token, expires, user.id),
                )
                conn.commit()
                return _row_to_user(conn.execute("SELECT * FROM users WHERE id = ?", (user.id,)).fetchone()), raw_token
            return user, ""

        username = _generate_username(email, conn)
        raw_token = secrets.token_urlsafe(32)
        expires = (datetime.now(timezone.utc) + timedelta(hours=INVITE_TTL_HOURS)).isoformat()
        conn.execute(
            """INSERT INTO users (username, email, role, invite_token, invite_expires, stripe_customer_id)
               VALUES (?, ?, 'premium', ?, ?, ?)""",
            (username, email, raw_token, expires, stripe_customer_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return _row_to_user(row), raw_token
    finally:
        if close:
            conn.close()


# ---------------------------------------------------------------------------
# Invite acceptance
# ---------------------------------------------------------------------------

def accept_invite(
    raw_token: str,
    password: str,
    conn: sqlite3.Connection | None = None,
) -> User | None:
    """Validate invite token, set password, clear token. Returns User or None if invalid/expired."""
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE invite_token = ?", (raw_token,)
        ).fetchone()
        if not row:
            return None
        # Check expiry
        if row["invite_expires"]:
            try:
                expires = datetime.fromisoformat(row["invite_expires"])
                if datetime.now(timezone.utc) > expires:
                    return None
            except ValueError:
                return None
        pw_hash = hash_password(password)
        conn.execute(
            "UPDATE users SET password_hash = ?, invite_token = NULL, invite_expires = NULL WHERE id = ?",
            (pw_hash, row["id"]),
        )
        conn.commit()
        return _row_to_user(conn.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone())
    finally:
        if close:
            conn.close()


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def authenticate(
    username_or_email: str,
    password: str,
    conn: sqlite3.Connection | None = None,
) -> User | None:
    """Verify credentials. Returns User on success, None on failure."""
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? OR email = ?",
            (username_or_email, username_or_email),
        ).fetchone()
        if not row or not row["password_hash"]:
            return None
        if not verify_password(row["password_hash"], password):
            return None
        # Update last_login
        conn.execute(
            "UPDATE users SET last_login = datetime('now') WHERE id = ?", (row["id"],)
        )
        conn.commit()
        return _row_to_user(conn.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone())
    finally:
        if close:
            conn.close()


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

def get_user_by_id(user_id: int, conn: sqlite3.Connection | None = None) -> User | None:
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_user(row) if row else None
    finally:
        if close:
            conn.close()


def get_user_by_email(email: str, conn: sqlite3.Connection | None = None) -> User | None:
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return _row_to_user(row) if row else None
    finally:
        if close:
            conn.close()


def get_user_by_invite_token(token: str, conn: sqlite3.Connection | None = None) -> User | None:
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE invite_token = ?", (token,)).fetchone()
        return _row_to_user(row) if row else None
    finally:
        if close:
            conn.close()


def list_users(conn: sqlite3.Connection | None = None) -> list[User]:
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        return [_row_to_user(r) for r in rows]
    finally:
        if close:
            conn.close()


# ---------------------------------------------------------------------------
# Role management
# ---------------------------------------------------------------------------

def set_role(user_id: int, role: str, conn: sqlite3.Connection | None = None) -> bool:
    """Set a user's role. Returns True if a row was updated."""
    if role not in ("guest", "premium", "admin"):
        raise ValueError(f"Invalid role: {role}")
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        cursor = conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        if close:
            conn.close()


# ---------------------------------------------------------------------------
# Bootstrap: ensure at least one admin exists
# ---------------------------------------------------------------------------

def ensure_bootstrap_admin(
    email: str,
    password: str,
    conn: sqlite3.Connection | None = None,
) -> User:
    """Create the first admin account if no admin exists yet.

    Called from scripts/hash_password.py or on first startup.
    Does nothing if an admin already exists.
    """
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        existing_admin = conn.execute(
            "SELECT * FROM users WHERE role = 'admin' LIMIT 1"
        ).fetchone()
        if existing_admin:
            return _row_to_user(existing_admin)

        username = _generate_username(email, conn)
        pw_hash = hash_password(password)
        conn.execute(
            """INSERT INTO users (username, email, password_hash, role)
               VALUES (?, ?, ?, 'admin')""",
            (username, email, pw_hash),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return _row_to_user(row)
    finally:
        if close:
            conn.close()


# ---------------------------------------------------------------------------
# Portfolio sharing
# ---------------------------------------------------------------------------

@dataclass
class PortfolioShare:
    id: int
    user_id: int
    share_token: str
    label: str | None
    scope: str
    percentage_only: bool
    include_holdings: bool
    created_at: str
    expires_at: str | None
    access_count: int
    last_accessed_at: str | None


def _row_to_share(row: sqlite3.Row) -> PortfolioShare:
    return PortfolioShare(
        id=row["id"],
        user_id=row["user_id"],
        share_token=row["share_token"],
        label=row["label"],
        scope=row["scope"],
        percentage_only=bool(row["percentage_only"]),
        include_holdings=bool(row["include_holdings"]),
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        access_count=row["access_count"],
        last_accessed_at=row["last_accessed_at"],
    )


def create_share(
    user_id: int,
    label: str | None = None,
    scope: str = "all",
    percentage_only: bool = True,
    include_holdings: bool = False,
    expires_hours: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> PortfolioShare:
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        token = secrets.token_urlsafe(32)
        expires_at = None
        if expires_hours:
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=expires_hours)).isoformat()
        conn.execute(
            """INSERT INTO portfolio_shares
               (user_id, share_token, label, scope, percentage_only, include_holdings, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, token, label, scope, int(percentage_only), int(include_holdings), expires_at),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM portfolio_shares WHERE share_token = ?", (token,)).fetchone()
        return _row_to_share(row)
    finally:
        if close:
            conn.close()


def get_share_by_token(
    token: str,
    conn: sqlite3.Connection | None = None,
) -> PortfolioShare | None:
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        row = conn.execute("SELECT * FROM portfolio_shares WHERE share_token = ?", (token,)).fetchone()
        if not row:
            return None
        share = _row_to_share(row)
        if share.expires_at:
            try:
                expires = datetime.fromisoformat(share.expires_at)
                if datetime.now(timezone.utc) > expires:
                    return None
            except ValueError:
                return None
        conn.execute(
            "UPDATE portfolio_shares SET access_count = access_count + 1, last_accessed_at = datetime('now') WHERE id = ?",
            (share.id,),
        )
        conn.commit()
        return share
    finally:
        if close:
            conn.close()


def list_shares(
    user_id: int,
    conn: sqlite3.Connection | None = None,
) -> list[PortfolioShare]:
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        rows = conn.execute(
            "SELECT * FROM portfolio_shares WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [_row_to_share(r) for r in rows]
    finally:
        if close:
            conn.close()


def delete_share(
    share_id: int,
    user_id: int,
    conn: sqlite3.Connection | None = None,
) -> bool:
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        cursor = conn.execute(
            "DELETE FROM portfolio_shares WHERE id = ? AND user_id = ?",
            (share_id, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        if close:
            conn.close()


# ---------------------------------------------------------------------------
# Magic login tokens (one-click login links in digest emails)
# ---------------------------------------------------------------------------

MAGIC_TOKEN_TTL_HOURS = 72


def create_magic_token(
    user_id: int,
    conn: sqlite3.Connection | None = None,
) -> str:
    """Create a single-use magic login token. Returns the raw token string."""
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        raw_token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=MAGIC_TOKEN_TTL_HOURS)).isoformat()
        conn.execute(
            "INSERT INTO magic_login_tokens (user_id, token, expires_at) VALUES (?, ?, ?)",
            (user_id, raw_token, expires_at),
        )
        conn.commit()
        return raw_token
    finally:
        if close:
            conn.close()


def consume_magic_token(
    token: str,
    conn: sqlite3.Connection | None = None,
) -> User | None:
    """Validate and consume a magic login token. Returns User or None if invalid/expired/used."""
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT * FROM magic_login_tokens WHERE token = ?", (token,)
        ).fetchone()
        if not row:
            return None
        if row["used_at"]:
            return None
        try:
            expires = datetime.fromisoformat(row["expires_at"])
            if datetime.now(timezone.utc) > expires:
                return None
        except ValueError:
            return None
        conn.execute(
            "UPDATE magic_login_tokens SET used_at = datetime('now') WHERE id = ?",
            (row["id"],),
        )
        conn.commit()
        user_row = conn.execute("SELECT * FROM users WHERE id = ?", (row["user_id"],)).fetchone()
        if not user_row:
            return None
        conn.execute(
            "UPDATE users SET last_login = datetime('now') WHERE id = ?", (row["user_id"],)
        )
        conn.commit()
        return _row_to_user(user_row)
    finally:
        if close:
            conn.close()


# ---------------------------------------------------------------------------
# Persistent sessions (SQLite-backed, survive restarts)
# ---------------------------------------------------------------------------

SESSION_TTL_SECONDS = 86400 * 7  # 7 days


def create_session(
    user,
    conn: sqlite3.Connection | None = None,
    active_portfolio_id: int = 1,
) -> str:
    """Create a persistent session token for a User. Returns the raw token."""
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=SESSION_TTL_SECONDS)).isoformat()
        conn.execute(
            "INSERT INTO sessions (token, user_id, username, role, active_portfolio_id, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
            (token, user.id, user.username, user.role, active_portfolio_id, expires_at),
        )
        conn.commit()
        return token
    finally:
        if close:
            conn.close()


def get_session(
    token: str,
    conn: sqlite3.Connection | None = None,
) -> dict | None:
    """Return session dict {user_id, username, role, active_portfolio_id} or None if missing/expired."""
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT s.*, u.role AS current_role FROM sessions s "
            "JOIN users u ON u.id = s.user_id "
            "WHERE s.token = ?",
            (token,),
        ).fetchone()
        if not row:
            return None
        try:
            expires = datetime.fromisoformat(row["expires_at"])
            if datetime.now(timezone.utc) > expires:
                conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
                conn.commit()
                return None
        except ValueError:
            return None
        # Always return the *current* role from users table (picks up role changes)
        return {
            "user_id": row["user_id"],
            "username": row["username"],
            "role": row["current_role"],
            "active_portfolio_id": row["active_portfolio_id"] if "active_portfolio_id" in row.keys() else 1,
        }
    finally:
        if close:
            conn.close()


def delete_session(
    token: str,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Delete a session (logout)."""
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
    finally:
        if close:
            conn.close()


def purge_expired_sessions(conn: sqlite3.Connection | None = None) -> int:
    """Delete all expired sessions. Returns number of rows deleted."""
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        cursor = conn.execute(
            "DELETE FROM sessions WHERE expires_at < datetime('now')"
        )
        conn.commit()
        return cursor.rowcount
    finally:
        if close:
            conn.close()


def set_active_portfolio(
    token: str,
    portfolio_id: int,
    conn: sqlite3.Connection | None = None,
) -> bool:
    """Update the active_portfolio_id for a session. Returns True on success."""
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        cursor = conn.execute(
            "UPDATE sessions SET active_portfolio_id = ? WHERE token = ?",
            (portfolio_id, token),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        if close:
            conn.close()


def _create_session(
    username: str,
    conn: sqlite3.Connection,
    active_portfolio_id: int = 1,
) -> str:
    """Internal helper for tests: create a session by username. Returns raw token."""
    user_row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not user_row:
        raise ValueError(f"User not found: {username}")
    user = _row_to_user(user_row)
    return create_session(user, conn, active_portfolio_id)


# ---------------------------------------------------------------------------
# Password reset tokens
# ---------------------------------------------------------------------------

RESET_TOKEN_TTL_HOURS = 1  # Short-lived for security


def create_password_reset_token(
    email: str,
    conn: sqlite3.Connection | None = None,
) -> str | None:
    """Create a password reset token for the given email. Returns raw token or None if user not found."""
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        user_row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not user_row:
            return None
        raw_token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=RESET_TOKEN_TTL_HOURS)).isoformat()
        conn.execute(
            "INSERT INTO password_reset_tokens (user_id, token, expires_at) VALUES (?, ?, ?)",
            (user_row["id"], raw_token, expires_at),
        )
        conn.commit()
        return raw_token
    finally:
        if close:
            conn.close()


def consume_password_reset_token(
    token: str,
    new_password: str,
    conn: sqlite3.Connection | None = None,
) -> User | None:
    """Validate reset token, set new password. Returns User on success, None otherwise."""
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT * FROM password_reset_tokens WHERE token = ?", (token,)
        ).fetchone()
        if not row:
            return None
        if row["used_at"]:
            return None
        try:
            expires = datetime.fromisoformat(row["expires_at"])
            if datetime.now(timezone.utc) > expires:
                return None
        except ValueError:
            return None
        pw_hash = hash_password(new_password)
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (pw_hash, row["user_id"]),
        )
        conn.execute(
            "UPDATE password_reset_tokens SET used_at = datetime('now') WHERE id = ?",
            (row["id"],),
        )
        conn.commit()
        user_row = conn.execute("SELECT * FROM users WHERE id = ?", (row["user_id"],)).fetchone()
        return _row_to_user(user_row) if user_row else None
    finally:
        if close:
            conn.close()


# ---------------------------------------------------------------------------
# Stripe subscription lifecycle helpers
# ---------------------------------------------------------------------------

def update_stripe_subscription_status(
    stripe_customer_id: str,
    status: str,
    conn: sqlite3.Connection | None = None,
) -> User | None:
    """Update stripe_subscription_status and adjust role based on subscription state.

    Active statuses ('active', 'trialing') → premium
    Inactive statuses ('canceled', 'unpaid', 'past_due') → guest
    Returns updated User or None if customer not found.
    """
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE stripe_customer_id = ?", (stripe_customer_id,)
        ).fetchone()
        if not row:
            return None

        active_statuses = {"active", "trialing"}
        new_role = "premium" if status in active_statuses else "guest"

        conn.execute(
            "UPDATE users SET stripe_subscription_status = ?, role = ? WHERE stripe_customer_id = ?",
            (status, new_role, stripe_customer_id),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM users WHERE stripe_customer_id = ?", (stripe_customer_id,)
        ).fetchone()
        return _row_to_user(updated) if updated else None
    finally:
        if close:
            conn.close()


def change_password(
    user_id: int,
    new_password: str,
    conn: sqlite3.Connection | None = None,
) -> bool:
    """Set a new password for the user. Returns True on success."""
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        pw_hash = hash_password(new_password)
        cursor = conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (pw_hash, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        if close:
            conn.close()


def delete_user(
    user_id: int,
    conn: sqlite3.Connection | None = None,
) -> bool:
    """Delete user account and all associated data. Returns True on success."""
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        # CASCADE deletes sessions, shares, magic_login_tokens, password_reset_tokens
        cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        if close:
            conn.close()


# ---------------------------------------------------------------------------
# Onboarding state management
# ---------------------------------------------------------------------------

def get_onboarding_status(
    user_id: int,
    conn: sqlite3.Connection | None = None,
) -> dict:
    """Get onboarding status for a user.

    Returns dict with:
    - completed: bool — whether onboarding wizard has been completed
    - hasData: bool — whether user has any portfolio data
    - hasSynced: bool — whether user has price data
    """
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT onboarding_completed FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not row:
            return {"completed": False, "hasData": False, "hasSynced": False}

        completed = bool(row["onboarding_completed"])

        # Check if user has portfolio data
        user = get_user_by_id(user_id, conn=conn)
        if not user:
            return {"completed": completed, "hasData": False, "hasSynced": False}

        from .db import get_connection
        portfolio_db = _user_db_path(user.username)

        has_data = False
        has_synced = False

        if portfolio_db.exists():
            try:
                portfolio_conn = get_connection(db_path=portfolio_db)
                # Check for transactions
                tx_count = portfolio_conn.execute(
                    "SELECT COUNT(*) as c FROM transactions"
                ).fetchone()
                has_data = tx_count["c"] > 0 if tx_count else False

                # Check for price data
                if has_data:
                    price_count = portfolio_conn.execute(
                        "SELECT COUNT(*) as c FROM prices"
                    ).fetchone()
                    has_synced = price_count["c"] > 0 if price_count else False

                portfolio_conn.close()
            except Exception:
                pass

        return {
            "completed": completed,
            "hasData": has_data,
            "hasSynced": has_synced,
        }
    finally:
        if close:
            conn.close()


def set_onboarding_completed(
    user_id: int,
    conn: sqlite3.Connection | None = None,
) -> bool:
    """Mark onboarding as completed for a user. Returns True on success."""
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        cursor = conn.execute(
            "UPDATE users SET onboarding_completed = 1 WHERE id = ?", (user_id,)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        if close:
            conn.close()
