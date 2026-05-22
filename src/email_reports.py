"""Scheduled email report delivery for premium users.

Manages report preferences per user and generates/sends portfolio summary emails.
Designed to be invoked via cron: `python -m src.cli send-reports`
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
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
    digest_enabled  INTEGER NOT NULL DEFAULT 0,
    scope           TEXT NOT NULL DEFAULT 'all',
    country         TEXT NOT NULL DEFAULT 'SI',
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS report_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    report_type     TEXT NOT NULL,
    sent_at         TEXT NOT NULL DEFAULT (datetime('now')),
    status          TEXT NOT NULL DEFAULT 'sent',
    error           TEXT,
    portfolio_value REAL
);
"""

_MIGRATE_SQL = """
ALTER TABLE report_preferences ADD COLUMN digest_enabled INTEGER NOT NULL DEFAULT 0;
"""

_MIGRATE_LOG_SQL = """
ALTER TABLE report_log ADD COLUMN portfolio_value REAL;
"""


def _ensure_prefs_schema(conn: sqlite3.Connection):
    conn.executescript(_PREFS_SCHEMA)
    conn.commit()
    # Idempotent migrations for columns added after initial schema creation
    for migration in (_MIGRATE_SQL, _MIGRATE_LOG_SQL):
        try:
            conn.executescript(migration)
            conn.commit()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Preferences CRUD
# ---------------------------------------------------------------------------

