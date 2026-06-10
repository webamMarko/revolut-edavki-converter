"""Portfolio operations: import, sync, reports, exports."""

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from .auth import get_session, get_session_token, get_client_ip
from .templates import page_env, FOUC_SCRIPT, COMMON_JS, html_response, json_response, redirect, error_response

DATA_DIR = Path(os.environ.get("REVOLUT_DATA_DIR", Path(__file__).resolve().parent.parent.parent / "data"))
DEMO_DB = DATA_DIR / "_demo" / "portfolio.db"
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8081")
STRIPE_BILLING_PORTAL_URL = os.environ.get("STRIPE_BILLING_PORTAL_URL", "")

# Import wizard staging: token -> {path, dir, filename, expires}
_IMPORT_STAGING: dict[str, dict] = {}


def user_db_path(username: str) -> Path:
    """Return path to user's portfolio DB."""
    return DATA_DIR / username / "portfolio.db"


def purge_expired_staging():
    """Remove expired staging entries and their temp files."""
    now = time.time()
    expired = [t for t, v in _IMPORT_STAGING.items() if v["expires"] < now]
    for t in expired:
        cleanup_staging(t)


def cleanup_staging(token: str):
    """Delete temp file/dir for a staging entry and remove from dict."""
    entry = _IMPORT_STAGING.pop(token, None)
    if not entry:
        return
    try:
        if os.path.exists(entry["path"]):
            os.unlink(entry["path"])
        if os.path.exists(entry.get("dir", "")):
            os.rmdir(entry["dir"])
    except Exception:
        pass


def detect_asset_class_from_headers(
    headers: list,
    first_row: Optional[list] = None,
) -> dict:
    """Detect asset class using confidence-scored rules.

    Returns a dict with detectedClass (str | None), confidence (float 0-1),
    and per-class scores. detectedClass is None when confidence < 70%.
    """
    from .detection_rules import detect_asset_class
    return detect_asset_class(headers, first_row)


# ------------------------------------------------------------------
# Demo view toggle (for premium/admin users to preview demo data)
# ------------------------------------------------------------------

# Demo view toggle: session_token -> bool (True = viewing demo data)
_DEMO_VIEW: dict[str, bool] = {}


def portfolio_conn(user: Optional[dict], session_token: Optional[str] = None):
    """Return a DB connection for the given session user (or demo DB if no user).

    If session_token is provided and demo_view is enabled for that session,
    returns demo DB even for premium/admin users.
    """
    from ..db import get_connection

    # Check if this session has demo view enabled
    if session_token and _DEMO_VIEW.get(session_token, False):
        return get_connection(db_path=DEMO_DB)

    if user and user["role"] in ("premium", "admin"):
        return get_connection(db_path=user_db_path(user["username"]))
    return get_connection(db_path=DEMO_DB)


def get_portfolio_conn(handler):
    """Get portfolio DB connection respecting session and demo toggle."""
    session = get_session(handler)
    session_token = get_session_token(handler)
    return portfolio_conn(session, session_token)


# ------------------------------------------------------------------
# Route handlers
# ------------------------------------------------------------------

def serve_upload_page(handler):
    """GET / — main upload/dashboard page."""
    session = get_session(handler)
    session_token = get_session_token(handler)
    is_demo_view = bool(session_token and _DEMO_VIEW.get(session_token, False))
    username = session["username"] if session else None
    role = session["role"] if session else "guest"
    is_premium = role in ("premium", "admin")

    template = page_env.get_template("pages/upload.html.j2")
    html = template.render(
        fouc_script=FOUC_SCRIPT,
        common_js=COMMON_JS,
        show_header=True,
        show_drop_import=is_premium,
        username=username,
        role=role,
        is_premium=is_premium,
        is_demo_view=is_demo_view,
        app_base_url=APP_BASE_URL.rstrip("/"),
        robots="index, follow",
    )
    html_response(handler, html)


