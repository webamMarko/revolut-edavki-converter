"""Scheduled email report delivery for premium users.

Manages report preferences per user and generates/sends portfolio summary emails.
Designed to be invoked via cron: `python -m src.cli send-reports`
"""

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .users import get_users_db, User, _row_to_user


# ---------------------------------------------------------------------------
# Report preferences schema (stored in users.db alongside user accounts)
# ---------------------------------------------------------------------------

_PREFS_SCHEMA = """
CREATE TABLE IF NOT EXISTS report_preferences (
    user_id         INTEGER PRIMARY KEY REFERENCES users(id),
    weekly_enabled  INTEGER NOT NULL DEFAULT 0,
    monthly_enabled INTEGER NOT NULL DEFAULT 1,
    alert_enabled   INTEGER NOT NULL DEFAULT 0,
    scope           TEXT NOT NULL DEFAULT 'all',
    country         TEXT NOT NULL DEFAULT 'SI',
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS report_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    report_type TEXT NOT NULL,
    sent_at     TEXT NOT NULL DEFAULT (datetime('now')),
    status      TEXT NOT NULL DEFAULT 'sent',
    error       TEXT
);
"""


def _ensure_prefs_schema(conn: sqlite3.Connection):
    conn.executescript(_PREFS_SCHEMA)
    conn.commit()


# ---------------------------------------------------------------------------
# Preferences CRUD
# ---------------------------------------------------------------------------

@dataclass
class ReportPreferences:
    user_id: int
    weekly_enabled: bool
    monthly_enabled: bool
    alert_enabled: bool
    scope: str
    country: str
    updated_at: str


