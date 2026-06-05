"""HTTP handlers for IBKR integration endpoints."""

from __future__ import annotations

import json

from .auth import get_session, get_session_token
from .portfolio import portfolio_conn
from .templates import json_response


def api_ibkr_status(handler):
    """GET /api/ibkr/status — return IBKR sync status (configured, last sync, etc.)."""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        json_response(handler, {"error": "Login required."}, status=403)
        return

    from ..ibkr_sync import get_sync_status
    conn = portfolio_conn(session, get_session_token(handler))
    try:
        status = get_sync_status(conn)
    finally:
        conn.close()

    json_response(handler, status)


def api_ibkr_save_credentials(handler):
    """POST /api/ibkr/credentials — save IBKR Flex token + query ID."""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        json_response(handler, {"error": "Login required."}, status=403)
        return

    length = int(handler.headers.get("Content-Length", 0))
    body = handler.rfile.read(length)
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        json_response(handler, {"error": "Invalid JSON."}, status=400)
        return

    token = str(data.get("token", "")).strip()
    query_id = str(data.get("query_id", "")).strip()

    if not token or not query_id:
        json_response(handler, {"error": "Both token and query_id are required."}, status=400)
        return

    from ..ibkr_sync import save_credentials
    conn = portfolio_conn(session, get_session_token(handler))
    try:
        save_credentials(conn, token, query_id)
    finally:
        conn.close()

    json_response(handler, {"ok": True})


def api_ibkr_delete_credentials(handler):
    """POST /api/ibkr/credentials/delete — remove stored IBKR credentials."""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        json_response(handler, {"error": "Login required."}, status=403)
        return

    from ..ibkr_sync import delete_credentials
    conn = portfolio_conn(session, get_session_token(handler))
    try:
        delete_credentials(conn)
    finally:
        conn.close()

    json_response(handler, {"ok": True})


def api_ibkr_sync(handler):
    """POST /api/ibkr/sync — fetch Flex report and import transactions."""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        json_response(handler, {"error": "Login required."}, status=403)
        return

    from ..ibkr_sync import sync_ibkr
    from ..analytics_cache import invalidate_cache
    from ..tax_cache import invalidate_current_year_tax
    from ..report_cache import invalidate_user_html

    portfolio_id = session.get("active_portfolio_id", 1)
    conn = portfolio_conn(session, get_session_token(handler))
    try:
        result = sync_ibkr(conn, portfolio_id=portfolio_id)
        if result["error"]:
            json_response(handler, {"error": result["error"]}, status=500)
            return
        # Invalidate caches so the UI reflects new data
        invalidate_cache(conn)
        invalidate_current_year_tax(conn)
        invalidate_user_html(session["username"])
        json_response(handler, result)
    finally:
        conn.close()