@dataclass
class ReportPreferences:
    user_id: int
    weekly_enabled: bool
    monthly_enabled: bool
    alert_enabled: bool
    digest_enabled: bool
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
                digest_enabled=bool(row["digest_enabled"]) if "digest_enabled" in row.keys() else False,
                scope=row["scope"],
                country=row["country"],
                updated_at=row["updated_at"],
            )
        return ReportPreferences(
            user_id=user_id,
            weekly_enabled=False,
            monthly_enabled=True,
            alert_enabled=False,
            digest_enabled=False,
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
    digest_enabled: bool = False,
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
                                            alert_enabled, digest_enabled, scope, country, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                weekly_enabled = excluded.weekly_enabled,
                monthly_enabled = excluded.monthly_enabled,
                alert_enabled = excluded.alert_enabled,
                digest_enabled = excluded.digest_enabled,
                scope = excluded.scope,
                country = excluded.country,
                updated_at = datetime('now')
        """, (user_id, int(weekly_enabled), int(monthly_enabled),
              int(alert_enabled), int(digest_enabled), scope, country))
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


def _get_last_digest_value(user_id: int, conn: sqlite3.Connection) -> float | None:
    """Return the portfolio value recorded in the most recent digest sent to this user."""
    _ensure_prefs_schema(conn)
    row = conn.execute("""
        SELECT portfolio_value FROM report_log
        WHERE user_id = ? AND report_type = 'digest' AND status = 'sent'
          AND portfolio_value IS NOT NULL
        ORDER BY sent_at DESC LIMIT 1
    """, (user_id,)).fetchone()
    return float(row["portfolio_value"]) if row and row["portfolio_value"] else None


def _get_top_movers(username: str, scope: str) -> tuple[list[dict], list[dict]]:
    """Return (top_3_gainers, top_3_losers) sorted by pct change, each with ticker+pct."""
    from .db import get_connection
    from .analytics import compute_analytics
    from .users import _DATA_DIR

    db_path = _DATA_DIR / username / "portfolio.db"
    if not db_path.exists():
        return [], []
    conn = get_connection(db_path=db_path)
    try:
        analytics = compute_analytics(conn, scope=scope)
        positions = analytics.positions
        gainers = sorted(
            [p for p in positions if p.unrealized_gain_pct > 0],
            key=lambda p: p.unrealized_gain_pct, reverse=True,
        )[:3]
        losers = sorted(
            [p for p in positions if p.unrealized_gain_pct < 0],
            key=lambda p: p.unrealized_gain_pct,
        )[:3]
        return (
            [{"ticker": p.ticker, "pct": round(p.unrealized_gain_pct, 1), "eur": round(p.unrealized_gain_eur, 2)} for p in gainers],
            [{"ticker": p.ticker, "pct": round(p.unrealized_gain_pct, 1), "eur": round(p.unrealized_gain_eur, 2)} for p in losers],
        )
    except Exception:
        return [], []
    finally:
        conn.close()


def _get_tax_events(username: str, scope: str, country: str) -> list[dict]:
    """Return upcoming tax bracket anniversaries within 30 days (holdings that will drop a rate bracket)."""
    from .db import get_connection
    from .analytics import compute_analytics
    from .users import _DATA_DIR
    from .tax_regimes import get_regime, get_tax_rate

    db_path = _DATA_DIR / username / "portfolio.db"
    if not db_path.exists():
        return []
    conn = get_connection(db_path=db_path)
    try:
        analytics = compute_analytics(conn, scope=scope)
        regime = get_regime(country)
        today = datetime.now()
        window_end = today + timedelta(days=30)
        events = []

        for ticker, lots in analytics.position_lots.items():
            if ticker.startswith("CFD:"):
                brackets = regime.cfd_brackets
            elif ticker.startswith("CRYPTO:"):
                brackets = regime.crypto_brackets
            elif ticker.startswith("SAVINGS:"):
                brackets = regime.savings_brackets
            else:
                brackets = regime.stock_brackets

            sorted_brackets = sorted(brackets, key=lambda b: b.min_years)
            for lot_qty, lot_cost, lot_date in lots:
                if not lot_date:
                    continue
                try:
                    buy_dt = datetime.strptime(lot_date, "%Y-%m-%d")
                except ValueError:
                    continue
                current_years = (today - buy_dt).days / 365.25
                current_rate = get_tax_rate(brackets, current_years)
                for bracket in sorted_brackets:
                    if bracket.min_years <= current_years:
                        continue
                    anniversary_dt = buy_dt + timedelta(days=int(bracket.min_years * 365.25))
                    if today <= anniversary_dt <= window_end:
                        new_rate = bracket.rate
                        if new_rate < current_rate:
                            days_away = (anniversary_dt - today).days
                            events.append({
                                "ticker": ticker,
                                "date": anniversary_dt.strftime("%Y-%m-%d"),
                                "days_away": days_away,
                                "from_rate_pct": round(current_rate * 100, 0),
                                "to_rate_pct": round(new_rate * 100, 0),
                            })
                        break  # only report first upcoming bracket for this lot
        # Deduplicate by ticker+date, keep lowest days_away
        seen = {}
        for ev in sorted(events, key=lambda e: e["days_away"]):
            key = (ev["ticker"], ev["date"])
            if key not in seen:
                seen[key] = ev
        return list(seen.values())[:5]
    except Exception:
        return []
    finally:
        conn.close()


def _get_harvest_summary(username: str, scope: str, country: str) -> list[dict]:
    """Return top-3 harvest opportunities (ticker, loss, potential saving)."""
    from .db import get_connection
    from .harvest import compute_harvest_suggestions
    from .users import _DATA_DIR

    db_path = _DATA_DIR / username / "portfolio.db"
    if not db_path.exists():
        return []
    conn = get_connection(db_path=db_path)
    try:
        report = compute_harvest_suggestions(conn, year=datetime.now().year, scope=scope, country=country)
        results = []
        for s in report.suggestions[:3]:
            results.append({
                "ticker": s.ticker,
                "loss_eur": round(s.unrealized_loss_eur, 2),
                "saving_eur": round(s.potential_tax_saving_eur, 2),
                "wash_risk": s.wash_sale_risk,
            })
        return results
    except Exception:
        return []
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Email rendering
# ---------------------------------------------------------------------------

def _render_weekly_email(username: str, summary: dict) -> tuple[str, str, str]:
    """Returns (subject, html, text) for a weekly report email."""
    subject = f"Weekly Portfolio Summary — {summary['end_date']}"

    gain_sign = "+" if summary["total_gain_eur"] >= 0 else ""

    gainers_html = ""
    if summary.get("top_gainers"):
        gainers_html = "<h3 style='margin-top:1.5rem;font-size:0.95rem'>Top gainers</h3><ul>"
        for g in summary["top_gainers"]:
            gainers_html += f"<li><strong>{g['ticker']}</strong>: +€{g['gain_eur']:,.2f}</li>"
        gainers_html += "</ul>"

    losers_html = ""
    if summary.get("top_losers"):
        losers_html = "<h3 style='margin-top:1rem;font-size:0.95rem'>Top losers</h3><ul>"
        for loser in summary["top_losers"]:
            losers_html += f"<li><strong>{loser['ticker']}</strong>: €{loser['gain_eur']:,.2f}</li>"
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


def _render_digest_email(
    user: "User",
    summary: dict,
    last_value: float | None,
    top_gainers: list[dict],
    top_losers: list[dict],
    tax_events: list[dict],
    harvest_opps: list[dict],
    magic_url: str,
    is_premium: bool,
) -> tuple[str, str, str]:
    """Returns (subject, html, text) for the weekly portfolio digest."""
    subject = f"📊 Your weekly portfolio digest — {summary['end_date']}"

    app_url = os.environ.get("APP_BASE_URL", "http://localhost:8083")
    gain_sign = "+" if summary["total_gain_eur"] >= 0 else ""
    gain_color = "#16a34a" if summary["total_gain_eur"] >= 0 else "#dc2626"

    # Week-over-week delta
    wow_html = ""
    wow_text = ""
    if last_value and last_value > 0:
        wow_eur = summary["total_value_eur"] - last_value
        wow_pct = wow_eur / last_value * 100
        wow_sign = "+" if wow_eur >= 0 else ""
        wow_color = "#16a34a" if wow_eur >= 0 else "#dc2626"
        wow_html = f"""
        <tr style="border-bottom:1px solid #eee">
          <td style="padding:8px 0;color:#666">vs last digest</td>
          <td style="padding:8px 0;text-align:right;font-weight:700;color:{wow_color}">
            {wow_sign}€{wow_eur:,.2f} ({wow_sign}{wow_pct:.1f}%)
          </td>
        </tr>"""
        wow_text = f"vs last digest: {wow_sign}€{wow_eur:,.2f} ({wow_sign}{wow_pct:.1f}%)\n"

    # Top movers section (premium only)
    movers_html = ""
    movers_text = ""
    if is_premium and (top_gainers or top_losers):
        movers_html = "<h3 style='margin-top:1.5rem;font-size:0.95rem;font-weight:700'>Top movers</h3>"
        if top_gainers:
            movers_html += "<div style='font-size:0.82rem;color:#888;margin-bottom:0.3rem'>Gainers</div><ul style='margin:0 0 0.75rem;padding-left:1.2rem'>"
            for g in top_gainers:
                movers_html += f"<li><strong>{g['ticker']}</strong>: +{g['pct']:.1f}% (+€{g['eur']:,.2f})</li>"
            movers_html += "</ul>"
            movers_text += "Top gainers:\n" + "\n".join(f"  {g['ticker']}: +{g['pct']:.1f}% (+€{g['eur']:,.2f})" for g in top_gainers) + "\n"
        if top_losers:
            movers_html += "<div style='font-size:0.82rem;color:#888;margin-bottom:0.3rem'>Losers</div><ul style='margin:0 0 0 0;padding-left:1.2rem'>"
            for loser in top_losers:
                movers_html += f"<li><strong>{loser['ticker']}</strong>: {loser['pct']:.1f}% (€{loser['eur']:,.2f})</li>"
            movers_html += "</ul>"
            movers_text += "Top losers:\n" + "\n".join(f"  {loser['ticker']}: {loser['pct']:.1f}% (€{loser['eur']:,.2f})" for loser in top_losers) + "\n"
    elif not is_premium:
        movers_html = """
        <div style="background:#fef9c3;border:1px solid #fde68a;border-radius:6px;padding:12px;margin-top:1.5rem;font-size:0.85rem">
          <strong>🔒 Top movers, tax events &amp; harvest opportunities</strong> are available on Premium.
          <a href="{app_url}/pricing" style="color:#92400e;text-decoration:underline">Upgrade →</a>
        </div>""".format(app_url=app_url)

    # Tax events section (premium only)
    tax_html = ""
    tax_text = ""
    if is_premium and tax_events:
        tax_html = "<h3 style='margin-top:1.5rem;font-size:0.95rem;font-weight:700'>Upcoming tax bracket anniversaries</h3>"
        tax_html += "<ul style='margin:0;padding-left:1.2rem;font-size:0.88rem'>"
        for ev in tax_events:
            days_str = f"in {ev['days_away']} day{'s' if ev['days_away'] != 1 else ''}"
            tax_html += (
                f"<li><strong>{ev['ticker']}</strong> — {ev['date']} ({days_str}): "
                f"{ev['from_rate_pct']:.0f}% → {ev['to_rate_pct']:.0f}% tax rate</li>"
            )
        tax_html += "</ul>"
        tax_text += "Tax bracket anniversaries:\n" + "\n".join(
            f"  {ev['ticker']}: {ev['date']} ({ev['days_away']}d) — {ev['from_rate_pct']:.0f}% → {ev['to_rate_pct']:.0f}%"
            for ev in tax_events
        ) + "\n"

    # Harvest section (premium only)
    harvest_html = ""
    harvest_text = ""
    if is_premium and harvest_opps:
        harvest_html = "<h3 style='margin-top:1.5rem;font-size:0.95rem;font-weight:700'>Harvest opportunities</h3>"
        harvest_html += "<ul style='margin:0;padding-left:1.2rem;font-size:0.88rem'>"
        for h in harvest_opps:
            wash = " ⚠️ wash-sale risk" if h["wash_risk"] else ""
            harvest_html += (
                f"<li><strong>{h['ticker']}</strong>: "
                f"€{abs(h['loss_eur']):,.2f} loss · saves ~€{h['saving_eur']:,.2f} tax{wash}</li>"
            )
        harvest_html += "</ul>"
        harvest_text += "Harvest opportunities:\n" + "\n".join(
            f"  {h['ticker']}: €{abs(h['loss_eur']):,.2f} loss, saves ~€{h['saving_eur']:,.2f}"
            + (" (wash-sale risk)" if h["wash_risk"] else "")
            for h in harvest_opps
        ) + "\n"

    login_btn_label = "Open my portfolio" if is_premium else "View demo portfolio"

    html_body = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:auto;padding:32px">
      <h2 style="font-size:1.3rem;margin-bottom:0.25rem">Weekly Portfolio Digest</h2>
      <p style="color:#666;font-size:0.85rem;margin-top:0">{summary['end_date']}</p>

      <table style="width:100%;border-collapse:collapse;margin:1.5rem 0">
        <tr style="border-bottom:1px solid #eee">
          <td style="padding:8px 0;color:#666">Portfolio value</td>
          <td style="padding:8px 0;text-align:right;font-weight:700">€{summary['total_value_eur']:,.2f}</td>
        </tr>
        {wow_html}
        <tr style="border-bottom:1px solid #eee">
          <td style="padding:8px 0;color:#666">Total gain/loss</td>
          <td style="padding:8px 0;text-align:right;font-weight:700;color:{gain_color}">
            {gain_sign}€{summary['total_gain_eur']:,.2f} ({gain_sign}{summary['total_return_pct']:.1f}%)
          </td>
        </tr>
        <tr>
          <td style="padding:8px 0;color:#666">Positions</td>
          <td style="padding:8px 0;text-align:right">{summary['positions_count']}</td>
        </tr>
      </table>

      {movers_html}
      {tax_html}
      {harvest_html}

      <p style="margin-top:2rem">
        <a href="{magic_url}"
           style="background:#f59e0b;color:#000;padding:12px 24px;border-radius:6px;
                  text-decoration:none;font-weight:700;display:inline-block">
          {login_btn_label} →
        </a>
      </p>
      <p style="font-size:0.78rem;color:#999;margin-top:0.5rem">
        One-click link — valid 72 hours, single use.
      </p>

      <p style="color:#999;font-size:0.75rem;margin-top:2rem">
        You're receiving this because you enabled weekly digest emails.
        <a href="{app_url}/settings" style="color:#999">Manage preferences</a>
      </p>
    </div>
    """

    text_body = (
        f"Weekly Portfolio Digest — {summary['end_date']}\n\n"
        f"Portfolio value: €{summary['total_value_eur']:,.2f}\n"
        + wow_text +
        f"Total gain/loss: {gain_sign}€{summary['total_gain_eur']:,.2f} ({gain_sign}{summary['total_return_pct']:.1f}%)\n"
        f"Positions: {summary['positions_count']}\n\n"
        + movers_text + tax_text + harvest_text +
        f"\nOpen portfolio: {magic_url}\n"
        f"(one-click link, valid 72 hours)\n"
    )

    return subject, html_body, text_body


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

def _log_send(conn: sqlite3.Connection, user_id: int, report_type: str,
              status: str = "sent", error: str | None = None,
              portfolio_value: float | None = None):
    _ensure_prefs_schema(conn)
    conn.execute(
        "INSERT INTO report_log (user_id, report_type, status, error, portfolio_value) VALUES (?, ?, ?, ?, ?)",
        (user_id, report_type, status, error, portfolio_value),
    )
    conn.commit()


def send_report_to_user(user: "User", report_type: str, prefs: "ReportPreferences",
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
    elif report_type == "digest":
        users_conn = get_users_db()
        try:
            _ensure_prefs_schema(users_conn)
            last_value = _get_last_digest_value(user.id, users_conn)
        finally:
            users_conn.close()

        is_premium = user.role in ("premium", "admin")
        top_gainers, top_losers = _get_top_movers(user.username, prefs.scope) if is_premium else ([], [])
        tax_events = _get_tax_events(user.username, prefs.scope, prefs.country) if is_premium else []
        harvest_opps = _get_harvest_summary(user.username, prefs.scope, prefs.country) if is_premium else []

        # Generate magic login link
        from .users import create_magic_token
        app_url = os.environ.get("APP_BASE_URL", "http://localhost:8083")
        try:
            uc = get_users_db()
            token = create_magic_token(user.id, conn=uc)
            uc.close()
            magic_url = f"{app_url.rstrip('/')}/login/magic/{token}"
        except Exception:
            magic_url = f"{app_url.rstrip('/')}/report"

        subject, html, text = _render_digest_email(
            user, summary, last_value, top_gainers, top_losers,
            tax_events, harvest_opps, magic_url, is_premium,
        )
    else:
        return False

    portfolio_value = summary.get("total_value_eur") if report_type == "digest" else None

    try:
        _send(user.email, subject, html, text)
        conn = get_users_db()
        try:
            _log_send(conn, user.id, report_type, "sent", portfolio_value=portfolio_value)
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
        elif report_type == "digest":
            col = "digest_enabled"
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