def serve_status(handler):
    """GET /status — portfolio status JSON."""
    session = get_session(handler)
    session_token = get_session_token(handler)
    conn = portfolio_conn(session, session_token)
    # Determine actual DB path being used (respects demo toggle)
    if session_token and _DEMO_VIEW.get(session_token, False):
        db_path = DEMO_DB
    elif session and session["role"] in ("premium", "admin"):
        db_path = user_db_path(session["username"])
    else:
        db_path = DEMO_DB
    data = {"has_data": False, "db_path": str(db_path)}
    try:
        row_count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        data["has_data"] = row_count > 0
        data["transaction_count"] = row_count
        data["ticker_count"] = conn.execute(
            "SELECT COUNT(DISTINCT ticker) FROM transactions WHERE ticker IS NOT NULL"
        ).fetchone()[0]
        date_range = conn.execute("SELECT MIN(date), MAX(date) FROM transactions").fetchone()
        if date_range and date_range[0]:
            data["date_range"] = [date_range[0][:10], date_range[1][:10]]
        class_rows = conn.execute(
            "SELECT asset_class, COUNT(*) FROM transactions GROUP BY asset_class"
        ).fetchall()
        data["asset_classes"] = {r[0]: r[1] for r in class_rows}
        data["import_count"] = conn.execute("SELECT COUNT(*) FROM import_log").fetchone()[0]
        data["price_count"] = conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
        recent_imports = conn.execute(
            "SELECT filename, rows_new, rows_skipped, imported_at FROM import_log ORDER BY imported_at DESC LIMIT 5"
        ).fetchall()
        data["recent_imports"] = [
            {"filename": r[0], "rows_new": r[1], "rows_skipped": r[2], "imported_at": r[3]}
            for r in recent_imports
        ]
    finally:
        conn.close()
    json_response(handler, data)


def handle_upload(handler):
    """POST /upload — upload CSV/Excel files (premium/admin only)."""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        json_response(handler, {"error": "Login required to upload files."}, status=403)
        return

    content_length = int(handler.headers.get("Content-Length", 0))
    if content_length > 100 * 1024 * 1024:
        json_response(handler, {"error": "File too large (max 100MB)"}, status=413)
        return

    body = handler._read_body(content_length)
    from ..server_utils import parse_multipart
    fields, files = parse_multipart(handler.headers, body)

    if not files:
        json_response(handler, {"error": "No files uploaded"}, status=400)
        return

    from ..db import get_connection
    from ..importer import import_csv

    conn = get_connection(db_path=user_db_path(session["username"]))
    results = []
    try:
        for f in files:
            filename = f["filename"]
            ext = Path(filename).suffix.lower()
            if ext not in (".csv", ".xlsx", ".xls"):
                results.append({"filename": filename, "error": f"Unsupported format: {ext}"})
                continue
            tmp_dir = tempfile.mkdtemp(prefix="revolut_upload_")
            tmp_path = os.path.join(tmp_dir, filename)
            try:
                with open(tmp_path, "wb") as tmp:
                    tmp.write(f["content"])
                result = import_csv(conn, tmp_path, verbose=handler.verbose)
                entry = {
                    "filename": filename,
                    "total": result.total,
                    "new": result.new,
                    "skipped": result.skipped,
                }
                if result.warnings:
                    entry["warnings"] = result.warnings
                results.append(entry)
            except Exception as e:
                results.append({"filename": filename, "error": str(e)})
            finally:
                try:
                    os.unlink(tmp_path)
                    os.rmdir(tmp_dir)
                except Exception:
                    pass
    finally:
        conn.close()

    from ..audit import log_event
    for r in results:
        if "error" not in r:
            log_event("data_import", username=session["username"],
                      ip_address=get_client_ip(handler),
                      detail=f"{r['filename']}: {r.get('new',0)} new rows")
    json_response(handler, {"results": results})


def handle_sync(handler):
    """POST /sync — sync prices from yfinance (premium/admin only)."""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        json_response(handler, {"error": "Login required to sync prices."}, status=403)
        return

    from ..db import get_connection
    from ..price_fetcher import sync_all
    from ..prices_db import get_prices_connection
    from ..analytics_cache import invalidate_cache
    from ..tax_cache import invalidate_current_year_tax
    from ..report_cache import invalidate_user_html

    conn = get_connection(db_path=user_db_path(session["username"]))
    prices_conn = get_prices_connection()
    try:
        sync_all(conn, verbose=handler.verbose, prices_conn=prices_conn)
        invalidate_cache(conn)
        invalidate_current_year_tax(conn)
        invalidate_user_html(session["username"])
        json_response(handler, {"ok": True})
    except Exception as e:
        json_response(handler, {"error": str(e)}, status=500)
    finally:
        prices_conn.close()
        conn.close()


