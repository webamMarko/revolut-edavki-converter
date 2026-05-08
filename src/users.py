"""User registry for multi-user deployment.

Stores users in a separate SQLite database at $REVOLUT_DATA_DIR/_system/users.db.
Handles authentication, invite tokens, role management, and Stripe customer linking.
"""

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
    role: str                     # 'guest', 'premium', 'admin'
    password_hash: str | None
    invite_token: str | None
    invite_expires: str | None
    stripe_customer_id: str | None
    created_at: str
    last_login: str | None


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
                       CHECK(role IN ('guest', 'premium', 'admin')),
    invite_token       TEXT UNIQUE,
    invite_expires     TEXT,
    stripe_customer_id TEXT UNIQUE,
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    last_login         TEXT
);
"""


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
    return conn


def _users_db_path() -> Path:
    """Return path to users.db, respecting REVOLUT_DATA_DIR env var."""
    return _DATA_DIR / "_system" / "users.db"


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
        created_at=row["created_at"],
        last_login=row["last_login"],
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