def get_preferences(user_id: int, conn: sqlite3.Connection | None = None) -> ReportPreferences:
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        _ensure_prefs_schema(conn)
        row = conn.execute(
            "SELECT * FROM report_preferences WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row:
            return ReportPreferences(
                user_id=row["user_id"],
                weekly_enabled=bool(row["weekly_enabled"]),
                monthly_enabled=bool(row["monthly_enabled"]),
                alert_enabled=bool(row["alert_enabled"]),
                scope=row["scope"],
                country=row["country"],
                updated_at=row["updated_at"],
            )
        return ReportPreferences(
            user_id=user_id,
            weekly_enabled=False,
            monthly_enabled=True,
            alert_enabled=False,
            scope="all",
            country="SI",
            updated_at="",
        )
    finally:
        if close:
            conn.close()


def save_preferences(
    user_id: int,
    weekly_enabled: bool,
    monthly_enabled: bool,
    alert_enabled: bool,
    scope: str = "all",
    country: str = "SI",
    conn: sqlite3.Connection | None = None,
) -> None:
    close = conn is None
    if conn is None:
        conn = get_users_db()
    try:
        _ensure_prefs_schema(conn)
        conn.execute("""
            INSERT INTO report_preferences (user_id, weekly_enabled, monthly_enabled,
                                            alert_enabled, scope, country, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                weekly_enabled = excluded.weekly_enabled,
                monthly_enabled = excluded.monthly_enabled,
                alert_enabled = excluded.alert_enabled,
                scope = excluded.scope,
                country = excluded.country,
                updated_at = datetime('now')
        """, (user_id, int(weekly_enabled), int(monthly_enabled),
              int(alert_enabled), scope, country))
        conn.commit()
    finally:
        if close:
            conn.close()


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _user_db_path(username: str) -> Path:
    from .users import _DATA_DIR
    return _DATA_DIR / username / "portfolio.db"


def _generate_summary_for_user(username: str, scope: str, country: str) -> dict | None:
    """Generate a portfolio summary dict for a user. Returns None if no data."""
    from .db import get_connection
    from .analytics import compute_analytics

    db_path = _user_db_path(username)
    if not db_path.exists():
        return None

    conn = get_connection(db_path=db_path)
    try:
        tx_count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        if tx_count == 0:
            return None

        analytics = compute_analytics(conn, scope=scope)

        summary = {
            "total_value_eur": round(analytics.total_value_eur, 2),
            "total_invested_eur": round(analytics.total_invested_eur, 2),
            "total_gain_eur": round(analytics.total_gain_eur, 2),
            "total_return_pct": round(analytics.total_return_pct, 2),
            "day_change_eur": round(analytics.day_change_eur, 2) if hasattr(analytics, "day_change_eur") else 0,
            "day_change_pct": round(analytics.day_change_pct, 2) if hasattr(analytics, "day_change_pct") else 0,
            "positions_count": len(analytics.positions) if hasattr(analytics, "positions") else 0,
            "start_date": analytics.start_date,
            "end_date": analytics.end_date,
        }

        if hasattr(analytics, "positions") and analytics.positions:
            top_gainers = sorted(
                [p for p in analytics.positions if p.get("unrealized_gain_eur", 0) > 0],
                key=lambda p: p.get("unrealized_gain_eur", 0),
                reverse=True,
            )[:5]
            top_losers = sorted(
                [p for p in analytics.positions if p.get("unrealized_gain_eur", 0) < 0],
                key=lambda p: p.get("unrealized_gain_eur", 0),
            )[:5]
            summary["top_gainers"] = [
                {"ticker": p["ticker"], "gain_eur": round(p["unrealized_gain_eur"], 2)}
                for p in top_gainers
            ]
            summary["top_losers"] = [
                {"ticker": p["ticker"], "gain_eur": round(p["unrealized_gain_eur"], 2)}
                for p in top_losers
            ]

        return summary
    except Exception:
        return None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Email rendering
# ---------------------------------------------------------------------------

def _render_weekly_email(username: str, summary: dict) -> tuple[str, str, str]:
    """Returns (subject, html, text) for a weekly report email."""
    subject = f"Weekly Portfolio Summary — {summary['end_date']}"

    gain_sign = "+" if summary["total_gain_eur"] >= 0 else ""
    day_sign = "+" if summary.get("day_change_eur", 0) >= 0 else ""

    gainers_html = ""
    if summary.get("top_gainers"):
        gainers_html = "<h3 style='margin-top:1.5rem;font-size:0.95rem'>Top gainers</h3><ul>"
        for g in summary["top_gainers"]:
            gainers_html += f"<li><strong>{g['ticker']}</strong>: +€{g['gain_eur']:,.2f}</li>"
        gainers_html += "</ul>"

    losers_html = ""
    if summary.get("top_losers"):
        losers_html = "<h3 style='margin-top:1rem;font-size:0.95rem'>Top losers</h3><ul>"
        for l in summary["top_losers"]:
            losers_html += f"<li><strong>{l['ticker']}</strong>: €{l['gain_eur']:,.2f}</li>"
        losers_html += "</ul>"

    app_url = os.environ.get("APP_BASE_URL", "http://localhost:8083")

    html_body = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:auto;padding:32px">
      <h2 style="font-size:1.3rem;margin-bottom:0.5rem">Weekly Portfolio Summary</h2>
      <p style="color:#666;font-size:0.85rem;margin-top:0">{summary['end_date']}</p>

      <table style="width:100%;border-collapse:collapse;margin:1.5rem 0">
        <tr style="border-bottom:1px solid #eee">
          <td style="padding:8px 0;color:#666">Portfolio value</td>
          <td style="padding:8px 0;text-align:right;font-weight:700">€{summary['total_value_eur']:,.2f}</td>
        </tr>
        <tr style="border-bottom:1px solid #eee">
          <td style="padding:8px 0;color:#666">Total gain/loss</td>
          <td style="padding:8px 0;text-align:right;font-weight:700;color:{'#16a34a' if summary['total_gain_eur'] >= 0 else '#dc2626'}">
            {gain_sign}€{summary['total_gain_eur']:,.2f} ({gain_sign}{summary['total_return_pct']:.1f}%)
          </td>
        </tr>
        <tr style="border-bottom:1px solid #eee">
          <td style="padding:8px 0;color:#666">Positions</td>
          <td style="padding:8px 0;text-align:right">{summary['positions_count']}</td>
        </tr>
      </table>

      {gainers_html}
      {losers_html}

      <p style="margin-top:2rem">
        <a href="{app_url}/report"
           style="background:#f59e0b;color:#000;padding:10px 20px;border-radius:6px;
                  text-decoration:none;font-weight:700;display:inline-block">
          View full report
        </a>
      </p>

      <p style="color:#999;font-size:0.75rem;margin-top:2rem">
        You're receiving this because you enabled weekly email reports.
        Log in to change your email preferences.
      </p>
    </div>
    """

    text_body = (
        f"Weekly Portfolio Summary — {summary['end_date']}\n\n"
        f"Portfolio value: €{summary['total_value_eur']:,.2f}\n"
        f"Total gain/loss: {gain_sign}€{summary['total_gain_eur']:,.2f} ({gain_sign}{summary['total_return_pct']:.1f}%)\n"
        f"Positions: {summary['positions_count']}\n\n"
        f"View full report: {app_url}/report\n"
    )

    return subject, html_body, text_body


def _render_monthly_email(username: str, summary: dict) -> tuple[str, str, str]:
    """Returns (subject, html, text) for a monthly report email."""
    subject = f"Monthly Portfolio Report — {summary['end_date']}"

    gain_sign = "+" if summary["total_gain_eur"] >= 0 else ""
    app_url = os.environ.get("APP_BASE_URL", "http://localhost:8083")

    html_body = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:auto;padding:32px">
      <h2 style="font-size:1.3rem;margin-bottom:0.5rem">Monthly Portfolio Report</h2>
      <p style="color:#666;font-size:0.85rem;margin-top:0">{summary['end_date']}</p>

      <table style="width:100%;border-collapse:collapse;margin:1.5rem 0">
        <tr style="border-bottom:1px solid #eee">
          <td style="padding:8px 0;color:#666">Portfolio value</td>
          <td style="padding:8px 0;text-align:right;font-weight:700">€{summary['total_value_eur']:,.2f}</td>
        </tr>
        <tr style="border-bottom:1px solid #eee">
          <td style="padding:8px 0;color:#666">Total invested</td>
          <td style="padding:8px 0;text-align:right">€{summary['total_invested_eur']:,.2f}</td>
        </tr>
        <tr style="border-bottom:1px solid #eee">
          <td style="padding:8px 0;color:#666">Total gain/loss</td>
          <td style="padding:8px 0;text-align:right;font-weight:700;color:{'#16a34a' if summary['total_gain_eur'] >= 0 else '#dc2626'}">
            {gain_sign}€{summary['total_gain_eur']:,.2f} ({gain_sign}{summary['total_return_pct']:.1f}%)
          </td>
        </tr>
        <tr style="border-bottom:1px solid #eee">
          <td style="padding:8px 0;color:#666">Positions</td>
          <td style="padding:8px 0;text-align:right">{summary['positions_count']}</td>
        </tr>
      </table>

      <p style="margin-top:2rem">
        <a href="{app_url}/report"
           style="background:#f59e0b;color:#000;padding:10px 20px;border-radius:6px;
                  text-decoration:none;font-weight:700;display:inline-block">
          View detailed report
        </a>
      </p>

      <p style="color:#999;font-size:0.75rem;margin-top:2rem">
        You're receiving this because you enabled monthly email reports.
        Log in to change your email preferences.
      </p>
    </div>
    """

    text_body = (
        f"Monthly Portfolio Report — {summary['end_date']}\n\n"
        f"Portfolio value: €{summary['total_value_eur']:,.2f}\n"
        f"Total invested: €{summary['total_invested_eur']:,.2f}\n"
        f"Total gain/loss: {gain_sign}€{summary['total_gain_eur']:,.2f} ({gain_sign}{summary['total_return_pct']:.1f}%)\n"
        f"Positions: {summary['positions_count']}\n\n"
        f"View detailed report: {app_url}/report\n"
    )

    return subject, html_body, text_body


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

def _log_send(conn: sqlite3.Connection, user_id: int, report_type: str,
              status: str = "sent", error: str | None = None):
    _ensure_prefs_schema(conn)
    conn.execute(
        "INSERT INTO report_log (user_id, report_type, status, error) VALUES (?, ?, ?, ?)",
        (user_id, report_type, status, error),
    )
    conn.commit()


def send_report_to_user(user: User, report_type: str, prefs: ReportPreferences,
                        verbose: bool = False) -> bool:
    """Generate and send a report email to a single user. Returns True on success."""
    from .email_service import _send

    summary = _generate_summary_for_user(user.username, prefs.scope, prefs.country)
    if not summary:
        if verbose:
            print(f"  {user.username}: no portfolio data, skipping")
        return False

    if report_type == "weekly":
        subject, html, text = _render_weekly_email(user.username, summary)
    elif report_type == "monthly":
        subject, html, text = _render_monthly_email(user.username, summary)
    else:
        return False

    try:
        _send(user.email, subject, html, text)
        conn = get_users_db()
        try:
            _log_send(conn, user.id, report_type, "sent")
        finally:
            conn.close()
        if verbose:
            print(f"  {user.username}: {report_type} report sent to {user.email}")
        return True
    except Exception as e:
        conn = get_users_db()
        try:
            _log_send(conn, user.id, report_type, "failed", str(e))
        finally:
            conn.close()
        if verbose:
            print(f"  {user.username}: FAILED — {e}")
        return False


# ---------------------------------------------------------------------------
# Batch send (called from CLI cron command)
# ---------------------------------------------------------------------------

def send_reports(report_type: str, verbose: bool = False) -> tuple[int, int]:
    """Send reports to all eligible users. Returns (sent_count, failed_count)."""
    conn = get_users_db()
    try:
        _ensure_prefs_schema(conn)

        if report_type == "weekly":
            col = "weekly_enabled"
        elif report_type == "monthly":
            col = "monthly_enabled"
        else:
            raise ValueError(f"Unknown report type: {report_type}")

        rows = conn.execute(f"""
            SELECT u.* FROM users u
            JOIN report_preferences rp ON rp.user_id = u.id
            WHERE u.role IN ('premium', 'admin')
              AND u.password_hash IS NOT NULL
              AND rp.{col} = 1
        """).fetchall()

        if not rows:
            if verbose:
                print(f"No users subscribed to {report_type} reports.")
            return (0, 0)

        if verbose:
            print(f"Sending {report_type} reports to {len(rows)} user(s)...")

        sent = 0
        failed = 0
        for row in rows:
            user = _row_to_user(row)
            prefs = get_preferences(user.id, conn=conn)
            if send_report_to_user(user, report_type, prefs, verbose=verbose):
                sent += 1
            else:
                failed += 1

        return (sent, failed)
    finally:
        conn.close()