def serve_report(handler):
    """GET /report — HTML portfolio report."""
    session = get_session(handler)
    from ..analytics import compute_analytics
    from ..analytics_cache import compute_data_hash, get_cached, put_cache
    from ..report_cache import get_cached_html, put_cached_html
    from ..tax import compute_tax_report
    from ..tax_cache import get_cached_tax, put_tax_cache
    from ..html_report import (generate_html_report, query_transactions,
                               query_real_estate, query_fire_config,
                               query_investment_notes)
    from datetime import datetime

    # Parse country from query string, default to SI
    qs = parse_qs(urlparse(handler.path).query)
    country = qs.get("country", ["SI"])[0].upper()

    from ..prices_db import get_prices_conn_or_none

    session_token = get_session_token(handler)
    username = session["username"] if session else "_demo"

    # Force portfolio_id = 1 when viewing demo data (demo DB only has portfolio 1)
    is_demo_view = session_token and _DEMO_VIEW.get(session_token, False)
    if is_demo_view or not session:
        portfolio_id = 1
    else:
        portfolio_id = session.get("active_portfolio_id", 1)

    conn = portfolio_conn(session, session_token)
    prices_conn = get_prices_conn_or_none()
    try:
        data_hash = compute_data_hash(conn, prices_conn, portfolio_id=portfolio_id)
        etag = f'"{data_hash}"'

        if_none_match = handler.headers.get("If-None-Match", "")
        if if_none_match == etag:
            handler.send_response(304)
            handler.send_header("ETag", etag)
            handler.end_headers()
            return

        cached_html = get_cached_html(username, data_hash)
        if cached_html is not None:
            handler.send_response(200)
            handler.send_header("Content-Type", "text/html; charset=utf-8")
            handler.send_header("ETag", etag)
            handler.end_headers()
            handler.wfile.write(cached_html.encode("utf-8"))
            return

        def _cached_analytics(scope):
            cached = get_cached(conn, scope, data_hash, portfolio_id=portfolio_id)
            if cached is not None:
                return cached
            result = compute_analytics(conn, scope=scope, prices_conn=prices_conn, portfolio_id=portfolio_id)
            put_cache(conn, scope, data_hash, result, portfolio_id=portfolio_id)
            return result

        analytics = _cached_analytics("all")
        tax_by_year = {}
        try:
            current_year = datetime.now().year
            years_with_tx = [
                int(r[0]) for r in conn.execute(
                    "SELECT DISTINCT strftime('%Y', date) FROM transactions "
                    "WHERE asset_class != 'realestate' AND portfolio_id = ? ORDER BY 1",
                    (portfolio_id,)
                ).fetchall()
            ]
            for yr in years_with_tx:
                try:
                    cached = get_cached_tax(conn, yr, "all", country, data_hash)
                    if cached is not None:
                        tax_by_year[yr] = cached
                    else:
                        report = compute_tax_report(conn, year=yr, include_unrealized=False,
                                                   scope="all", country=country,
                                                   prices_conn=prices_conn, portfolio_id=portfolio_id)
                        put_tax_cache(conn, yr, "all", country, data_hash, report, current_year)
                        tax_by_year[yr] = report
                except Exception:
                    pass
        except Exception:
            pass
        transactions = query_transactions(conn, portfolio_id=portfolio_id)
        # Lazy-load: pass only class names; frontend fetches per-class data on demand
        available_classes = [r[0] for r in conn.execute("SELECT DISTINCT asset_class FROM transactions WHERE portfolio_id = ?", (portfolio_id,)).fetchall()]
        re_data = query_real_estate(conn, prices_conn=prices_conn, portfolio_id=portfolio_id)
        fire_cfg = query_fire_config(conn)
        notes = query_investment_notes(conn, portfolio_id=portfolio_id)
        html = generate_html_report(analytics, tax_by_year, transactions, per_class=None,
                                    available_classes=available_classes,
                                    real_estate=re_data, fire_config=fire_cfg,
                                    investment_notes=notes, conn=conn,
                                    country=country, prices_conn=prices_conn)
        # Inject current user into D so client JS can gate the edit UI.
        user_payload = json.dumps({
            "id": session["user_id"],
            "username": session["username"],
            "role": session["role"],
        }) if session else "null"
        html = html.replace(
            "<script>const D=",
            "<script>const D=",
            1,
        )
        # Find the </script> that closes the D= block and inject before it
        d_script_end = html.find(";</script>", html.find("<script>const D="))
        if d_script_end != -1:
            html = html[:d_script_end] + f";D.user={user_payload}" + html[d_script_end:]

        put_cached_html(username, data_hash, html)

        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("ETag", etag)
        handler.end_headers()
        handler.wfile.write(html.encode("utf-8"))
    except ValueError as e:
        error_response(handler, str(e), status=400)
    except Exception as e:
        handler.send_response(500)
        handler.send_header("Content-Type", "text/plain")
        handler.end_headers()
        handler.wfile.write(f"Error generating report: {e}".encode("utf-8"))
    finally:
        if prices_conn:
            prices_conn.close()
        conn.close()


# ------------------------------------------------------------------
# Tax exports
# ------------------------------------------------------------------

