"""Audit logging for security-relevant events.

Stores events in _system/audit.db with structured fields for filtering.
"""

import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

def _default_data_dir() -> str:
    project_data = Path(__file__).resolve().parent.parent / "data"
    if project_data.is_dir():
        return str(project_data)
    return str(Path.home() / ".revolut-edavki")

_DATA_DIR = Path(os.environ.get("REVOLUT_DATA_DIR", _default_data_dir()))
_AUDIT_DB_PATH = _DATA_DIR / "_system" / "audit.db"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp  TEXT NOT NULL DEFAULT (datetime('now')),
    event_type TEXT NOT NULL,
    username   TEXT,
    ip_address TEXT,
    detail     TEXT,
    success    INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_username ON audit_log(username);
"""


def _get_audit_db() -> sqlite3.Connection:
    _AUDIT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_AUDIT_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    return conn


def log_event(
    event_type: str,
    username: str | None = None,
    ip_address: str | None = None,
    detail: str | None = None,
    success: bool = True,
) -> None:
    try:
        conn = _get_audit_db()
        conn.execute(
            "INSERT INTO audit_log (event_type, username, ip_address, detail, success) "
            "VALUES (?, ?, ?, ?, ?)",
            (event_type, username, ip_address, detail, int(success)),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def query_events(
    event_type: str | None = None,
    username: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    try:
        conn = _get_audit_db()
        sql = "SELECT * FROM audit_log WHERE 1=1"
        params: list = []
        if event_type:
            sql += " AND event_type = ?"
            params.append(event_type)
        if username:
            sql += " AND username = ?"
            params.append(username)
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(sql, params).fetchall()
        result = [
            {
                "id": r["id"],
                "timestamp": r["timestamp"],
                "event_type": r["event_type"],
                "username": r["username"],
                "ip_address": r["ip_address"],
                "detail": r["detail"],
                "success": bool(r["success"]),
            }
            for r in rows
        ]
        conn.close()
        return result
    except Exception:
        return []


def get_event_types() -> list[str]:
    try:
        conn = _get_audit_db()
        rows = conn.execute("SELECT DISTINCT event_type FROM audit_log ORDER BY event_type").fetchall()
        conn.close()
        return [r["event_type"] for r in rows]
    except Exception:
        return []