def export_year(handler):
    """Parse year from query string and validate session. Returns (session, year) or sends error."""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        json_response(handler, {"error": "Login required."}, status=403)
        return None, None
    qs = parse_qs(urlparse(handler.path).query)
    try:
        year = int(qs.get("year", [0])[0])
    except (ValueError, IndexError):
        json_response(handler, {"error": "Invalid year."}, status=400)
        return None, None
    if year < 2000 or year > 2100:
        json_response(handler, {"error": "Invalid year."}, status=400)
        return None, None
    return session, year



def serve_settings_page(handler):
    """GET /settings — settings page."""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        redirect(handler, "/login")
        return

    conn = portfolio_conn(session, get_session_token(handler))
    try:
        from ..ibkr_sync import get_sync_status
        ibkr_status = get_sync_status(conn)
    except Exception:
        ibkr_status = {"configured": False, "query_id": "", "last_sync": None, "last_error": None}
    finally:
        conn.close()

    template = page_env.get_template("pages/settings.html.j2")
    html = template.render(
        username=session["username"],
        role=session["role"],
        billing_portal_url=STRIPE_BILLING_PORTAL_URL,
        fouc_script=FOUC_SCRIPT,
        common_js=COMMON_JS,
        show_header=True,
        show_drop_import=True,
        ibkr_status=ibkr_status,
    )
    html_response(handler, html)


def serve_pricing_page(handler):
    """GET /pricing — pricing page."""
    session = get_session(handler)
    username = session["username"] if session else ""
    role = session["role"] if session else "guest"

    STRIPE_CHECKOUT_URL = os.environ.get("STRIPE_CHECKOUT_URL", "")
    stripe_url = STRIPE_CHECKOUT_URL
    cta_btn = (
        f'<a class="btn btn-primary btn-lg" href="{stripe_url}">Get Started</a>'
        if stripe_url
        else '<span class="btn btn-secondary btn-lg disabled">Coming soon</span>'
    )

    template = page_env.get_template("pages/pricing.html.j2")
    html = template.render(
        cta_btn=cta_btn,
        app_base_url=APP_BASE_URL.rstrip("/"),
        fouc_script=FOUC_SCRIPT,
        common_js=COMMON_JS,
        show_header=True,
        show_drop_import=False,
        username=username,
        role=role,
        active_page="pricing"
    )
    html_response(handler, html)


# ------------------------------------------------------------------
# Real estate property pages
# ------------------------------------------------------------------

def serve_properties_list(handler):
    """GET /properties — property list page."""
    session = get_session(handler)
    if not session:
        redirect(handler, "/login")
        return
    conn = portfolio_conn(session, get_session_token(handler))
    try:
        from ..realestate import list_properties
        portfolio_id = session.get("active_portfolio_id", 1)
        props = list_properties(conn, portfolio_id=portfolio_id)
    finally:
        conn.close()

    template = page_env.get_template("pages/properties_list.html.j2")
    html = template.render(
        fouc_script=FOUC_SCRIPT,
        common_js=COMMON_JS,
        show_header=True,
        show_drop_import=False,
        username=session.get("username"),
        role=session.get("role"),
        active_page="properties",
        properties=props,
    )
    html_response(handler, html)


def serve_property_new(handler):
    """GET /properties/new — 3-step creation wizard."""
    session = get_session(handler)
    if not session:
        redirect(handler, "/login")
        return

    from ..countries import COUNTRIES
    template = page_env.get_template("pages/properties_new.html.j2")
    html = template.render(
        fouc_script=FOUC_SCRIPT,
        common_js=COMMON_JS,
        show_header=True,
        show_drop_import=False,
        username=session.get("username"),
        role=session.get("role"),
        active_page="properties",
        countries=COUNTRIES,
    )
    html_response(handler, html)


def serve_property_edit(handler, property_id: int):
    """GET /properties/{id}/edit — single-page edit form."""
    session = get_session(handler)
    if not session:
        redirect(handler, "/login")
        return
    conn = portfolio_conn(session, get_session_token(handler))
    try:
        from ..realestate import get_property
        portfolio_id = session.get("active_portfolio_id", 1)
        prop = get_property(conn, property_id, portfolio_id=portfolio_id)
    finally:
        conn.close()

    if not prop:
        error_response(handler, "Property not found", status=404)
        return

    from ..countries import COUNTRIES
    template = page_env.get_template("pages/properties_edit.html.j2")
    html = template.render(
        fouc_script=FOUC_SCRIPT,
        common_js=COMMON_JS,
        show_header=True,
        show_drop_import=False,
        username=session.get("username"),
        role=session.get("role"),
        active_page="properties",
        prop=prop,
        countries=COUNTRIES,
    )
    html_response(handler, html)
