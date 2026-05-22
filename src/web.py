"""Lightweight web UI for CSV upload, import, and portfolio dashboard.

Multi-user mode: session cookies, per-user SQLite databases, role-based access.
Roles: guest (unauthenticated, sees demo portfolio), premium (own DB), admin (+ user management).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from jinja2 import Environment, FileSystemLoader
from src.i18n import get_translations

# ---------------------------------------------------------------------------
# Environment / constants
# ---------------------------------------------------------------------------

def _default_data_dir() -> str:
    project_data = Path(__file__).resolve().parent.parent / "data"
    if project_data.is_dir():
        return str(project_data)
    return str(Path.home() / ".revolut-edavki")

DATA_DIR = Path(os.environ.get("REVOLUT_DATA_DIR", _default_data_dir()))
DEMO_DB  = DATA_DIR / "_demo" / "portfolio.db"

APP_BASE_URL                = os.environ.get("APP_BASE_URL", "http://localhost:8080")
STRIPE_WEBHOOK_SECRET       = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_CHECKOUT_URL         = os.environ.get("STRIPE_CHECKOUT_URL", "")
STRIPE_BILLING_PORTAL_URL   = os.environ.get("STRIPE_BILLING_PORTAL_URL", "")

SESSION_TTL = 86400 * 7  # 7 days (also used for cookie Max-Age)

FORCE_HTTPS = os.environ.get("FORCE_HTTPS", "").lower() in ("true", "1", "yes")

# Rate limiting: sliding window per IP for login attempts
RATE_LIMIT_MAX_ATTEMPTS = 5
RATE_LIMIT_WINDOW_SECONDS = 900  # 15 minutes
_login_attempts: dict[str, list[float]] = {}  # ip -> [timestamps]

# Import wizard staging: token -> {path, dir, filename, expires}
_IMPORT_STAGING: dict[str, dict] = {}

# Demo view toggle: session_token -> bool (True = viewing demo data)
_DEMO_VIEW: dict[str, bool] = {}


def _detect_asset_class_from_headers(headers: list) -> str | None:
    """Detect asset class from CSV header list."""
    cols = {h.strip() for h in headers}
    # IBKR Activity Statement
    if "Trades" in cols and "DataDiscriminator" in cols:
        return "stock"
    # Trading 212
    if "Action" in cols and "No. of shares" in cols and "Price / share" in cols:
        return "stock"
    # Degiro
    if "Datum" in cols and "Product" in cols and "ISIN" in cols:
        return "stock"
    if "FinancialInstrument" in cols and "TransactionTypeName" in cols:
        return "stock"
    if "Symbol" in cols and "Margin" in cols:
        return "cfd"
    if "Symbol" in cols and "Value" in cols and "Ticker" not in cols:
        return "crypto"
    if "Description" in cols and "Symbol" not in cols and "Ticker" not in cols:
        return "savings"
    if "Ticker" in cols or "Price per share" in cols:
        return "stock"
    return None


def _purge_expired_staging():
    """Remove expired staging entries and their temp files."""
    now = time.time()
    expired = [t for t, v in _IMPORT_STAGING.items() if v["expires"] < now]
    for t in expired:
        _cleanup_staging(t)


def _cleanup_staging(token: str):
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


def _get_session_token(handler) -> str | None:
    """Extract raw session token from cookie (used as staging key)."""
    cookie_header = handler.headers.get("Cookie", "")
    if not cookie_header:
        return None
    c = SimpleCookie()
    c.load(cookie_header)
    morsel = c.get("session")
    return morsel.value if morsel else None


def _get_client_ip(handler) -> str:
    forwarded = handler.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return handler.client_address[0] if handler.client_address else "unknown"


def _check_rate_limit(ip: str) -> int | None:
    """Return seconds until retry is allowed, or None if not rate-limited."""
    now = time.time()
    attempts = _login_attempts.get(ip, [])
    attempts = [t for t in attempts if now - t < RATE_LIMIT_WINDOW_SECONDS]
    _login_attempts[ip] = attempts
    if len(attempts) >= RATE_LIMIT_MAX_ATTEMPTS:
        oldest = attempts[0]
        return int(oldest + RATE_LIMIT_WINDOW_SECONDS - now) + 1
    return None


def _record_login_attempt(ip: str) -> None:
    _login_attempts.setdefault(ip, []).append(time.time())


# ---------------------------------------------------------------------------
# Multipart parser (unchanged from original)
# ---------------------------------------------------------------------------

def _parse_multipart(headers, body):
    content_type = headers.get("Content-Type", "")
    if "boundary=" not in content_type:
        return {}, []
    boundary = content_type.split("boundary=")[1].strip().strip('"').encode()
    parts = body.split(b"--" + boundary)
    fields, files = {}, []
    for part in parts:
        part = part.strip()
        if not part or part == b"--":
            continue
        if b"\r\n\r\n" not in part:
            continue
        header_block, content = part.split(b"\r\n\r\n", 1)
        if content.endswith(b"\r\n"):
            content = content[:-2]
        header_str = header_block.decode("utf-8", errors="replace")
        name = filename = None
        for line in header_str.split("\r\n"):
            if "Content-Disposition:" in line:
                for param in line.split(";"):
                    param = param.strip()
                    if param.startswith("name="):
                        name = param.split("=", 1)[1].strip('"')
                    elif param.startswith("filename="):
                        filename = param.split("=", 1)[1].strip('"')
        if filename:
            files.append({"filename": filename, "content": content, "field_name": name})
        elif name:
            fields[name] = content.decode("utf-8", errors="replace")
    return fields, files


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _user_db_path(username: str) -> Path:
    return DATA_DIR / username / "portfolio.db"


def _portfolio_conn(user: dict | None, session_token: str | None = None):
    """Return a DB connection for the given session user (or demo DB if no user).

    If session_token is provided and demo_view is enabled for that session,
    returns demo DB even for premium/admin users.
    """
    from .db import get_connection

    # Check if this session has demo view enabled
    if session_token and _DEMO_VIEW.get(session_token, False):
        return get_connection(db_path=DEMO_DB)

    if user and user["role"] in ("premium", "admin"):
        return get_connection(db_path=_user_db_path(user["username"]))
    return get_connection(db_path=DEMO_DB)


def _create_session(user) -> str:
    """Create a persistent DB-backed session token for a User object."""
    from .users import create_session as _db_create_session
    return _db_create_session(user)


def _get_session(handler) -> dict | None:
    """Return session dict {user_id, username, role} or None."""
    from .users import get_session as _db_get_session
    cookie_header = handler.headers.get("Cookie", "")
    if not cookie_header:
        return None
    c = SimpleCookie()
    c.load(cookie_header)
    morsel = c.get("session")
    if not morsel:
        return None
    return _db_get_session(morsel.value)


def _get_portfolio_conn(handler):
    """Get portfolio DB connection respecting session and demo toggle."""
    session = _get_session(handler)
    session_token = _get_session_token(handler)
    return _portfolio_conn(session, session_token)


# ---------------------------------------------------------------------------
# Stripe webhook HMAC verification
# ---------------------------------------------------------------------------

def _verify_stripe_signature(body: bytes, sig_header: str, secret: str) -> bool:
    """Verify Stripe-Signature header using HMAC-SHA256."""
    if not secret:
        return False
    try:
        pairs = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
        timestamp = pairs.get("t", "")
        v1 = pairs.get("v1", "")
        signed_payload = f"{timestamp}.".encode() + body
        expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        return secrets.compare_digest(expected, v1)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class UploadHandler(BaseHTTPRequestHandler):
    verbose = False

    def log_message(self, format, *args):
        if self.verbose:
            super().log_message(format, *args)

    def _enforce_https(self) -> bool:
        """If FORCE_HTTPS is set and request is HTTP (not localhost), redirect. Returns True if redirected."""
        if not FORCE_HTTPS:
            return False
        host = self.headers.get("Host", "")
        if host.startswith("localhost") or host.startswith("127."):
            return False
        proto = self.headers.get("X-Forwarded-Proto", "http")
        if proto == "https":
            return False
        target = f"https://{host}{self.path}"
        self.send_response(301)
        self.send_header("Location", target)
        self.end_headers()
        return True

    def _add_security_headers(self):
        if FORCE_HTTPS:
            self.send_header("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def do_GET(self):
        if self._enforce_https():
            return
        path = urlparse(self.path).path
        if path == "/admin/audit-log":
            self._serve_audit_log()
            return
        if path == "/api/audit-events":
            self._api_audit_events()
            return
        if path == "/":
            self._serve_upload_page()
        elif path == "/status":
            self._serve_status()
        elif path == "/report":
            self._serve_report()
        elif path == "/login":
            self._serve_login_page()
        elif path == "/logout":
            self._handle_logout()
        elif path.startswith("/login/magic/"):
            token = path[len("/login/magic/"):]
            self._handle_magic_login(token)
        elif path.startswith("/invite/"):
            token = path[len("/invite/"):]
            self._serve_invite_page(token)
        elif path == "/admin":
            self._serve_admin_page()
        elif path == "/admin/users":
            self._serve_admin_users_json()
        elif path == "/api/notes":
            self._api_list_notes()
        elif path == "/api/onboarding-status":
            self._api_onboarding_status()
        elif path == "/import":
            self._serve_import_wizard()
        elif path == "/export/edavki":
            self._handle_export_edavki()
        elif path == "/export/fifo-csv":
            self._handle_export_fifo_csv()
        elif path == "/export/tax-pdf":
            self._handle_export_tax_pdf()
        elif path == "/export/doh-div":
            self._handle_export_doh_div()
        elif path == "/api/dividend-summary":
            self._handle_dividend_summary()
        elif path == "/api/email-preferences":
            self._api_get_email_preferences()
        elif path == "/api/edavki-filed":
            self._api_get_edavki_filed()
        elif path.startswith("/api/analytics/"):
            scope = path[len("/api/analytics/"):]
            self._api_get_analytics(scope)
        elif path == "/settings":
            self._serve_settings_page()
        elif path == "/pricing":
            self._serve_pricing_page()
        elif path == "/reset-password":
            self._serve_reset_password_page()
        elif path.startswith("/reset-password/"):
            token = path[len("/reset-password/"):]
            self._serve_reset_password_confirm_page(token)
        elif path == "/account":
            self._serve_account_page()
        elif path == "/robots.txt":
            self._serve_robots_txt()
        elif path == "/sitemap.xml":
            self._serve_sitemap_xml()
        elif path == "/api/shares":
            self._api_list_shares()
        elif path == "/api/goals":
            self._api_list_goals()
        elif path.startswith("/api/goals/") and path.endswith("/projection"):
            goal_id = path[len("/api/goals/"):-len("/projection")]
            if goal_id.isdigit():
                self._api_goal_projection(int(goal_id))
            else:
                self.send_error(404)
        elif path.startswith("/api/goals/"):
            goal_id = path[len("/api/goals/"):]
            if goal_id.isdigit():
                self._api_get_goal(int(goal_id))
            else:
                self.send_error(404)
        elif path.startswith("/s/"):
            token = path[3:]
            self._serve_shared_portfolio(token)
        elif path == "/static/common.css":
            self._serve_static_css()
        else:
            self.send_error(404)

    def _serve_static_css(self):
        """Serve common.css with caching headers."""
        css_path = _TEMPLATES_DIR / "assets" / "common.css"
        try:
            with open(css_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404)

    def _serve_robots_txt(self):
        body = (
            "User-agent: *\n"
            "Allow: /\n"
            "Disallow: /admin\n"
            "Disallow: /api\n"
            "Disallow: /settings\n"
            "Disallow: /import\n"
            "Disallow: /export/\n"
            "Disallow: /s/\n"
            "\n"
            f"Sitemap: {APP_BASE_URL.rstrip('/')}/sitemap.xml\n"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _serve_sitemap_xml(self):
        base = APP_BASE_URL.rstrip("/")
        urls = ["/", "/pricing", "/report", "/login"]
        lines = ['<?xml version="1.0" encoding="UTF-8"?>']
        lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
        for u in urls:
            lines.append(f"  <url><loc>{base}{u}</loc></url>")
        lines.append("</urlset>")
        body = "\n".join(lines)
        self.send_response(200)
        self.send_header("Content-Type", "application/xml; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_POST(self):
        if self._enforce_https():
            return
        path = urlparse(self.path).path
        if path == "/upload":
            self._handle_upload()
        elif path == "/sync":
            self._handle_sync()
        elif path == "/login":
            self._handle_login()
        elif path.startswith("/invite/"):
            token = path[len("/invite/"):]
            self._handle_invite_accept(token)
        elif path == "/admin/users":
            self._handle_admin_create_user()
        elif path.startswith("/admin/users/") and path.endswith("/role"):
            parts = path.split("/")
            # /admin/users/{id}/role
            if len(parts) == 5:
                self._handle_admin_set_role(parts[3])
        elif path == "/webhook/stripe":
            self._handle_stripe_webhook()
        elif path == "/reset-password":
            self._handle_reset_password_request()
        elif path.startswith("/reset-password/"):
            token = path[len("/reset-password/"):]
            self._handle_reset_password_confirm(token)
        elif path == "/account/change-password":
            self._handle_change_password()
        elif path == "/account/delete":
            self._handle_delete_account()
        elif path == "/api/notes":
            self._api_create_note()
        elif path == "/api/onboarding-complete":
            self._api_onboarding_complete()
        elif path == "/api/demo-toggle":
            self._api_demo_toggle()
        elif path == "/import/preview":
            self._handle_import_preview()
        elif path == "/import/validate":
            self._handle_import_validate()
        elif path == "/import/run":
            self._handle_import_run()
        elif path == "/api/email-preferences":
            self._api_save_email_preferences()
        elif path == "/api/edavki-filed":
            self._api_save_edavki_filed()
        elif path == "/api/shares":
            self._api_create_share()
        elif path.startswith("/api/shares/") and path.endswith("/delete"):
            share_id = path[len("/api/shares/"):-len("/delete")]
            self._api_delete_share(share_id)
        elif path == "/api/goals":
            self._api_create_goal()
        elif path.startswith("/api/goals/") and path.endswith("/delete"):
            goal_id = path[len("/api/goals/"):-len("/delete")]
            if goal_id.isdigit():
                self._api_delete_goal(int(goal_id))
            else:
                self.send_error(404)
        else:
            self.send_error(404)

    def do_PUT(self):
        if self._enforce_https():
            return
        path = urlparse(self.path).path
        parts = path.split("/")
        # /api/notes/<id>
        if len(parts) == 4 and parts[1] == "api" and parts[2] == "notes" and parts[3].isdigit():
            self._api_update_note(int(parts[3]))
        # /api/goals/<id>
        elif len(parts) == 4 and parts[1] == "api" and parts[2] == "goals" and parts[3].isdigit():
            self._api_update_goal(int(parts[3]))
        else:
            self.send_error(404)

    def do_DELETE(self):
        if self._enforce_https():
            return
        path = urlparse(self.path).path
        parts = path.split("/")
        # /api/notes/<id>
        if len(parts) == 4 and parts[1] == "api" and parts[2] == "notes" and parts[3].isdigit():
            self._api_delete_note(int(parts[3]))
        # /api/goals/<id>
        elif len(parts) == 4 and parts[1] == "api" and parts[2] == "goals" and parts[3].isdigit():
            self._api_delete_goal(int(parts[3]))
        else:
            self.send_error(404)

    # ------------------------------------------------------------------
    # Login / logout
    # ------------------------------------------------------------------

    def _serve_login_page(self, error: str = ""):
        template = _page_env.get_template("pages/login.html.j2")
        html = template.render(
            error=error,
            app_base_url=APP_BASE_URL.rstrip("/"),
            fouc_script=_FOUC_SCRIPT,
            common_js=_COMMON_JS,
            show_header=False,
            show_drop_import=False
        )
        self._html_response(html)

    def _handle_login(self):
        from .audit import log_event
        ip = _get_client_ip(self)

        retry_after = _check_rate_limit(ip)
        if retry_after is not None:
            self.send_response(429)
            self.send_header("Retry-After", str(retry_after))
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._add_security_headers()
            self.end_headers()
            template = _page_env.get_template("pages/login.html.j2")
            html = template.render(
                error=f"Too many login attempts. Please try again in {retry_after // 60 + 1} minutes.",
                app_base_url=APP_BASE_URL.rstrip("/"),
                fouc_script=_FOUC_SCRIPT,
                common_js=_COMMON_JS,
                show_header=False,
                show_drop_import=False
            )
            self.wfile.write(html.encode("utf-8"))
            log_event("login_rate_limited", ip_address=ip)
            return

        body = self._read_body()
        fields = parse_qs(body.decode("utf-8", errors="replace"))
        username_or_email = fields.get("username", [""])[0].strip()
        password = fields.get("password", [""])[0]

        from .users import authenticate
        try:
            user = authenticate(username_or_email, password)
        except Exception:
            self._serve_login_page(error="Login service unavailable. Please try again later.")
            return
        if not user:
            _record_login_attempt(ip)
            log_event("login_failed", username=username_or_email, ip_address=ip, success=False)
            self._serve_login_page(error="Invalid username or password.")
            return

        _login_attempts.pop(ip, None)
        log_event("login_success", username=user.username, ip_address=ip)
        token = _create_session(user)
        self.send_response(302)
        self.send_header("Location", "/")
        self.send_header(
            "Set-Cookie",
            f"session={token}; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL}; Path=/"
        )
        self.end_headers()

    def _handle_logout(self):
        from .audit import log_event
        from .users import delete_session as _db_delete_session
        session = _get_session(self)
        if session:
            log_event("logout", username=session["username"], ip_address=_get_client_ip(self))
        cookie_header = self.headers.get("Cookie", "")
        c = SimpleCookie()
        c.load(cookie_header)
        morsel = c.get("session")
        if morsel:
            _db_delete_session(morsel.value)
        self.send_response(302)
        self.send_header("Location", "/")
        self.send_header(
            "Set-Cookie",
            "session=; HttpOnly; SameSite=Lax; Max-Age=0; Path=/"
        )
        self.end_headers()

    def _handle_magic_login(self, token: str):
        from .users import consume_magic_token
        user = consume_magic_token(token)
        if not user:
            self._html_response(_error_html("This login link is invalid, expired, or has already been used."))
            return
        session_token = _create_session(user)
        self.send_response(302)
        self.send_header("Location", "/report")
        self.send_header(
            "Set-Cookie",
            f"session={session_token}; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL}; Path=/"
        )
        self.end_headers()

    # ------------------------------------------------------------------
    # Invite (set password)
    # ------------------------------------------------------------------

    def _serve_invite_page(self, token: str, error: str = ""):
        from .users import get_user_by_invite_token
        user = get_user_by_invite_token(token)
        if not user:
            self._html_response(_error_html("This invite link is invalid or has expired."))
            return
        template = _page_env.get_template("pages/invite.html.j2")
        html = template.render(
            token=token,
            email=user.email,
            error=error,
            fouc_script=_FOUC_SCRIPT,
            common_js=_COMMON_JS,
            show_header=False,
            show_drop_import=False
        )
        self._html_response(html)

    def _handle_invite_accept(self, token: str):
        body = self._read_body()
        fields = parse_qs(body.decode("utf-8", errors="replace"))
        password = fields.get("password", [""])[0]
        confirm = fields.get("confirm", [""])[0]

        if not password or len(password) < 8:
            self._serve_invite_page(token, error="Password must be at least 8 characters.")
            return
        if password != confirm:
            self._serve_invite_page(token, error="Passwords do not match.")
            return

        from .users import accept_invite
        user = accept_invite(token, password)
        if not user:
            self._html_response(_error_html("This invite link is invalid or has expired."))
            return

        session_token = _create_session(user)
        self.send_response(302)
        self.send_header("Location", "/")
        self.send_header(
            "Set-Cookie",
            f"session={session_token}; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL}; Path=/"
        )
        self.end_headers()

    # ------------------------------------------------------------------
    # Upload page (main UI)
    # ------------------------------------------------------------------

    def _serve_upload_page(self):
        session = _get_session(self)
        session_token = _get_session_token(self)
        is_demo_view = bool(session_token and _DEMO_VIEW.get(session_token, False))
        username = session["username"] if session else None
        role = session["role"] if session else "guest"
        is_premium = role in ("premium", "admin")

        template = _page_env.get_template("pages/upload.html.j2")
        html = template.render(
            fouc_script=_FOUC_SCRIPT,
            common_js=_COMMON_JS,
            show_header=True,
            show_drop_import=is_premium,
            username=username,
            role=role,
            is_premium=is_premium,
            is_demo_view=is_demo_view,
            app_base_url=APP_BASE_URL.rstrip("/"),
            robots="index, follow",
        )
        self._html_response(html)

    # ------------------------------------------------------------------
    # Status (JSON)
    # ------------------------------------------------------------------

    def _serve_status(self):
        session = _get_session(self)
        session_token = _get_session_token(self)
        conn = _portfolio_conn(session, session_token)
        # Determine actual DB path being used (respects demo toggle)
        if session_token and _DEMO_VIEW.get(session_token, False):
            db_path = DEMO_DB
        elif session and session["role"] in ("premium", "admin"):
            db_path = _user_db_path(session["username"])
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
        self._json_response(data)

    # ------------------------------------------------------------------
    # Upload (premium/admin only)
    # ------------------------------------------------------------------

    def _handle_upload(self):
        session = _get_session(self)
        if not session or session["role"] not in ("premium", "admin"):
            self._json_response({"error": "Login required to upload files."}, status=403)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 100 * 1024 * 1024:
            self._json_response({"error": "File too large (max 100MB)"}, status=413)
            return

        body = self._read_body(content_length)
        fields, files = _parse_multipart(self.headers, body)

        if not files:
            self._json_response({"error": "No files uploaded"}, status=400)
            return

        from .db import get_connection
        from .importer import import_csv

        conn = get_connection(db_path=_user_db_path(session["username"]))
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
                    result = import_csv(conn, tmp_path, verbose=self.verbose)
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

        from .audit import log_event
        for r in results:
            if "error" not in r:
                log_event("data_import", username=session["username"],
                          ip_address=_get_client_ip(self),
                          detail=f"{r['filename']}: {r.get('new',0)} new rows")
        self._json_response({"results": results})

    # ------------------------------------------------------------------
    # Sync (premium/admin only)
    # ------------------------------------------------------------------

    def _handle_sync(self):
        session = _get_session(self)
        if not session or session["role"] not in ("premium", "admin"):
            self._json_response({"error": "Login required to sync prices."}, status=403)
            return

        from .db import get_connection
        from .price_fetcher import sync_all
        from .prices_db import get_prices_connection
        from .analytics_cache import invalidate_cache
        from .tax_cache import invalidate_current_year_tax
        from .report_cache import invalidate_user_html

        conn = get_connection(db_path=_user_db_path(session["username"]))
        prices_conn = get_prices_connection()
        try:
            sync_all(conn, verbose=self.verbose, prices_conn=prices_conn)
            invalidate_cache(conn)
            invalidate_current_year_tax(conn)
            invalidate_user_html(session["username"])
            self._json_response({"ok": True})
        except Exception as e:
            self._json_response({"error": str(e)}, status=500)
        finally:
            prices_conn.close()
            conn.close()

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def _serve_report(self):
        session = _get_session(self)
        from .analytics import compute_analytics
        from .analytics_cache import compute_data_hash, get_cached, put_cache
        from .report_cache import get_cached_html, put_cached_html
        from .tax import compute_tax_report
        from .tax_cache import get_cached_tax, put_tax_cache
        from .html_report import (generate_html_report, query_transactions,
                                   query_real_estate, query_fire_config,
                                   query_investment_notes)
        from datetime import datetime

        # Parse country from query string, default to SI
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        country = qs.get("country", ["SI"])[0].upper()

        from .prices_db import get_prices_conn_or_none

        session_token = _get_session_token(self)
        username = session["username"] if session else "_demo"
        conn = _portfolio_conn(session, session_token)
        prices_conn = get_prices_conn_or_none()
        try:
            data_hash = compute_data_hash(conn, prices_conn)
            etag = f'"{data_hash}"'

            if_none_match = self.headers.get("If-None-Match", "")
            if if_none_match == etag:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.end_headers()
                return

            cached_html = get_cached_html(username, data_hash)
            if cached_html is not None:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("ETag", etag)
                self.end_headers()
                self.wfile.write(cached_html.encode("utf-8"))
                return

            def _cached_analytics(scope):
                cached = get_cached(conn, scope, data_hash)
                if cached is not None:
                    return cached
                result = compute_analytics(conn, scope=scope, prices_conn=prices_conn)
                put_cache(conn, scope, data_hash, result)
                return result

            analytics = _cached_analytics("all")
            tax_by_year = {}
            try:
                current_year = datetime.now().year
                years_with_tx = [
                    int(r[0]) for r in conn.execute(
                        "SELECT DISTINCT strftime('%Y', date) FROM transactions "
                        "WHERE asset_class != 'realestate' ORDER BY 1"
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
                                                       prices_conn=prices_conn)
                            put_tax_cache(conn, yr, "all", country, data_hash, report, current_year)
                            tax_by_year[yr] = report
                    except Exception:
                        pass
            except Exception:
                pass
            transactions = query_transactions(conn)
            # Lazy-load: pass only class names; frontend fetches per-class data on demand
            available_classes = [r[0] for r in conn.execute("SELECT DISTINCT asset_class FROM transactions").fetchall()]
            re_data = query_real_estate(conn, prices_conn=prices_conn)
            fire_cfg = query_fire_config(conn)
            notes = query_investment_notes(conn)
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

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("ETag", etag)
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        except ValueError as e:
            self._html_response(_error_html(str(e)))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"Error generating report: {e}".encode("utf-8"))
        finally:
            if prices_conn:
                prices_conn.close()
            conn.close()

    # ------------------------------------------------------------------
    # Analytics API (lazy-load per-class)
    # ------------------------------------------------------------------

    def _api_get_analytics(self, scope: str):
        valid_scopes = ("stock", "cfd", "crypto", "savings")
        if scope not in valid_scopes:
            self._json_response({"error": f"Invalid scope. Must be one of: {', '.join(valid_scopes)}"}, status=400)
            return
        session = _get_session(self)
        conn = _portfolio_conn(session)
        from .prices_db import get_prices_conn_or_none
        prices_conn = get_prices_conn_or_none()
        try:
            from .analytics import compute_analytics
            from .analytics_cache import compute_data_hash, get_cached, put_cache
            data_hash = compute_data_hash(conn, prices_conn)
            cached = get_cached(conn, scope, data_hash)
            if cached is not None:
                ac_analytics = cached
            else:
                ac_analytics = compute_analytics(conn, scope=scope, prices_conn=prices_conn)
                put_cache(conn, scope, data_hash, ac_analytics)

            ac_daily = ac_analytics.daily_series
            result = {
                "dates": [str(d) for d in ac_daily.index],
                "value_eur": [round(float(v), 2) for v in ac_daily["value_eur"]],
                "invested_eur": [round(float(v), 2) for v in ac_daily["invested_eur"]],
                "dividends_eur": [round(float(v), 2) for v in ac_daily["dividends_eur"]],
                "realized_gain_eur": [round(float(v), 2) for v in ac_daily["realized_gain_eur"]],
                "perf_index": [round(float(v), 2) for v in ac_daily["perf_index"]] if "perf_index" in ac_daily.columns else [],
                "summary": {
                    "portfolio_value_eur": round(ac_analytics.portfolio_value_eur, 2),
                    "total_invested_eur": round(ac_analytics.total_invested_eur, 2),
                    "absolute_gain_eur": round(ac_analytics.absolute_gain_eur, 2),
                    "total_return_pct": round(ac_analytics.total_return_pct, 2),
                    "cagr_pct": round(ac_analytics.cagr_pct, 2) if ac_analytics.cagr_pct else None,
                    "twr_pct": round(ac_analytics.twr_pct, 2) if ac_analytics.twr_pct else None,
                    "max_drawdown_pct": round(ac_analytics.max_drawdown_pct, 2),
                    "max_drawdown_peak_date": ac_analytics.max_drawdown_peak_date,
                    "max_drawdown_trough_date": ac_analytics.max_drawdown_trough_date,
                    "risk_metrics": ac_analytics.risk_metrics,
                },
                "gains": {
                    "realized_eur": round(ac_analytics.total_realized_gain_eur, 2),
                    "unrealized_eur": round(ac_analytics.total_unrealized_gain_eur, 2),
                    "dividends_eur": round(ac_analytics.total_dividends_eur, 2),
                    "fees_eur": round(ac_analytics.total_fees_eur, 2),
                },
                "positions": sorted(
                    [
                        {
                            "ticker": p.ticker,
                            "quantity": round(p.quantity, 4),
                            "cost_basis_eur": round(p.cost_basis_eur, 2),
                            "avg_cost_eur": round(p.cost_basis_eur / p.quantity, 4) if p.quantity else 0,
                            "market_value_eur": round(p.market_value_eur, 2),
                            "unrealized_gain_eur": round(p.unrealized_gain_eur, 2),
                            "unrealized_gain_pct": round(p.unrealized_gain_pct, 2),
                            "weight_pct": round(p.weight_pct, 2),
                            "realized_gain_eur": round(p.realized_gain_eur, 2),
                        }
                        for p in ac_analytics.positions
                    ],
                    key=lambda x: x["market_value_eur"],
                    reverse=True,
                ),
                "closed_positions": sorted(
                    [
                        {
                            "ticker": p.ticker,
                            "total_cost_eur": round(p.total_cost_eur, 2),
                            "total_proceeds_eur": round(p.total_proceeds_eur, 2),
                            "realized_gain_eur": round(p.realized_gain_eur, 2),
                            "realized_gain_pct": round(p.realized_gain_pct, 2),
                        }
                        for p in ac_analytics.closed_positions
                    ],
                    key=lambda x: abs(x["realized_gain_eur"]),
                    reverse=True,
                ),
                "position_lots": {
                    ticker: [
                        {"qty": round(qty, 4), "cost_eur": round(cost, 4), "date": date}
                        for qty, cost, date in lots
                    ]
                    for ticker, lots in ac_analytics.position_lots.items()
                },
            }
            self._json_response(result)
        except ValueError as e:
            self._json_response({"error": str(e)}, status=400)
        except Exception as e:
            self._json_response({"error": f"Analytics computation failed: {e}"}, status=500)
        finally:
            if prices_conn:
                prices_conn.close()
            conn.close()

    # ------------------------------------------------------------------
    # Tax exports
    # ------------------------------------------------------------------

    def _export_year(self):
        """Parse year from query string and validate session. Returns (session, year) or sends error."""
        session = _get_session(self)
        if not session or session["role"] not in ("premium", "admin"):
            self._json_response({"error": "Login required."}, status=403)
            return None, None
        qs = parse_qs(urlparse(self.path).query)
        try:
            year = int(qs.get("year", [0])[0])
        except (ValueError, IndexError):
            self._json_response({"error": "Invalid year."}, status=400)
            return None, None
        if year < 2000 or year > 2100:
            self._json_response({"error": "Invalid year."}, status=400)
            return None, None
        return session, year

    def _handle_export_edavki(self):
        session, year = self._export_year()
        if session is None:
            return
        import pandas as pd
        from .revolut_parser import RevolutTransaction
        from .edavki_generator import EDavkiGenerator

        conn = _portfolio_conn(session)
        try:
            rows = conn.execute(
                "SELECT date, ticker, type, quantity, price_per_share, total_amount, "
                "currency, fx_rate, asset_class FROM transactions "
                "WHERE asset_class = 'stock' ORDER BY date"
            ).fetchall()
            # Convert DB rows to RevolutTransaction objects
            transactions = []
            for r in rows:
                s = pd.Series({
                    "Type": r[2], "Ticker": r[1], "Quantity": r[3],
                    "Price per share": r[4], "Total Amount": r[5],
                    "Currency": r[6], "FX Rate": r[7],
                    "Completed Date": r[0], "Date": r[0],
                    "State": "COMPLETED",
                })
                transactions.append(RevolutTransaction(s))

            gen = EDavkiGenerator()
            gen.generate_xml(transactions, year)
            xml_bytes = gen.to_string(pretty_print=True).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/xml; charset=utf-8")
            self.send_header("Content-Disposition",
                             f'attachment; filename="Doh_KDVP_{year}.xml"')
            self.send_header("Content-Length", str(len(xml_bytes)))
            self.end_headers()
            self.wfile.write(xml_bytes)
        except Exception as e:
            self._json_response({"error": str(e)}, status=500)
        finally:
            conn.close()

    def _handle_export_fifo_csv(self):
        session, year = self._export_year()
        if session is None:
            return
        from .tax import compute_tax_report
        import csv
        import io

        conn = _portfolio_conn(session)
        try:
            report = compute_tax_report(conn, year=year, include_unrealized=False, scope="all")
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow([
                "Ticker", "Asset Class", "Sell Date", "Quantity",
                "Proceeds EUR", "Cost Basis EUR", "Gain EUR",
                "Std Costs EUR", "Holding Years", "Tax Rate", "Tax EUR",
            ])
            for s in report.realized_sales:
                writer.writerow([
                    s.ticker, s.asset_class, s.sell_date,
                    f"{s.quantity:.6f}", f"{s.sell_price_eur:.2f}",
                    f"{s.cost_basis_eur:.2f}", f"{s.gain_eur:.2f}",
                    f"{s.std_costs_eur:.2f}", f"{s.holding_years:.2f}",
                    f"{s.tax_rate:.4f}", f"{s.tax_eur:.2f}",
                ])
            csv_bytes = buf.getvalue().encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition",
                             f'attachment; filename="fifo_transactions_{year}.csv"')
            self.send_header("Content-Length", str(len(csv_bytes)))
            self.end_headers()
            self.wfile.write(csv_bytes)
        except Exception as e:
            self._json_response({"error": str(e)}, status=500)
        finally:
            conn.close()

    def _handle_export_tax_pdf(self):
        session, year = self._export_year()
        if session is None:
            return
        from .tax import compute_tax_report
        from .pdf_report import generate_tax_pdf

        qs = parse_qs(urlparse(self.path).query)
        country = qs.get("country", ["SI"])[0].upper()

        conn = _portfolio_conn(session)
        try:
            report = compute_tax_report(conn, year=year, include_unrealized=False,
                                        scope="all", country=country)
            pdf_bytes = generate_tax_pdf(report, country=country)

            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Disposition",
                             f'attachment; filename="tax_summary_{country}_{year}.pdf"')
            self.send_header("Content-Length", str(len(pdf_bytes)))
            self.end_headers()
            self.wfile.write(pdf_bytes)
        except Exception as e:
            self._json_response({"error": str(e)}, status=500)
        finally:
            conn.close()

    def _handle_export_doh_div(self):
        session, year = self._export_year()
        if session is None:
            return
        from .doh_div_generator import DohDivGenerator, build_dividend_entries

        conn = _portfolio_conn(session)
        try:
            entries = build_dividend_entries(conn, year)
            if not entries:
                self._json_response({"error": f"No dividends for {year}"}, status=404)
                return

            gen = DohDivGenerator()
            gen.generate_xml(entries, year)
            xml_bytes = gen.to_string(pretty_print=True).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/xml; charset=utf-8")
            self.send_header("Content-Disposition",
                             f'attachment; filename="Doh_Div_{year}.xml"')
            self.send_header("Content-Length", str(len(xml_bytes)))
            self.end_headers()
            self.wfile.write(xml_bytes)
        except Exception as e:
            self._json_response({"error": str(e)}, status=500)
        finally:
            conn.close()

    def _handle_dividend_summary(self):
        session = _get_session(self)
        if not session:
            self._json_response({"error": "Unauthorized"}, status=401)
            return
        from .doh_div_generator import build_dividend_entries, compute_dividend_tax_summary

        qs = parse_qs(urlparse(self.path).query)
        year = int(qs.get("year", [str(__import__("datetime").datetime.now().year)])[0])

        conn = _portfolio_conn(session)
        try:
            entries = build_dividend_entries(conn, year)
            summary = compute_dividend_tax_summary(entries, year)
            self._json_response({
                "year": year,
                "total_gross_eur": summary.total_gross_eur,
                "total_withholding_eur": summary.total_withholding_eur,
                "total_net_received_eur": summary.total_net_received_eur,
                "si_tax_liability": summary.si_tax_liability,
                "total_credit_eur": summary.total_credit_eur,
                "net_tax_owed_si": summary.net_tax_owed_si,
                "total_reclaimable_eur": summary.total_reclaimable_eur,
                "entry_count": len(entries),
                "by_country": {
                    k: {
                        "country_name": v["country_name"],
                        "gross_eur": round(v["gross_eur"], 2),
                        "withholding_eur": round(v["withholding_eur"], 2),
                        "credit_eur": round(v["credit_eur"], 2),
                        "reclaimable_eur": round(v["reclaimable_eur"], 2),
                        "treaty_rate": v["treaty_rate"],
                        "count": v["count"],
                    } for k, v in summary.by_country.items()
                },
            })
        except Exception as e:
            self._json_response({"error": str(e)}, status=500)
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Admin — user management
    # ------------------------------------------------------------------

    def _serve_admin_page(self):
        session = _get_session(self)
        if not session or session["role"] != "admin":
            self._redirect("/login")
            return
        from .users import list_users
        users = list_users()
        template = _page_env.get_template("pages/admin.html.j2")
        html = template.render(
            users=users,
            current_username=session["username"],
            fouc_script=_FOUC_SCRIPT,
            common_js=_COMMON_JS,
            show_header=True,
            show_drop_import=True,
        )
        self._html_response(html)

    def _serve_audit_log(self):
        session = _get_session(self)
        if not session or session["role"] != "admin":
            self._redirect("/login")
            return
        self._html_response(_audit_log_html(session["username"], session["role"]))

    def _api_audit_events(self):
        session = _get_session(self)
        if not session or session["role"] != "admin":
            self._json_response({"error": "Forbidden"}, status=403)
            return
        from .audit import query_events, get_event_types
        qs = parse_qs(urlparse(self.path).query)
        event_type = qs.get("type", [None])[0]
        username = qs.get("username", [None])[0]
        limit = min(int(qs.get("limit", ["200"])[0]), 1000)
        offset = int(qs.get("offset", ["0"])[0])
        events = query_events(event_type=event_type, username=username, limit=limit, offset=offset)
        types = get_event_types()
        self._json_response({"events": events, "event_types": types})

    def _serve_admin_users_json(self):
        session = _get_session(self)
        if not session or session["role"] != "admin":
            self._json_response({"error": "Forbidden"}, status=403)
            return
        from .users import list_users
        users = list_users()
        self._json_response([
            {"id": u.id, "username": u.username, "email": u.email, "role": u.role,
             "has_password": bool(u.password_hash), "invite_pending": bool(u.invite_token),
             "created_at": u.created_at, "last_login": u.last_login}
            for u in users
        ])

    def _handle_admin_create_user(self):
        session = _get_session(self)
        if not session or session["role"] != "admin":
            self._json_response({"error": "Forbidden"}, status=403)
            return

        body = self._read_body()
        try:
            data = json.loads(body)
            email = data.get("email", "").strip().lower()
            role = data.get("role", "premium")
        except Exception:
            self._json_response({"error": "Invalid JSON"}, status=400)
            return

        if not email or "@" not in email:
            self._json_response({"error": "Valid email required"}, status=400)
            return
        if role not in ("premium", "admin"):
            self._json_response({"error": "Role must be premium or admin"}, status=400)
            return

        from .users import create_user, get_user_by_email
        if get_user_by_email(email):
            self._json_response({"error": "A user with that email already exists"}, status=409)
            return

        user, raw_token = create_user(email, role=role)
        invite_url = f"{APP_BASE_URL}/invite/{raw_token}"

        # Send invite email
        sent = False
        try:
            from .email_service import send_invite
            send_invite(email, invite_url, user.username)
            sent = True
        except Exception:
            pass  # Don't fail the creation if email fails

        from .audit import log_event
        log_event("admin_create_user", username=session["username"],
                  ip_address=_get_client_ip(self), detail=f"created {user.username} ({email}) role={role}")

        self._json_response({
            "ok": True,
            "username": user.username,
            "invite_url": invite_url,
            "email_sent": sent,
        })

    def _handle_admin_set_role(self, user_id_str: str):
        session = _get_session(self)
        if not session or session["role"] != "admin":
            self._json_response({"error": "Forbidden"}, status=403)
            return

        body = self._read_body()
        try:
            data = json.loads(body)
            role = data.get("role", "")
        except Exception:
            self._json_response({"error": "Invalid JSON"}, status=400)
            return

        try:
            user_id = int(user_id_str)
        except ValueError:
            self._json_response({"error": "Invalid user id"}, status=400)
            return

        from .users import set_role
        ok = set_role(user_id, role)
        if ok:
            from .audit import log_event
            log_event("role_change", username=session["username"],
                      ip_address=_get_client_ip(self), detail=f"user_id={user_id} new_role={role}")
        self._json_response({"ok": ok})

    # ------------------------------------------------------------------
    # Stripe webhook
    # ------------------------------------------------------------------

    def _handle_stripe_webhook(self):
        body = self._read_body()
        sig_header = self.headers.get("Stripe-Signature", "")

        if STRIPE_WEBHOOK_SECRET and not _verify_stripe_signature(body, sig_header, STRIPE_WEBHOOK_SECRET):
            self.send_error(400, "Invalid signature")
            return

        try:
            event = json.loads(body)
        except Exception:
            self.send_error(400, "Invalid JSON")
            return

        event_type = event.get("type", "")
        obj = event.get("data", {}).get("object", {})

        if event_type == "checkout.session.completed":
            # New subscription purchase → create premium user + send invite
            email = obj.get("customer_details", {}).get("email") or obj.get("customer_email", "")
            stripe_customer_id = obj.get("customer", "")
            if email:
                from .users import create_stripe_user
                user, raw_token = create_stripe_user(email, stripe_customer_id)
                if raw_token:
                    invite_url = f"{APP_BASE_URL}/invite/{raw_token}"
                    try:
                        from .email_service import send_invite
                        send_invite(email, invite_url, user.username)
                    except Exception:
                        pass

        elif event_type in (
            "customer.subscription.updated",
            "customer.subscription.deleted",
        ):
            # Subscription state change → sync role to subscription status
            stripe_customer_id = obj.get("customer", "")
            status = obj.get("status", "canceled")
            if stripe_customer_id:
                from .users import update_stripe_subscription_status
                update_stripe_subscription_status(stripe_customer_id, status)

        elif event_type == "invoice.payment_failed":
            # Payment failure → downgrade to guest immediately
            stripe_customer_id = obj.get("customer", "")
            if stripe_customer_id:
                from .users import update_stripe_subscription_status
                update_stripe_subscription_status(stripe_customer_id, "past_due")

        elif event_type == "invoice.payment_succeeded":
            # Payment recovered → re-activate premium
            stripe_customer_id = obj.get("customer", "")
            if stripe_customer_id:
                from .users import update_stripe_subscription_status
                update_stripe_subscription_status(stripe_customer_id, "active")

        self._json_response({"received": True})

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Notes API  (premium + admin only)
    # ------------------------------------------------------------------

    def _notes_conn_or_403(self):
        """Return (session, conn) if user is premium/admin, else send 403 and return (None, None)."""
        session = _get_session(self)
        if not session or session["role"] not in ("premium", "admin"):
            self._json_response({"error": "forbidden"}, 403)
            return None, None
        conn = _portfolio_conn(session)
        return session, conn

    def _api_list_notes(self):
        session = _get_session(self)
        conn = _portfolio_conn(session)
        try:
            from .notes import query_notes_for_report
            notes = query_notes_for_report(conn)
            self._json_response(notes)
        finally:
            conn.close()

    def _api_create_note(self):
        _, conn = self._notes_conn_or_403()
        if conn is None:
            return
        try:
            data = json.loads(self._read_body())
            from .notes import add_note
            note_id = add_note(
                conn,
                title=str(data.get("title", "")).strip(),
                summary=str(data.get("summary", "")).strip(),
                body=str(data.get("body", "")),
                tickers=str(data.get("tickers", "")),
                conviction=data.get("conviction", "medium"),
                action=data.get("action", "watch"),
            )
            from .notes import query_notes_for_report
            all_notes = query_notes_for_report(conn)
            note = next((n for n in all_notes if n["id"] == note_id), None)
            self._json_response(note or {"id": note_id}, 201)
        except (json.JSONDecodeError, KeyError) as e:
            self._json_response({"error": str(e)}, 400)
        finally:
            conn.close()

    def _api_update_note(self, note_id: int):
        _, conn = self._notes_conn_or_403()
        if conn is None:
            return
        try:
            data = json.loads(self._read_body())
            from .notes import edit_note, query_notes_for_report
            edit_note(conn, note_id, **{k: data[k] for k in
                ("title", "summary", "body", "tickers", "conviction", "action")
                if k in data})
            all_notes = query_notes_for_report(conn)
            note = next((n for n in all_notes if n["id"] == note_id), None)
            if note is None:
                self._json_response({"error": "not found"}, 404)
            else:
                self._json_response(note)
        except (json.JSONDecodeError, KeyError) as e:
            self._json_response({"error": str(e)}, 400)
        finally:
            conn.close()

    def _api_delete_note(self, note_id: int):
        _, conn = self._notes_conn_or_403()
        if conn is None:
            return
        try:
            from .notes import delete_note
            ok = delete_note(conn, note_id)
            if ok:
                self._json_response({"deleted": note_id})
            else:
                self._json_response({"error": "not found"}, 404)
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Onboarding API
    # ------------------------------------------------------------------

    def _api_onboarding_status(self):
        """GET /api/onboarding-status — returns {completed, hasData, hasSynced}"""
        session = _get_session(self)
        if not session or session["role"] not in ("premium", "admin"):
            self._json_response({"error": "Login required."}, status=403)
            return

        from .users import get_onboarding_status
        status = get_onboarding_status(session["user_id"])
        self._json_response(status)

    def _api_onboarding_complete(self):
        """POST /api/onboarding-complete — marks onboarding as completed"""
        session = _get_session(self)
        if not session or session["role"] not in ("premium", "admin"):
            self._json_response({"error": "Login required."}, status=403)
            return

        from .users import set_onboarding_completed
        ok = set_onboarding_completed(session["user_id"])
        self._json_response({"ok": ok})

    def _api_demo_toggle(self):
        """POST /api/demo-toggle — toggles demo view for premium/admin users"""
        session = _get_session(self)
        if not session or session["role"] not in ("premium", "admin"):
            self._json_response({"error": "Login required."}, status=403)
            return

        try:
            data = json.loads(self._read_body())
            demo_enabled = bool(data.get("demo", False))

            # Get session token from cookie
            session_token = _get_session_token(self)
            if session_token:
                _DEMO_VIEW[session_token] = demo_enabled

            self._json_response({"ok": True, "demo": demo_enabled})
        except (json.JSONDecodeError, KeyError) as e:
            self._json_response({"error": str(e)}, 400)

    # ------------------------------------------------------------------
    # Goals API
    # ------------------------------------------------------------------

    def _goals_conn_or_403(self):
        session = _get_session(self)
        if not session or session["role"] not in ("premium", "admin"):
            self._json_response({"error": "Login required."}, status=403)
            return None, None
        return session, _portfolio_conn(session)

    def _api_list_goals(self):
        session = _get_session(self)
        conn = _portfolio_conn(session)
        try:
            from .goals import list_goals
            goals = list_goals(conn)
            self._json_response(goals)
        finally:
            conn.close()

    def _api_get_goal(self, goal_id: int):
        session = _get_session(self)
        conn = _portfolio_conn(session)
        try:
            from .goals import get_goal
            goal = get_goal(conn, goal_id)
            if goal is None:
                self._json_response({"error": "not found"}, 404)
            else:
                self._json_response(goal)
        finally:
            conn.close()

    def _api_create_goal(self):
        session, conn = self._goals_conn_or_403()
        if conn is None:
            return
        try:
            data = json.loads(self._read_body())
            name = str(data.get("name", "")).strip()
            target_amount = float(data.get("target_amount_eur", 0))
            target_date = str(data.get("target_date", "")).strip()
            if not name or target_amount <= 0 or not target_date:
                self._json_response({"error": "name, target_amount_eur, and target_date are required"}, 400)
                return
            from .goals import create_goal, get_goal
            goal_id = create_goal(
                conn, name=name, target_amount_eur=target_amount,
                target_date=target_date,
                monthly_contribution=float(data.get("monthly_contribution", 0)),
                scope=str(data.get("scope", "all")),
                tickers=str(data.get("tickers", "")),
            )
            goal = get_goal(conn, goal_id)
            self._json_response(goal, 201)
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            self._json_response({"error": str(e)}, 400)
        finally:
            conn.close()

    def _api_update_goal(self, goal_id: int):
        session, conn = self._goals_conn_or_403()
        if conn is None:
            return
        try:
            data = json.loads(self._read_body())
            from .goals import update_goal, get_goal
            update_goal(conn, goal_id, **data)
            goal = get_goal(conn, goal_id)
            if goal is None:
                self._json_response({"error": "not found"}, 404)
            else:
                self._json_response(goal)
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            self._json_response({"error": str(e)}, 400)
        finally:
            conn.close()

    def _api_delete_goal(self, goal_id: int):
        session, conn = self._goals_conn_or_403()
        if conn is None:
            return
        try:
            from .goals import delete_goal
            ok = delete_goal(conn, goal_id)
            if ok:
                self._json_response({"deleted": goal_id})
            else:
                self._json_response({"error": "not found"}, 404)
        finally:
            conn.close()

    def _api_goal_projection(self, goal_id: int):
        session = _get_session(self)
        conn = _portfolio_conn(session)
        from .prices_db import get_prices_conn_or_none
        prices_conn = get_prices_conn_or_none()
        try:
            from .goals import compute_goal_projection
            projection = compute_goal_projection(conn, goal_id, prices_conn=prices_conn)
            if projection is None:
                self._json_response({"error": "goal not found"}, 404)
                return
            self._json_response({
                "goal_id": projection.goal_id,
                "current_value_eur": projection.current_value_eur,
                "target_amount_eur": projection.target_amount_eur,
                "progress_pct": projection.progress_pct,
                "months_remaining": projection.months_remaining,
                "required_monthly_eur": projection.required_monthly_eur,
                "probability_of_success": projection.probability_of_success,
                "percentile_10": projection.percentile_10,
                "percentile_50": projection.percentile_50,
                "percentile_90": projection.percentile_90,
            })
        except Exception as e:
            self._json_response({"error": f"Projection failed: {e}"}, 500)
        finally:
            if prices_conn:
                prices_conn.close()
            conn.close()

    # ------------------------------------------------------------------
    # Import wizard
    # ------------------------------------------------------------------

    def _serve_import_wizard(self):
        session = _get_session(self)
        if not session or session["role"] not in ("premium", "admin"):
            self._redirect("/login")
            return

        template = _page_env.get_template("pages/import_wizard.html.j2")
        html = template.render(
            fouc_script=_FOUC_SCRIPT,
            common_js=_COMMON_JS,
            show_header=True,
            show_drop_import=False,
            username=session["username"],
            role=session["role"],
        )
        self._html_response(html)

    def _handle_import_preview(self):
        session = _get_session(self)
        if not session or session["role"] not in ("premium", "admin"):
            self._json_response({"error": "Login required."}, status=403)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 50 * 1024 * 1024:
            self._json_response({"error": "File too large (max 50 MB)."}, status=413)
            return

        body = self._read_body(content_length)
        fields, files = _parse_multipart(self.headers, body)

        if not files:
            self._json_response({"error": "No file received."}, status=400)
            return

        f = files[0]
        filename = f["filename"]
        content = f["content"]

        # Reject binary
        if b"\x00" in content:
            self._json_response({"error": "Binary file rejected."}, status=400)
            return

        # Decode text
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = content.decode("latin-1")
            except Exception:
                self._json_response({"error": "Could not decode file as text."}, status=400)
                return

        # CSV sniff
        import csv as _csv
        import io as _io
        lines = text.splitlines()
        if not lines:
            self._json_response({"error": "File is empty."}, status=400)
            return

        reader = _csv.reader(_io.StringIO(text))
        rows_raw = list(reader)
        if not rows_raw:
            self._json_response({"error": "File is empty."}, status=400)
            return

        headers = rows_raw[0]
        # Retry with semicolon if single column
        if len(headers) <= 1:
            reader2 = _csv.reader(_io.StringIO(text), delimiter=";")
            rows_raw2 = list(reader2)
            if rows_raw2 and len(rows_raw2[0]) > 1:
                rows_raw = rows_raw2
                headers = rows_raw[0]

        if len(headers) <= 1:
            self._json_response({"error": "Could not parse as CSV (comma or semicolon separated)."}, status=400)
            return

        preview_rows = [list(r) for r in rows_raw[1:6]]
        row_count = max(0, len(rows_raw) - 1)

        detected = _detect_asset_class_from_headers(headers)

        # Stage the file
        token = _get_session_token(self)
        tmp_dir = tempfile.mkdtemp(prefix="revolut_import_")
        tmp_path = os.path.join(tmp_dir, filename)
        with open(tmp_path, "wb") as fh:
            fh.write(content)

        _IMPORT_STAGING[token] = {
            "path": tmp_path,
            "dir": tmp_dir,
            "filename": filename,
            "expires": time.time() + 3600,
        }
        _purge_expired_staging()

        self._json_response({
            "headers": headers,
            "rows": preview_rows,
            "detected_asset_class": detected,
            "row_count": row_count,
            "filename": filename,
        })

    def _handle_import_validate(self):
        session = _get_session(self)
        if not session or session["role"] not in ("premium", "admin"):
            self._json_response({"error": "Login required."}, status=403)
            return

        body = self._read_body()
        try:
            data = json.loads(body)
        except Exception:
            self._json_response({"error": "Invalid JSON."}, status=400)
            return

        asset_class = data.get("asset_class", "")
        column_map = data.get("mapping", {})

        if asset_class not in ("stock", "cfd", "crypto", "savings"):
            self._json_response({"error": "Invalid asset class."}, status=400)
            return

        token = _get_session_token(self)
        staging = _IMPORT_STAGING.get(token)
        if not staging or staging["expires"] < time.time():
            if staging:
                _cleanup_staging(token)
            self._json_response({"error": "Upload session expired. Please re-upload the file."}, status=400)
            return

        import pandas as _pd
        from .import_validator import validate_csv

        file_path = staging["path"]
        df = _pd.read_csv(file_path)
        if len(df.columns) == 1 or (len(df.columns) < 3 and ";" in df.columns[0]):
            df = _pd.read_csv(file_path, sep=";")

        # Get existing tickers from the user's portfolio for context
        existing_tickers = []
        try:
            conn = _portfolio_conn(session)
            rows = conn.execute("SELECT DISTINCT ticker FROM transactions WHERE ticker IS NOT NULL").fetchall()
            existing_tickers = [r[0] for r in rows]
            conn.close()
        except Exception:
            pass

        report = validate_csv(df, column_map, asset_class, existing_tickers)
        self._json_response(report.to_dict())

    def _handle_import_run(self):
        session = _get_session(self)
        if not session or session["role"] not in ("premium", "admin"):
            self._json_response({"error": "Login required."}, status=403)
            return

        body = self._read_body()
        try:
            data = json.loads(body)
        except Exception:
            self._json_response({"error": "Invalid JSON."}, status=400)
            return

        asset_class = data.get("asset_class", "")
        column_map = data.get("mapping", {})
        filename = data.get("filename", "")

        if asset_class not in ("stock", "cfd", "crypto", "savings"):
            self._json_response({"error": "Invalid asset class."}, status=400)
            return

        token = _get_session_token(self)
        staging = _IMPORT_STAGING.get(token)
        if not staging or staging["expires"] < time.time():
            if staging:
                _cleanup_staging(token)
            self._json_response({"error": "Upload session expired. Please re-upload the file."}, status=400)
            return

        from .importer import import_csv_mapped
        from .analytics_cache import invalidate_cache
        from .tax_cache import invalidate_current_year_tax
        from .report_cache import invalidate_user_html
        conn = _portfolio_conn(session)
        try:
            result = import_csv_mapped(
                conn,
                staging["path"],
                asset_class=asset_class,
                column_map=column_map,
                filename_hint=filename or staging["filename"],
                verbose=self.verbose,
            )
            invalidate_cache(conn)
            invalidate_current_year_tax(conn)
            invalidate_user_html(session["username"])
        except Exception as e:
            conn.close()
            self._json_response({"error": str(e)}, status=500)
            return
        finally:
            conn.close()

        _cleanup_staging(token)
        self._json_response({
            "total": result.total,
            "new": result.new,
            "skipped": result.skipped,
        })

    def _serve_settings_page(self):
        session = _get_session(self)
        if not session or session["role"] not in ("premium", "admin"):
            self._redirect("/login")
            return
        template = _page_env.get_template("pages/settings.html.j2")
        html = template.render(
            username=session["username"],
            role=session["role"],
            billing_portal_url=STRIPE_BILLING_PORTAL_URL,
            fouc_script=_FOUC_SCRIPT,
            common_js=_COMMON_JS,
            show_header=True,
            show_drop_import=True,
        )
        self._html_response(html)

    def _serve_pricing_page(self):
        session = _get_session(self)
        username = session["username"] if session else ""
        role = session["role"] if session else "guest"
        html = _pricing_html(username, role)
        self._html_response(html)

    # ------------------------------------------------------------------
    # Password reset
    # ------------------------------------------------------------------

    def _serve_reset_password_page(self, error: str = "", success: str = ""):
        template = _page_env.get_template("pages/reset_password_request.html.j2")
        html = template.render(
            error=error,
            success=success,
            fouc_script=_FOUC_SCRIPT,
            common_js=_COMMON_JS,
            show_header=False,
            show_drop_import=False
        )
        self._html_response(html)

    def _handle_reset_password_request(self):
        from .users import create_password_reset_token
        body = self._read_body()
        fields = parse_qs(body.decode("utf-8", errors="replace"))
        email = fields.get("email", [""])[0].strip().lower()
        if not email:
            self._serve_reset_password_page(error="Please enter your email address.")
            return
        token = create_password_reset_token(email)
        if token:
            reset_url = f"{APP_BASE_URL}/reset-password/{token}"
            try:
                from .email_service import send_password_reset
                send_password_reset(email, reset_url)
            except Exception:
                pass
        # Always show success (don't leak whether email exists)
        self._serve_reset_password_page(
            success="If that email is registered, you will receive a password reset link shortly."
        )

    def _serve_reset_password_confirm_page(self, token: str, error: str = ""):
        from .users import get_users_db
        conn = get_users_db()
        try:
            row = conn.execute(
                "SELECT * FROM password_reset_tokens WHERE token = ? AND used_at IS NULL",
                (token,)
            ).fetchone()
        finally:
            conn.close()
        if not row:
            self._html_response(_error_html("This password reset link is invalid or has already been used."))
            return
        from datetime import datetime, timezone
        try:
            from datetime import datetime, timezone
            expires = datetime.fromisoformat(row["expires_at"])
            if datetime.now(timezone.utc) > expires:
                self._html_response(_error_html("This password reset link has expired. Please request a new one."))
                return
        except ValueError:
            pass
        template = _page_env.get_template("pages/reset_password_confirm.html.j2")
        html = template.render(
            token=token,
            error=error,
            fouc_script=_FOUC_SCRIPT,
            common_js=_COMMON_JS,
            show_header=False,
            show_drop_import=False
        )
        self._html_response(html)

    def _handle_reset_password_confirm(self, token: str):
        from .users import consume_password_reset_token
        body = self._read_body()
        fields = parse_qs(body.decode("utf-8", errors="replace"))
        password = fields.get("password", [""])[0]
        confirm = fields.get("confirm", [""])[0]
        if not password or len(password) < 8:
            self._serve_reset_password_confirm_page(token, error="Password must be at least 8 characters.")
            return
        if password != confirm:
            self._serve_reset_password_confirm_page(token, error="Passwords do not match.")
            return
        user = consume_password_reset_token(token, password)
        if not user:
            self._html_response(_error_html("This password reset link is invalid, expired, or already used."))
            return
        from .audit import log_event
        log_event("password_reset", username=user.username, ip_address=_get_client_ip(self))
        session_token = _create_session(user)
        self.send_response(302)
        self.send_header("Location", "/")
        self.send_header(
            "Set-Cookie",
            f"session={session_token}; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL}; Path=/"
        )
        self.end_headers()

    # ------------------------------------------------------------------
    # Account settings (change password, delete account)
    # ------------------------------------------------------------------

    def _serve_account_page(self):
        session = _get_session(self)
        if not session:
            self._redirect("/login")
            return
        from .users import get_user_by_id
        user = get_user_by_id(session["user_id"])
        template = _page_env.get_template("pages/account.html.j2")
        html = template.render(
            username=session["username"],
            role=session["role"],
            email=user.email if user else "",
            subscription_status=(user.stripe_subscription_status or "—") if user else "—",
            billing_portal_url=STRIPE_BILLING_PORTAL_URL,
            fouc_script=_FOUC_SCRIPT,
            common_js=_COMMON_JS,
            show_header=True,
            show_drop_import=False,
        )
        self._html_response(html)

    def _handle_change_password(self):
        session = _get_session(self)
        if not session:
            self._json_response({"error": "Not authenticated"}, 401)
            return
        body = self._read_body()
        fields = parse_qs(body.decode("utf-8", errors="replace"))
        current_pw = fields.get("current_password", [""])[0]
        new_pw = fields.get("new_password", [""])[0]
        confirm_pw = fields.get("confirm_password", [""])[0]

        from .users import get_user_by_id, verify_password, change_password
        user = get_user_by_id(session["user_id"])
        if not user:
            self._json_response({"error": "User not found"}, 400)
            return
        if user.password_hash and not verify_password(user.password_hash, current_pw):
            self._json_response({"error": "Current password is incorrect."}, 400)
            return
        if not new_pw or len(new_pw) < 8:
            self._json_response({"error": "New password must be at least 8 characters."}, 400)
            return
        if new_pw != confirm_pw:
            self._json_response({"error": "Passwords do not match."}, 400)
            return
        change_password(session["user_id"], new_pw)
        from .audit import log_event
        log_event("password_change", username=session["username"], ip_address=_get_client_ip(self))
        self._json_response({"ok": True})

    def _handle_delete_account(self):
        session = _get_session(self)
        if not session:
            self._json_response({"error": "Not authenticated"}, 401)
            return
        if session["role"] == "admin":
            self._json_response({"error": "Admin accounts cannot be self-deleted."}, 403)
            return
        from .users import delete_user, delete_session as _db_delete_session
        # Delete session first
        token = _get_session_token(self)
        if token:
            _db_delete_session(token)
        delete_user(session["user_id"])
        self.send_response(302)
        self.send_header("Location", "/")
        self.send_header(
            "Set-Cookie",
            "session=; HttpOnly; SameSite=Lax; Max-Age=0; Path=/"
        )
        self.end_headers()

    def _api_get_email_preferences(self):
        session = _get_session(self)
        if not session or session["role"] not in ("premium", "admin"):
            self._json_response({"error": "Login required."}, status=403)
            return
        from .email_reports import get_preferences
        prefs = get_preferences(session["user_id"])
        self._json_response({
            "weekly_enabled": prefs.weekly_enabled,
            "monthly_enabled": prefs.monthly_enabled,
            "alert_enabled": prefs.alert_enabled,
            "digest_enabled": prefs.digest_enabled,
            "scope": prefs.scope,
            "country": prefs.country,
        })

    def _api_save_email_preferences(self):
        session = _get_session(self)
        if not session or session["role"] not in ("premium", "admin"):
            self._json_response({"error": "Login required."}, status=403)
            return
        body = self._read_body()
        try:
            data = json.loads(body)
        except Exception:
            self._json_response({"error": "Invalid JSON."}, status=400)
            return
        from .email_reports import save_preferences
        save_preferences(
            user_id=session["user_id"],
            weekly_enabled=bool(data.get("weekly_enabled", False)),
            monthly_enabled=bool(data.get("monthly_enabled", True)),
            alert_enabled=bool(data.get("alert_enabled", False)),
            digest_enabled=bool(data.get("digest_enabled", False)),
            scope=data.get("scope", "all"),
            country=data.get("country", "SI"),
        )
        self._json_response({"ok": True})

    # ------------------------------------------------------------------
    # eDavki filed-year tracking
    # ------------------------------------------------------------------

    def _api_get_edavki_filed(self):
        session = _get_session(self)
        if not session or session["role"] not in ("premium", "admin"):
            self._json_response({"error": "Login required."}, status=403)
            return
        conn = _portfolio_conn(session)
        try:
            row = conn.execute(
                "SELECT value FROM metadata WHERE key = 'edavki_filed_years'"
            ).fetchone()
            filed_years = json.loads(row[0]) if row and row[0] else []
            self._json_response({"filed_years": filed_years})
        finally:
            conn.close()

    def _api_save_edavki_filed(self):
        session = _get_session(self)
        if not session or session["role"] not in ("premium", "admin"):
            self._json_response({"error": "Login required."}, status=403)
            return
        body = self._read_body()
        try:
            data = json.loads(body)
        except Exception:
            self._json_response({"error": "Invalid JSON."}, status=400)
            return
        filed_years = data.get("filed_years")
        dismissed_until = data.get("dismissed_until")
        if filed_years is not None and not isinstance(filed_years, list):
            self._json_response({"error": "filed_years must be a list."}, status=400)
            return
        conn = _portfolio_conn(session)
        try:
            if filed_years is not None:
                conn.execute(
                    "INSERT OR REPLACE INTO metadata (key, value) VALUES ('edavki_filed_years', ?)",
                    (json.dumps(sorted(set(int(y) for y in filed_years))),)
                )
            if dismissed_until is not None:
                conn.execute(
                    "INSERT OR REPLACE INTO metadata (key, value) VALUES ('edavki_widget_dismissed_until', ?)",
                    (str(dismissed_until),)
                )
            conn.commit()
            from .report_cache import invalidate_user_html
            try:
                invalidate_user_html(session["username"])
            except Exception:
                pass
            self._json_response({"ok": True})
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Portfolio sharing
    # ------------------------------------------------------------------

    def _api_list_shares(self):
        session = _get_session(self)
        if not session or session["role"] not in ("premium", "admin"):
            self._json_response({"error": "Login required."}, status=403)
            return
        from .users import list_shares
        shares = list_shares(session["user_id"])
        self._json_response([{
            "id": s.id,
            "token": s.share_token,
            "label": s.label,
            "scope": s.scope,
            "percentage_only": s.percentage_only,
            "include_holdings": s.include_holdings,
            "created_at": s.created_at,
            "expires_at": s.expires_at,
            "access_count": s.access_count,
            "url": f"{APP_BASE_URL.rstrip('/')}/s/{s.share_token}",
        } for s in shares])

    def _api_create_share(self):
        session = _get_session(self)
        if not session or session["role"] not in ("premium", "admin"):
            self._json_response({"error": "Login required."}, status=403)
            return
        body = self._read_body()
        try:
            data = json.loads(body) if body else {}
        except Exception:
            data = {}
        from .users import create_share
        share = create_share(
            user_id=session["user_id"],
            label=data.get("label"),
            scope=data.get("scope", "all"),
            percentage_only=data.get("percentage_only", True),
            include_holdings=data.get("include_holdings", False),
            expires_hours=data.get("expires_hours"),
        )
        self._json_response({
            "id": share.id,
            "token": share.share_token,
            "url": f"{APP_BASE_URL.rstrip('/')}/s/{share.share_token}",
        })

    def _api_delete_share(self, share_id_str: str):
        session = _get_session(self)
        if not session or session["role"] not in ("premium", "admin"):
            self._json_response({"error": "Login required."}, status=403)
            return
        try:
            share_id = int(share_id_str)
        except ValueError:
            self._json_response({"error": "Invalid share ID."}, status=400)
            return
        from .users import delete_share
        deleted = delete_share(share_id, session["user_id"])
        self._json_response({"ok": deleted})

    def _serve_shared_portfolio(self, token: str):
        from .users import get_share_by_token, get_user_by_id
        from .analytics import compute_analytics
        from .analytics_cache import compute_data_hash, get_cached, put_cache
        from .html_report import generate_html_report, query_transactions
        from .prices_db import get_prices_conn_or_none

        share = get_share_by_token(token)
        if not share:
            self._html_response(_shared_expired_html(), status=404)
            return

        user = get_user_by_id(share.user_id)
        if not user:
            self._html_response(_shared_expired_html(), status=404)
            return

        conn = None
        prices_conn = None
        try:
            from .db import get_connection
            conn = get_connection(db_path=_user_db_path(user.username))
            prices_conn = get_prices_conn_or_none()

            data_hash = compute_data_hash(conn, prices_conn)

            cached = get_cached(conn, share.scope, data_hash)
            if cached is not None:
                analytics = cached
            else:
                analytics = compute_analytics(conn, scope=share.scope, prices_conn=prices_conn)
                put_cache(conn, share.scope, data_hash, analytics)

            transactions = query_transactions(conn) if share.include_holdings else []

            html = generate_html_report(
                analytics, {}, transactions, per_class=None,
                available_classes=[],
                real_estate=None, fire_config=None,
                investment_notes=[], conn=conn,
                country="SI", prices_conn=prices_conn,
                shared_mode=True,
                percentage_only=share.percentage_only,
                include_holdings=share.include_holdings,
            )

            share_meta = json.dumps({
                "shared": True,
                "label": share.label,
                "percentage_only": share.percentage_only,
                "include_holdings": share.include_holdings,
                "scope": share.scope,
            })
            d_script_end = html.find(";</script>", html.find("<script>const D="))
            if d_script_end != -1:
                html = html[:d_script_end] + f";D.share={share_meta};D.user=null" + html[d_script_end:]

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "public, max-age=300")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"Error loading shared portfolio: {e}".encode("utf-8"))
        finally:
            if prices_conn:
                prices_conn.close()
            if conn:
                conn.close()

    def _read_body(self, length: int | None = None) -> bytes:
        if length is None:
            length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length)

    def _html_response(self, html: str, status: int = 200):
        encoded = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self._add_security_headers()
        self.end_headers()
        self.wfile.write(encoded)

    def _json_response(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._add_security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, path: str):
        self.send_response(302)
        self.send_header("Location", path)
        self.end_headers()


# ---------------------------------------------------------------------------
# Server entry point
# ---------------------------------------------------------------------------

def start_server(host="0.0.0.0", port=8080, verbose=False, reload=False):
    """Start the web server, optionally with file-watching auto-reload."""
    if reload:
        _run_with_reloader(host, port, verbose)
    else:
        _serve(host, port, verbose)


def _serve(host, port, verbose):
    """Run the HTTP server (inner worker)."""
    UploadHandler.verbose = verbose
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer((host, port), UploadHandler)
    print(f"Server running at http://{host}:{port}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


def _run_with_reloader(host, port, verbose):
    """Spawn the server as a subprocess and restart it when source files change."""
    import subprocess
    import signal
    import sys
    from pathlib import Path

    watch_dirs = [
        Path(__file__).resolve().parent,                    # src/
        Path(__file__).resolve().parent / "templates",      # src/templates/
    ]
    watch_extensions = {".py", ".html", ".j2", ".js", ".css", ".json"}

    def _get_mtimes():
        mtimes = {}
        for d in watch_dirs:
            if not d.exists():
                continue
            for f in d.rglob("*"):
                if f.suffix in watch_extensions and f.is_file():
                    try:
                        mtimes[str(f)] = f.stat().st_mtime
                    except OSError:
                        pass
        return mtimes

    env = os.environ.copy()
    env["_RELOADER_CHILD"] = "1"
    cmd = [sys.executable, "-m", "src.cli", "web",
           "--host", host, "--port", str(port)]
    if verbose:
        cmd.append("--verbose")

    print(f"[reloader] Watching {', '.join(str(d) for d in watch_dirs)}", flush=True)
    print(f"[reloader] Extensions: {', '.join(sorted(watch_extensions))}", flush=True)

    proc = None
    try:
        while True:
            proc = subprocess.Popen(cmd, env=env)
            mtimes = _get_mtimes()

            while proc.poll() is None:
                time.sleep(1)
                new_mtimes = _get_mtimes()
                changed = []
                for path, mtime in new_mtimes.items():
                    if mtimes.get(path) != mtime:
                        changed.append(path)
                for path in set(mtimes) - set(new_mtimes):
                    changed.append(path)
                if changed:
                    rel = [os.path.relpath(c) for c in changed[:3]]
                    print(f"\n[reloader] Detected change in: {', '.join(rel)}", flush=True)
                    print("[reloader] Restarting server...", flush=True)
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                    break
                mtimes = new_mtimes

            if proc.returncode is not None and proc.returncode != 0:
                if proc.returncode == -signal.SIGTERM:
                    pass  # normal restart
                else:
                    print(f"[reloader] Server exited with code {proc.returncode}, restarting in 2s...")
                    time.sleep(2)
    except KeyboardInterrupt:
        print("\n[reloader] Shutting down.")
        if proc and proc.poll() is None:
            proc.terminate()
            proc.wait()


# ---------------------------------------------------------------------------
# Shared design system for all non-report pages
# ---------------------------------------------------------------------------

# Jinja2 Environment for page templates
_TEMPLATES_DIR = Path(__file__).parent / "templates"
_page_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=True,
)
_page_env.globals["t"] = lambda key, lang="en": get_translations(lang).get(key, key)

# Prevent flash of unstyled content — runs before paint
_FOUC_SCRIPT = (
    "<script>(function(){var t=localStorage.getItem('theme');"
    "if(!t&&window.matchMedia&&window.matchMedia('(prefers-color-scheme:light)').matches)t='light';"
    "if(t)document.documentElement.setAttribute('data-theme',t);})()</script>"
)

# Theme toggle JS — same logic as report's nav.js
_COMMON_JS = r"""
<script>
function toggleTheme(){
  var c=document.documentElement.getAttribute('data-theme');
  var n=c==='light'?'dark':'light';
  if(n==='dark'){document.documentElement.removeAttribute('data-theme');localStorage.removeItem('theme');}
  else{document.documentElement.setAttribute('data-theme',n);localStorage.setItem('theme',n);}
  document.querySelectorAll('.theme-icon').forEach(function(el){el.textContent=n==='light'?'\u{1F319}':'\u2600\uFE0F';});
}
(function(){
  var isDark=document.documentElement.getAttribute('data-theme')!=='light';
  document.querySelectorAll('.theme-icon').forEach(function(el){el.textContent=isDark?'\u2600\uFE0F':'\u{1F319}';});
})();
</script>
"""

# Shared CSS with design tokens matching report's styles.css
_COMMON_CSS = r"""
/* ---- Design tokens (dark default) ---- */
:root {
  --bg:#0a0c10;--surface:#111520;--raised:#181e2e;--border:#1e2a3a;
  --text:#dce4f0;--muted:#8090a8;--subtle:#2e3a4e;
  --accent:#f59e0b;--accent-dim:rgba(245,158,11,0.12);
  --green:#34d399;--red:#f87171;--blue:#60a5fa;
  --radius:10px;--radius-sm:6px;
}
[data-theme="light"] {
  --bg:#f0f2f5;--surface:#ffffff;--raised:#f5f7fa;--border:#dde1e9;
  --text:#111827;--muted:#6b7280;--subtle:#c8cdd8;
  --accent:#d97706;--accent-dim:rgba(217,119,6,0.10);
  --green:#059669;--red:#dc2626;--blue:#2563eb;
}

/* ---- Reset & base ---- */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
     background:var(--bg);color:var(--text);line-height:1.5;min-height:100vh}

/* ---- App header ---- */
.app-header{
  width:100%;background:var(--surface);border-bottom:1px solid var(--border);
  padding:0.75rem 2rem;display:flex;align-items:center;gap:1.5rem;
}
.brand{font-size:1.15rem;font-weight:700;letter-spacing:-0.03em;
       text-decoration:none;color:var(--text);flex-shrink:0}
.brand-accent{color:var(--accent)}
.app-nav{display:flex;align-items:center;gap:0.25rem;margin-left:1rem}
.nav-link{font-size:0.82rem;font-weight:500;color:var(--muted);text-decoration:none;
          padding:0.35rem 0.7rem;border-radius:var(--radius-sm);transition:all 0.12s}
.nav-link:hover{color:var(--text);background:var(--raised)}
.nav-link.active{color:var(--accent);background:var(--accent-dim)}
.header-right{margin-left:auto;display:flex;align-items:center;gap:0.75rem;font-size:0.82rem}
.header-user{color:var(--muted)}
.header-link{color:var(--accent);text-decoration:none;font-weight:600}
.header-link:hover{opacity:0.85}

/* ---- Theme toggle ---- */
.theme-toggle{background:none;border:1px solid var(--border);border-radius:20px;
              padding:0.15rem 0.5rem;cursor:pointer;font-size:0.85rem;line-height:1;
              transition:border-color 0.12s}
.theme-toggle:hover{border-color:var(--accent)}

/* ---- App main ---- */
.app-main{max-width:720px;width:100%;margin:0 auto;padding:2rem 1rem;
          display:flex;flex-direction:column;gap:1.5rem}

/* ---- Cards ---- */
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:1.5rem}
.card h2{font-size:1rem;font-weight:600;margin-bottom:1rem}

/* ---- Form elements ---- */
label{display:block;font-size:0.72rem;font-weight:600;color:var(--muted);
      text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.3rem}
input[type=text],input[type=email],input[type=password],select,textarea{
  width:100%;padding:0.55rem 0.75rem;border:1px solid var(--border);border-radius:var(--radius-sm);
  background:var(--bg);color:var(--text);font-size:0.9rem;font-family:inherit;margin-bottom:1rem;
}
input:focus,select:focus,textarea:focus{outline:none;border-color:var(--accent)}

/* ---- Buttons ---- */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:0.4rem;
     padding:0.55rem 1.25rem;border-radius:var(--radius-sm);font-size:0.88rem;font-weight:600;
     cursor:pointer;border:none;transition:all 0.12s;font-family:inherit;text-decoration:none}
.btn-primary{background:var(--accent);color:#000}
.btn-primary:hover{opacity:0.88}
.btn-primary:disabled{opacity:0.35;cursor:default}
.btn-secondary{background:transparent;color:var(--muted);border:1px solid var(--border)}
.btn-secondary:hover{background:var(--raised);color:var(--text)}
.btn-sm{padding:0.35rem 0.8rem;font-size:0.8rem}
.btn-group{display:flex;gap:0.6rem;margin-top:1.25rem;flex-wrap:wrap}

/* ---- Drop zone ---- */
.drop-zone{border:2px dashed var(--border);border-radius:var(--radius);padding:2.5rem 1.5rem;
           text-align:center;cursor:pointer;transition:all 0.15s;position:relative}
.drop-zone:hover,.drop-zone.dragover{border-color:var(--accent);background:var(--accent-dim)}
.drop-zone .icon{font-size:2.2rem;margin-bottom:0.5rem}
.drop-zone .lbl{font-size:0.9rem;color:var(--muted)}
.drop-zone .lbl strong{color:var(--accent)}
.drop-zone .hint{font-size:0.72rem;color:var(--muted);margin-top:0.3rem}
.drop-zone input[type=file]{position:absolute;inset:0;opacity:0;cursor:pointer}

/* ---- Data table ---- */
.data-table{width:100%;border-collapse:collapse;font-size:0.85rem}
.data-table th,.data-table td{padding:0.5rem 0.75rem;text-align:left;border-bottom:1px solid var(--border)}
.data-table th{font-size:0.67rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--muted);font-weight:600}
.data-table select{background:var(--raised);color:var(--text);border:1px solid var(--border);
                   border-radius:4px;padding:0.2rem 0.4rem;font-size:0.82rem;cursor:pointer;width:auto;margin-bottom:0}

/* ---- Status bar ---- */
.status-bar{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);
            padding:1rem 1.25rem;display:flex;align-items:center;gap:1.25rem;flex-wrap:wrap;font-size:0.85rem}
.status-item{display:flex;align-items:center;gap:0.35rem}
.status-item .num{font-weight:700}
.status-item .lbl{color:var(--muted)}

/* ---- Feedback states ---- */
.error-msg{color:var(--red);font-size:0.82rem;margin-top:0.6rem}
.success-box{background:rgba(52,211,153,0.08);border:1px solid rgba(52,211,153,0.25);
             border-radius:var(--radius-sm);padding:1rem;text-align:center}
.success-box .big{font-size:1.1rem;font-weight:700;color:var(--green);margin-bottom:0.4rem}
.success-box .sub{font-size:0.82rem;color:var(--muted)}

/* ---- Badges ---- */
.badge{font-size:0.68rem;font-weight:700;padding:0.15rem 0.45rem;border-radius:8px;display:inline-block}
.badge-accent{background:var(--accent-dim);color:var(--accent)}
.badge-green{background:rgba(52,211,153,0.12);color:var(--green)}
.badge-red{background:rgba(248,113,113,0.15);color:var(--red)}
.badge-muted{background:var(--raised);color:var(--muted)}

/* ---- Spinner ---- */
@keyframes spin{to{transform:rotate(360deg)}}
.spin{display:inline-block;width:0.85em;height:0.85em;border:2px solid rgba(0,0,0,0.3);
      border-top-color:#000;border-radius:50%;animation:spin 0.6s linear infinite}

/* ---- File list ---- */
.file-list{margin-top:0.75rem;display:flex;flex-direction:column;gap:0.35rem}
.file-item{display:flex;align-items:center;gap:0.5rem;padding:0.4rem 0.75rem;
           background:var(--raised);border-radius:var(--radius-sm);font-size:0.85rem}
.file-item .name{flex:1;font-weight:500}
.file-item .size{color:var(--muted);font-size:0.8rem}
.file-item .remove{cursor:pointer;color:var(--red);font-weight:700;padding:0 0.25rem;
                   border:none;background:none;font-size:1rem}

/* ---- Progress ---- */
.progress{display:none;margin-top:1rem}
.progress.active{display:block}
.progress-bar{height:4px;background:var(--border);border-radius:4px;overflow:hidden}
.progress-bar .fill{height:100%;background:var(--accent);transition:width 0.3s ease;border-radius:4px}
.progress-label{font-size:0.8rem;color:var(--muted);margin-top:0.35rem}

/* ---- Results ---- */
.results{margin-top:1rem;display:none}
.results.active{display:block}
.result-item{display:flex;align-items:center;gap:0.75rem;padding:0.75rem;
             border-bottom:1px solid var(--border);font-size:0.85rem}
.result-item:last-child{border-bottom:none}
.result-item .status{font-size:1.2rem}
.result-item .info{flex:1}
.result-item .info .filename{font-weight:600}
.result-item .info .detail{color:var(--muted);font-size:0.8rem}
.result-item .info .error{color:var(--red);font-size:0.8rem}
.actions{display:none}
.actions.active{display:flex;gap:0.75rem;flex-wrap:wrap;margin-top:1rem}

/* ---- Guest banner ---- */
.guest-banner{background:var(--accent-dim);border:1px solid var(--accent);
              border-radius:var(--radius);padding:1rem 1.25rem;font-size:0.9rem}
.demo-banner{background:#2a1f0a;border:1px solid #d4a017;
             border-radius:var(--radius);padding:1rem 1.25rem;font-size:0.9rem;margin-bottom:1rem}

/* ---- Centered auth layout ---- */
.auth-layout{display:flex;align-items:center;justify-content:center;min-height:100vh;padding:1rem}
.auth-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);
           padding:2rem;width:100%;max-width:380px;position:relative}
.auth-card .logo{text-align:center;margin-bottom:1.5rem;font-size:1.5rem;font-weight:700;letter-spacing:-0.03em}
.auth-theme-toggle{position:absolute;top:1rem;right:1rem}
.auth-error{color:var(--red);font-size:0.82rem;margin-bottom:1rem;text-align:center}
.auth-sub{font-size:0.82rem;color:var(--muted);text-align:center;margin-bottom:1.5rem}

/* ---- Import wizard extras ---- */
.steps{display:flex;align-items:center;gap:0;margin-bottom:0.5rem}
.step{display:flex;align-items:center;gap:0.5rem;font-size:0.78rem;font-weight:600;
      color:var(--muted);padding:0.4rem 0.75rem;border-radius:20px}
.step.active{color:var(--accent)}
.step.done{color:var(--green)}
.step-num{width:20px;height:20px;border-radius:50%;border:2px solid currentColor;
          display:flex;align-items:center;justify-content:center;font-size:0.7rem;flex-shrink:0}
.step-sep{flex:1;height:1px;background:var(--border);margin:0 0.25rem;max-width:40px}
.ac-toggles{display:flex;gap:0.5rem;flex-wrap:wrap;margin-bottom:1.25rem}
.ac-btn{padding:0.3rem 0.85rem;border-radius:12px;font-size:0.75rem;font-weight:700;
        cursor:pointer;border:1px solid var(--border);background:transparent;
        color:var(--muted);font-family:inherit;transition:all 0.12s}
.ac-btn.active{background:var(--accent-dim);color:var(--accent);border-color:var(--accent)}
.preview-wrap{overflow-x:auto;margin-bottom:1.25rem}
.preview-table{border-collapse:collapse;font-size:0.75rem;width:100%}
.preview-table th,.preview-table td{padding:0.3rem 0.55rem;text-align:left;border-bottom:1px solid var(--border);white-space:nowrap}
.preview-table thead th{font-weight:600;color:var(--accent);font-size:0.68rem;text-transform:uppercase;letter-spacing:0.05em}
.map-table{width:100%;border-collapse:collapse;font-size:0.83rem}
.map-table td{padding:0.45rem 0.5rem;border-bottom:1px solid var(--border);vertical-align:middle}
.map-table td:first-child{width:38%;font-weight:500}
.map-table td:nth-child(2){width:10%;text-align:center}
.map-table select{background:var(--raised);border:1px solid var(--border);border-radius:var(--radius-sm);
                  color:var(--text);font-family:inherit;font-size:0.8rem;padding:0.3rem 0.5rem;width:100%;margin-bottom:0}
.map-table select:focus{outline:none;border-color:var(--accent)}
.req-badge{font-size:0.62rem;font-weight:700;padding:0.1rem 0.4rem;border-radius:8px;
           background:rgba(248,113,113,0.15);color:var(--red)}
.opt-badge{font-size:0.62rem;font-weight:700;padding:0.1rem 0.4rem;border-radius:8px;
           background:var(--raised);color:var(--muted)}
.summary-list{display:flex;flex-direction:column;gap:0.4rem;font-size:0.83rem}
.summary-row{display:flex;gap:0.75rem}
.summary-lbl{color:var(--muted);width:140px;flex-shrink:0;font-size:0.75rem;font-weight:600;
             text-transform:uppercase;letter-spacing:0.05em}
.summary-val{color:var(--text)}
.success-links{display:flex;gap:0.6rem;justify-content:center;margin-top:1rem;flex-wrap:wrap}
.chosen-file{margin-top:0.75rem;font-size:0.83rem;font-weight:500;color:var(--text)}

/* ---- Validation Issues ---- */
.validation-issues-list{max-height:320px;overflow-y:auto;border:1px solid var(--border,#e0e0e0);
  border-radius:6px;font-size:0.78rem}
.v-issue{display:flex;align-items:center;gap:0.5rem;padding:0.35rem 0.6rem;
  border-bottom:1px solid var(--border,#f0f0f0);flex-wrap:wrap}
.v-issue:last-child{border-bottom:none}
.v-issue.sev-error{background:rgba(248,113,113,0.06)}
.v-issue.sev-warning{background:rgba(245,158,11,0.06)}
.v-issue.sev-info{background:transparent}
.v-sev{font-size:0.6rem;font-weight:700;padding:0.1rem 0.35rem;border-radius:6px;flex-shrink:0}
.sev-error .v-sev{background:rgba(248,113,113,0.2);color:var(--red)}
.sev-warning .v-sev{background:rgba(245,158,11,0.2);color:#b45309}
.sev-info .v-sev{background:var(--raised,#f0f0f0);color:var(--muted)}
.v-row{color:var(--muted);font-size:0.72rem;flex-shrink:0;min-width:45px}
.v-col{color:var(--text);font-weight:600;flex-shrink:0}
.v-msg{color:var(--text);flex:1}
.v-val{font-family:monospace;font-size:0.72rem;color:var(--muted);
  background:var(--raised,#f5f5f5);padding:0.1rem 0.3rem;border-radius:3px}
.v-sug{font-size:0.72rem;color:var(--accent,#d97706);font-style:italic}

/* ---- Global drop overlay ---- */
.drop-overlay{position:fixed;inset:0;z-index:9999;background:rgba(10,12,16,0.88);
  display:none;align-items:center;justify-content:center;flex-direction:column;
  backdrop-filter:blur(4px);transition:opacity 0.15s}
[data-theme="light"] .drop-overlay{background:rgba(0,0,0,0.55)}
[data-theme="light"] .import-preview{background:rgba(0,0,0,0.55)}
.drop-overlay.visible{display:flex}
.drop-overlay-inner{border:2px dashed var(--accent);border-radius:var(--radius);
  padding:3rem 2.5rem;text-align:center;max-width:680px;width:90%;
  background:var(--surface);position:relative}
.drop-overlay-icon{font-size:3rem;margin-bottom:0.75rem}
.drop-overlay-title{font-size:1.15rem;font-weight:700;margin-bottom:0.3rem}
.drop-overlay-hint{font-size:0.82rem;color:var(--muted)}
.drop-overlay-close{position:absolute;top:0.75rem;right:1rem;background:none;border:none;
  font-size:1.3rem;color:var(--muted);cursor:pointer}
.drop-overlay-close:hover{color:var(--text)}

/* ---- Import preview modal ---- */
.import-preview{position:fixed;inset:0;z-index:10000;background:rgba(10,12,16,0.92);
  display:none;align-items:flex-start;justify-content:center;overflow-y:auto;
  padding:2rem 1rem;backdrop-filter:blur(4px)}
.import-preview.visible{display:flex}
.import-preview-card{background:var(--surface);border:1px solid var(--border);
  border-radius:var(--radius);padding:1.75rem;width:100%;max-width:780px;margin-top:2vh}
.import-preview-card h2{font-size:1.05rem;font-weight:700;margin-bottom:1rem}
.import-files-list{display:flex;flex-direction:column;gap:0.35rem;margin-bottom:1.25rem}
.import-file-tag{display:inline-flex;align-items:center;gap:0.4rem;padding:0.3rem 0.7rem;
  background:var(--raised);border-radius:var(--radius-sm);font-size:0.82rem}
.import-file-tag .size{color:var(--muted);font-size:0.75rem}
.import-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:0.6rem;margin-bottom:1.25rem}
.import-stat{background:var(--raised);border-radius:var(--radius-sm);padding:0.6rem 0.8rem}
.import-stat .val{font-size:1.1rem;font-weight:700}
.import-stat .lbl{font-size:0.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.05em}
.import-preview-table{width:100%;border-collapse:collapse;font-size:0.78rem;margin-bottom:1rem}
.import-preview-table th,.import-preview-table td{padding:0.35rem 0.55rem;text-align:left;
  border-bottom:1px solid var(--border);white-space:nowrap;max-width:180px;overflow:hidden;text-overflow:ellipsis}
.import-preview-table thead th{font-weight:600;color:var(--accent);font-size:0.68rem;
  text-transform:uppercase;letter-spacing:0.05em}
.import-issues{margin-bottom:1rem}
.import-issue{display:flex;align-items:center;gap:0.5rem;padding:0.35rem 0.6rem;
  border-radius:var(--radius-sm);margin-bottom:0.25rem;font-size:0.8rem}
.import-issue.error{background:rgba(248,113,113,0.08);color:var(--red)}
.import-issue.warning{background:rgba(245,158,11,0.08);color:#b45309}
.import-issue-icon{font-size:0.9rem;flex-shrink:0}
.import-actions{display:flex;gap:0.6rem;margin-top:1.25rem;flex-wrap:wrap}
.import-progress{margin-top:1rem;display:none}
.import-progress.active{display:block}

/* ---- Responsive ---- */
@media (max-width:768px) {
  .app-header{padding:0.75rem 1rem;gap:0.75rem;flex-wrap:wrap}
  .app-nav{margin-left:0;gap:0.15rem}
  .nav-link{padding:0.3rem 0.5rem;font-size:0.78rem}
  .app-main{padding:1.25rem 0.75rem}
  .card{padding:1.25rem}
  .import-preview-card{padding:1.25rem}
}

/* ---- Toast notifications ---- */
.toast-container {
  position: fixed;
  top: 1rem;
  right: 1rem;
  z-index: 10000;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  pointer-events: none;
}

.toast {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.75rem 1rem;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  opacity: 0;
  transform: translateX(100%);
  transition: all 0.3s ease;
  max-width: 400px;
  pointer-events: auto;
}

.toast-show {
  opacity: 1;
  transform: translateX(0);
}

.toast-icon {
  font-size: 1.25rem;
  font-weight: bold;
  flex-shrink: 0;
}

.toast-message {
  font-size: 0.875rem;
  line-height: 1.4;
}

.toast-success {
  border-left: 3px solid var(--green);
}

.toast-success .toast-icon {
  color: var(--green);
}

.toast-error {
  border-left: 3px solid var(--red);
}

.toast-error .toast-icon {
  color: var(--red);
}

.toast-info {
  border-left: 3px solid var(--blue);
}

.toast-info .toast-icon {
  color: var(--blue);
}

.toast-warning {
  border-left: 3px solid var(--accent);
}

.toast-warning .toast-icon {
  color: var(--accent);
}

/* ---- Confetti canvas ---- */
.confetti-canvas {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 9999;
}

/* ---- Empty states ---- */
.empty-state-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 3rem 2rem;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1.25rem;
  margin: 2rem auto;
  max-width: 500px;
}

.empty-state-icon {
  font-size: 3rem;
  opacity: 0.7;
}

.empty-state-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text);
  margin: 0;
}

.empty-state-message {
  font-size: 0.9rem;
  color: var(--muted);
  line-height: 1.6;
  margin: 0;
  max-width: 400px;
}

.empty-state-actions {
  display: flex;
  gap: 0.75rem;
  margin-top: 0.5rem;
  flex-wrap: wrap;
  justify-content: center;
}

.btn-primary, .btn-secondary {
  padding: 0.625rem 1.25rem;
  border-radius: var(--radius-sm);
  font-size: 0.875rem;
  font-weight: 600;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  transition: all 0.2s;
  cursor: pointer;
  border: none;
  font-family: inherit;
}

.btn-primary {
  background: var(--accent);
  color: #111827;
}

.btn-primary:hover {
  opacity: 0.9;
  transform: translateY(-1px);
}

.btn-secondary {
  background: var(--raised);
  color: var(--text);
  border: 1px solid var(--border);
}

.btn-secondary:hover {
  background: var(--subtle);
}

.btn-text {
  background: none;
  border: none;
  color: var(--muted);
  font-size: 0.875rem;
  padding: 0.5rem;
  cursor: pointer;
  transition: color 0.2s;
}

.btn-text:hover {
  color: var(--text);
}

/* ---- Welcome wizard ---- */
.wizard-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(4px);
  z-index: 10001;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
}

.wizard-modal {
  background: var(--surface);
  border-radius: var(--radius);
  max-width: 600px;
  width: 100%;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  animation: wizardSlideIn 0.3s ease;
}

@keyframes wizardSlideIn {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.wizard-step {
  display: flex;
  flex-direction: column;
}

.wizard-progress {
  height: 4px;
  background: var(--subtle);
  border-radius: var(--radius) var(--radius) 0 0;
  overflow: hidden;
}

.wizard-progress-bar {
  height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--blue));
  transition: width 0.3s ease;
}

.wizard-content {
  padding: 3rem 2.5rem;
  text-align: center;
}

.wizard-icon {
  font-size: 4rem;
  margin-bottom: 1.5rem;
}

.wizard-title {
  font-size: 1.75rem;
  font-weight: 700;
  margin-bottom: 1rem;
  color: var(--text);
}

.wizard-description {
  font-size: 1rem;
  color: var(--muted);
  line-height: 1.6;
  margin-bottom: 1.5rem;
}

.wizard-features {
  list-style: none;
  text-align: left;
  display: inline-block;
  margin: 1.5rem 0;
}

.wizard-features li {
  padding: 0.5rem 0;
  font-size: 0.95rem;
  color: var(--text);
}

.wizard-info-box {
  background: var(--raised);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 1.25rem;
  margin: 1.5rem 0;
  text-align: left;
}

.wizard-info-box strong {
  display: block;
  margin-bottom: 0.75rem;
  color: var(--text);
}

.wizard-info-box ul {
  list-style: none;
  margin: 0;
}

.wizard-info-box li {
  padding: 0.25rem 0;
  color: var(--muted);
  font-size: 0.9rem;
}

.wizard-spinner {
  width: 48px;
  height: 48px;
  border: 4px solid var(--subtle);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 2rem auto;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.wizard-highlights {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1rem;
  margin: 2rem 0;
}

.wizard-highlight-card {
  background: var(--raised);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 1.5rem;
}

.wizard-highlight-value {
  font-size: 2rem;
  font-weight: 700;
  color: var(--accent);
  margin-bottom: 0.5rem;
}

.wizard-highlight-label {
  font-size: 0.875rem;
  color: var(--muted);
}

.wizard-actions {
  padding: 0 2.5rem 2.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.wizard-btn-large {
  padding: 0.875rem 1.5rem;
  font-size: 1rem;
}

@media (max-width: 768px) {
  .toast-container {
    top: 0.5rem;
    right: 0.5rem;
    left: 0.5rem;
  }
  .toast {
    max-width: 100%;
  }
  .empty-state-card {
    padding: 2rem 1.5rem;
  }
  .empty-state-actions {
    flex-direction: column;
    width: 100%;
  }
  .btn-primary, .btn-secondary {
    width: 100%;
    justify-content: center;
  }
  .wizard-modal {
    margin: 0;
    max-height: 100vh;
    overflow-y: auto;
  }
  .wizard-content {
    padding: 2rem 1.5rem;
  }
  .wizard-icon {
    font-size: 3rem;
  }
  .wizard-title {
    font-size: 1.5rem;
  }
  .wizard-actions {
    padding: 0 1.5rem 1.5rem;
  }
  .wizard-highlights {
    grid-template-columns: 1fr;
  }
}
"""


def _head_html(title: str, extra_css: str = "", description: str = "",
               canonical_path: str = "", robots: str = "") -> str:
    """Shared <head> block for all non-report pages."""
    meta = ""
    if description:
        meta += f'<meta name="description" content="{description}">\n'
    if robots:
        meta += f'<meta name="robots" content="{robots}">\n'
    if canonical_path:
        canonical_url = APP_BASE_URL.rstrip("/") + canonical_path
        meta += f'<link rel="canonical" href="{canonical_url}">\n'
        meta += f'<meta property="og:title" content="{title}">\n'
        meta += f'<meta property="og:description" content="{description}">\n'
        meta += '<meta property="og:type" content="website">\n'
        meta += f'<meta property="og:url" content="{canonical_url}">\n'
        meta += f'<meta property="og:image" content="{APP_BASE_URL.rstrip("/")}/static/og-card.png">\n'
        meta += '<meta property="og:site_name" content="WealthEagle">\n'
        meta += '<meta name="twitter:card" content="summary_large_image">\n'
        meta += f'<meta name="twitter:title" content="{title}">\n'
        meta += f'<meta name="twitter:description" content="{description}">\n'
        meta += f'<meta name="twitter:image" content="{APP_BASE_URL.rstrip("/")}/static/og-card.png">\n'
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'{meta}'
        f'{_FOUC_SCRIPT}\n'
        f'<title>{title}</title>\n'
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">\n'
        f'<style>{_COMMON_CSS}{extra_css}</style>\n'
        '</head>\n'
    )


def _header_html(username: str = "", role: str = "guest", active_page: str = "") -> str:
    """Shared navigation header."""
    def _link(href: str, label: str, page: str) -> str:
        cls = "nav-link active" if page == active_page else "nav-link"
        return f'<a class="{cls}" href="{href}">{label}</a>'

    nav = _link("/", "Home", "home")
    nav += _link("/report", "Report", "report")
    if role == "guest":
        nav += _link("/pricing", "Pricing", "pricing")
    if role in ("premium", "admin"):
        nav += _link("/import", "Import Wizard", "import")
        nav += _link("/settings", "Settings", "settings")
        nav += _link("/account", "Account", "account")
    if role == "admin":
        nav += _link("/admin", "Admin", "admin")

    right = '<button class="theme-toggle" onclick="toggleTheme()"><span class="theme-icon"></span></button>'
    if username:
        right += f' <span class="header-user">{username}</span>'
        right += ' <a class="header-link" href="/logout">Log out</a>'
    else:
        right += ' <a class="header-link" href="/login">Log in</a>'

    return (
        '<header class="app-header">\n'
        f'  <a class="brand" href="/">WealthEagle<span class="brand-accent">.</span></a>\n'
        f'  <nav class="app-nav">{nav}</nav>\n'
        f'  <div class="header-right">{right}</div>\n'
        '</header>\n'
    )


# ---------------------------------------------------------------------------
# Global drag-and-drop CSV import overlay (premium/admin pages)
# ---------------------------------------------------------------------------

def _global_drop_import_html() -> str:
    """Full-page drag-and-drop overlay + preview modal for CSV import.

    Included on premium/admin pages. Handles:
    - Drag-over anywhere on the page shows the drop overlay
    - Dropped CSVs are parsed client-side instantly
    - Preview shows transaction count, tickers, buy/sell breakdown, date range
    - Issues highlighted (duplicates, unrecognized formats, date gaps)
    - Confirm triggers server import; Cancel discards
    - Multiple files supported
    """
    return r"""
<!-- Global drop overlay -->
<div class="drop-overlay" id="globalDropOverlay">
  <div class="drop-overlay-inner">
    <button class="drop-overlay-close" id="dropOverlayClose">&times;</button>
    <div class="drop-overlay-icon">&#128229;</div>
    <div class="drop-overlay-title">Drop CSV files to import</div>
    <div class="drop-overlay-hint">Drop one or more CSV files anywhere on the page</div>
  </div>
</div>

<!-- Import preview modal -->
<div class="import-preview" id="importPreviewModal">
  <div class="import-preview-card">
    <h2>Import Preview</h2>
    <div class="import-files-list" id="importFilesList"></div>
    <div class="import-stats" id="importStats"></div>
    <div class="import-issues" id="importIssues"></div>
    <div style="overflow-x:auto">
      <table class="import-preview-table" id="importPreviewTable"></table>
    </div>
    <div class="import-progress" id="importProgress">
      <div class="progress-bar"><div class="fill" id="importProgressFill" style="width:0%"></div></div>
      <div class="progress-label" id="importProgressLabel">Importing...</div>
    </div>
    <div id="importResultBox" style="display:none"></div>
    <div class="import-actions" id="importActions">
      <button class="btn btn-secondary" id="importCancelBtn">Cancel</button>
      <button class="btn btn-primary" id="importConfirmBtn">Confirm Import</button>
      <input type="file" id="importFilePicker" accept=".csv" multiple style="display:none">
      <button class="btn btn-secondary btn-sm" id="importAddMoreBtn" style="margin-left:auto">+ Add files</button>
    </div>
  </div>
</div>

<script>
(function() {
  var overlay = document.getElementById('globalDropOverlay');
  var modal = document.getElementById('importPreviewModal');
  var filesList = document.getElementById('importFilesList');
  var statsEl = document.getElementById('importStats');
  var issuesEl = document.getElementById('importIssues');
  var tableEl = document.getElementById('importPreviewTable');
  var confirmBtn = document.getElementById('importConfirmBtn');
  var cancelBtn = document.getElementById('importCancelBtn');
  var closeBtn = document.getElementById('dropOverlayClose');
  var progressEl = document.getElementById('importProgress');
  var progressFill = document.getElementById('importProgressFill');
  var progressLabel = document.getElementById('importProgressLabel');
  var resultBox = document.getElementById('importResultBox');
  var actionsEl = document.getElementById('importActions');
  var filePicker = document.getElementById('importFilePicker');
  var addMoreBtn = document.getElementById('importAddMoreBtn');

  var dragCounter = 0;
  var pendingFiles = [];
  var parsedData = [];

  // --- Drag overlay logic ---
  document.addEventListener('dragenter', function(e) {
    if (!_hasCsvFiles(e)) return;
    e.preventDefault();
    dragCounter++;
    if (dragCounter === 1) overlay.classList.add('visible');
  });
  document.addEventListener('dragleave', function(e) {
    e.preventDefault();
    dragCounter--;
    if (dragCounter <= 0) { dragCounter = 0; overlay.classList.remove('visible'); }
  });
  document.addEventListener('dragover', function(e) {
    if (!_hasCsvFiles(e)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  });
  document.addEventListener('drop', function(e) {
    e.preventDefault();
    dragCounter = 0;
    overlay.classList.remove('visible');
    var files = Array.from(e.dataTransfer.files).filter(function(f) {
      return f.name.toLowerCase().endsWith('.csv');
    });
    if (files.length > 0) handleFiles(files);
  });
  closeBtn.addEventListener('click', function() {
    dragCounter = 0;
    overlay.classList.remove('visible');
  });

  function _hasCsvFiles(e) {
    if (e.dataTransfer && e.dataTransfer.types) {
      return e.dataTransfer.types.indexOf('Files') !== -1;
    }
    return false;
  }

  // --- File picker fallback ---
  addMoreBtn.addEventListener('click', function() { filePicker.click(); });
  filePicker.addEventListener('change', function() {
    var files = Array.from(filePicker.files).filter(function(f) {
      return f.name.toLowerCase().endsWith('.csv');
    });
    if (files.length > 0) handleFiles(files);
    filePicker.value = '';
  });

  // --- Handle dropped/picked files ---
  function handleFiles(files) {
    files.forEach(function(f) {
      if (!pendingFiles.some(function(pf) { return pf.name === f.name && pf.size === f.size; })) {
        pendingFiles.push(f);
      }
    });
    parseAllFiles();
  }

  function parseAllFiles() {
    parsedData = [];
    var remaining = pendingFiles.length;
    pendingFiles.forEach(function(file, idx) {
      var reader = new FileReader();
      reader.onload = function(e) {
        var text = e.target.result;
        parsedData[idx] = parseCSV(text, file.name);
        remaining--;
        if (remaining === 0) showPreview();
      };
      reader.readAsText(file);
    });
  }

  // --- CSV parser ---
  function parseCSV(text, filename) {
    var lines = text.split(/\r?\n/);
    var sep = ',';
    if (lines[0] && lines[0].indexOf(';') > lines[0].indexOf(',')) sep = ';';
    var headers = splitCSVLine(lines[0], sep);
    var rows = [];
    for (var i = 1; i < lines.length; i++) {
      if (!lines[i].trim()) continue;
      rows.push(splitCSVLine(lines[i], sep));
    }
    var issues = detectIssues(headers, rows, filename);
    var stats = computeStats(headers, rows);
    return { filename: filename, headers: headers, rows: rows, issues: issues, stats: stats };
  }

  function splitCSVLine(line, sep) {
    var result = [], current = '', inQuote = false;
    for (var i = 0; i < line.length; i++) {
      var ch = line[i];
      if (ch === '"') { inQuote = !inQuote; continue; }
      if (ch === sep && !inQuote) { result.push(current.trim()); current = ''; continue; }
      current += ch;
    }
    result.push(current.trim());
    return result;
  }

  // --- Stats computation ---
  function computeStats(headers, rows) {
    var stats = { total: rows.length, tickers: {}, types: {}, dateMin: null, dateMax: null };
    var tickerIdx = findColIndex(headers, ['ticker','symbol','financialinstrument']);
    var typeIdx = findColIndex(headers, ['type','transactiontypename','transaction type']);
    var dateIdx = findColIndex(headers, ['date','started date','started_date','datevalue','settlementdate']);
    rows.forEach(function(row) {
      if (tickerIdx >= 0 && row[tickerIdx]) {
        var t = row[tickerIdx].replace(/"/g,'').trim();
        if (t) stats.tickers[t] = (stats.tickers[t] || 0) + 1;
      }
      if (typeIdx >= 0 && row[typeIdx]) {
        var ty = row[typeIdx].replace(/"/g,'').trim().toLowerCase();
        stats.types[ty] = (stats.types[ty] || 0) + 1;
      }
      if (dateIdx >= 0 && row[dateIdx]) {
        var d = row[dateIdx].replace(/"/g,'').trim().slice(0, 10);
        if (d && d.match(/\d{4}[-\/]\d{2}[-\/]\d{2}/)) {
          if (!stats.dateMin || d < stats.dateMin) stats.dateMin = d;
          if (!stats.dateMax || d > stats.dateMax) stats.dateMax = d;
        }
      }
    });
    return stats;
  }

  function findColIndex(headers, aliases) {
    var lower = headers.map(function(h) { return h.toLowerCase().trim(); });
    for (var i = 0; i < aliases.length; i++) {
      var idx = lower.indexOf(aliases[i]);
      if (idx >= 0) return idx;
    }
    return -1;
  }

  // --- Issue detection ---
  function detectIssues(headers, rows, filename) {
    var issues = [];
    var knownHeaders = ['date','started date','started_date','type','transactiontypename',
      'transaction type','ticker','symbol','financialinstrument','quantity','volume',
      'volumevalue','price per share','price','pricevalue','total amount','amount','value',
      'total_amount','currency','ccy','fx rate','fxrate','fx_rate','exchange rate',
      'quantity of shares','qty','price_per_share','description','margin','isin',
      'settlementdate','datevalue'];
    var lowerHeaders = headers.map(function(h) { return h.toLowerCase().trim(); });

    // Check for unrecognized format
    var recognized = lowerHeaders.filter(function(h) { return knownHeaders.indexOf(h) >= 0; });
    if (recognized.length === 0 && headers.length > 0) {
      issues.push({ severity: 'error', msg: 'Unrecognized CSV format — no known columns detected in ' + filename });
    } else if (recognized.length < 2) {
      issues.push({ severity: 'warning', msg: 'Only ' + recognized.length + ' recognized column(s) in ' + filename + '. May need manual mapping.' });
    }

    // Date column check
    var dateIdx = findColIndex(headers, ['date','started date','started_date','datevalue','settlementdate']);
    if (dateIdx < 0) {
      issues.push({ severity: 'error', msg: 'No date column found in ' + filename });
    }

    // Duplicate detection (same row content)
    var seen = {};
    var dupeCount = 0;
    rows.forEach(function(row) {
      var key = row.join('|');
      if (seen[key]) dupeCount++;
      else seen[key] = true;
    });
    if (dupeCount > 0) {
      issues.push({ severity: 'warning', msg: dupeCount + ' potential duplicate row(s) detected in ' + filename });
    }

    // Date gaps (more than 90 days between consecutive dates)
    if (dateIdx >= 0) {
      var dates = [];
      rows.forEach(function(row) {
        if (row[dateIdx]) {
          var d = row[dateIdx].replace(/"/g,'').trim().slice(0, 10);
          if (d.match(/\d{4}[-\/]\d{2}[-\/]\d{2}/)) dates.push(d);
        }
      });
      dates.sort();
      for (var i = 1; i < dates.length; i++) {
        var prev = new Date(dates[i-1]);
        var curr = new Date(dates[i]);
        var gap = (curr - prev) / (1000*60*60*24);
        if (gap > 90) {
          issues.push({ severity: 'warning', msg: 'Date gap of ' + Math.round(gap) + ' days between ' + dates[i-1] + ' and ' + dates[i] + ' in ' + filename });
          break;
        }
      }
    }

    return issues;
  }

  // --- Show preview modal ---
  function showPreview() {
    resultBox.style.display = 'none';
    progressEl.classList.remove('active');
    confirmBtn.disabled = false;
    actionsEl.style.display = '';

    // File list
    filesList.innerHTML = pendingFiles.map(function(f, i) {
      var sz = f.size < 1024 ? f.size + ' B' : f.size < 1048576 ? (f.size/1024).toFixed(1) + ' KB' : (f.size/1048576).toFixed(1) + ' MB';
      return '<div class="import-file-tag"><span>' + esc(f.name) + '</span><span class="size">(' + sz + ')</span>'
        + '<button style="background:none;border:none;color:var(--red);cursor:pointer;font-weight:700;padding:0 0.2rem" data-ridx="'+i+'">&times;</button></div>';
    }).join('');
    filesList.querySelectorAll('button[data-ridx]').forEach(function(btn) {
      btn.addEventListener('click', function() {
        pendingFiles.splice(+btn.dataset.ridx, 1);
        parsedData.splice(+btn.dataset.ridx, 1);
        if (pendingFiles.length === 0) { closeModal(); return; }
        showPreview();
      });
    });

    // Aggregate stats
    var totalRows = 0, allTickers = {}, allTypes = {}, dateMin = null, dateMax = null;
    var allIssues = [];
    var hasErrors = false;
    parsedData.forEach(function(pd) {
      totalRows += pd.stats.total;
      Object.keys(pd.stats.tickers).forEach(function(t) { allTickers[t] = (allTickers[t]||0) + pd.stats.tickers[t]; });
      Object.keys(pd.stats.types).forEach(function(t) { allTypes[t] = (allTypes[t]||0) + pd.stats.types[t]; });
      if (pd.stats.dateMin && (!dateMin || pd.stats.dateMin < dateMin)) dateMin = pd.stats.dateMin;
      if (pd.stats.dateMax && (!dateMax || pd.stats.dateMax > dateMax)) dateMax = pd.stats.dateMax;
      pd.issues.forEach(function(iss) {
        allIssues.push(iss);
        if (iss.severity === 'error') hasErrors = true;
      });
    });

    var tickerCount = Object.keys(allTickers).length;
    var buyCount = (allTypes['buy'] || 0) + (allTypes['market buy'] || 0) + (allTypes['limit buy'] || 0);
    var sellCount = (allTypes['sell'] || 0) + (allTypes['market sell'] || 0) + (allTypes['limit sell'] || 0);

    statsEl.innerHTML = '<div class="import-stat"><div class="val">' + totalRows + '</div><div class="lbl">Transactions</div></div>'
      + '<div class="import-stat"><div class="val">' + tickerCount + '</div><div class="lbl">Tickers</div></div>'
      + '<div class="import-stat"><div class="val">' + buyCount + ' / ' + sellCount + '</div><div class="lbl">Buys / Sells</div></div>'
      + (dateMin ? '<div class="import-stat"><div class="val">' + dateMin + ' — ' + dateMax + '</div><div class="lbl">Date Range</div></div>' : '');

    // Issues
    if (allIssues.length > 0) {
      issuesEl.innerHTML = allIssues.map(function(iss) {
        var cls = iss.severity === 'error' ? 'error' : 'warning';
        var icon = iss.severity === 'error' ? '&#9888;' : '&#9888;';
        return '<div class="import-issue ' + cls + '"><span class="import-issue-icon">' + icon + '</span>' + esc(iss.msg) + '</div>';
      }).join('');
    } else {
      issuesEl.innerHTML = '<div class="import-issue" style="background:rgba(52,211,153,0.08);color:var(--green)"><span class="import-issue-icon">&#10003;</span>No issues detected — ready to import</div>';
    }

    // Preview table (first file, first 8 rows)
    if (parsedData.length > 0 && parsedData[0].rows.length > 0) {
      var pd = parsedData[0];
      var html = '<thead><tr>' + pd.headers.map(function(h) { return '<th>' + esc(h) + '</th>'; }).join('') + '</tr></thead><tbody>';
      var showRows = pd.rows.slice(0, 8);
      showRows.forEach(function(row) {
        html += '<tr>' + row.map(function(c) { return '<td>' + esc(c) + '</td>'; }).join('') + '</tr>';
      });
      if (pd.rows.length > 8) {
        html += '<tr><td colspan="' + pd.headers.length + '" style="text-align:center;color:var(--muted);font-style:italic">... and ' + (pd.rows.length - 8) + ' more rows</td></tr>';
      }
      html += '</tbody>';
      tableEl.innerHTML = html;
    } else {
      tableEl.innerHTML = '';
    }

    if (hasErrors) {
      confirmBtn.disabled = true;
      confirmBtn.title = 'Fix errors before importing';
    }

    modal.classList.add('visible');
    document.body.style.overflow = 'hidden';
  }

  // --- Confirm import ---
  confirmBtn.addEventListener('click', async function() {
    confirmBtn.disabled = true;
    progressEl.classList.add('active');
    progressFill.style.width = '30%';
    progressLabel.textContent = 'Uploading ' + pendingFiles.length + ' file(s)...';

    var form = new FormData();
    pendingFiles.forEach(function(f) { form.append('files', f); });

    try {
      progressFill.style.width = '60%';
      progressLabel.textContent = 'Importing...';
      var resp = await fetch('/upload', { method: 'POST', body: form });
      var data = await resp.json();
      progressFill.style.width = '100%';
      if (data.error) {
        progressLabel.textContent = 'Error: ' + data.error;
        confirmBtn.disabled = false;
        return;
      }
      progressLabel.textContent = 'Done!';
      actionsEl.style.display = 'none';
      var rhtml = '<div class="success-box" style="margin-top:1rem"><div class="big">Import complete</div><div class="sub">';
      data.results.forEach(function(r) {
        if (r.error) {
          rhtml += '<div style="color:var(--red)">' + esc(r.filename) + ': ' + esc(r.error) + '</div>';
        } else {
          rhtml += '<div>' + esc(r.filename) + ': ' + r.new + ' new, ' + r.skipped + ' skipped</div>';
        }
      });
      rhtml += '</div><div class="success-links"><a class="btn btn-primary" href="/report">View Report</a>';
      rhtml += '<button class="btn btn-secondary" onclick="document.getElementById(\'importPreviewModal\').classList.remove(\'visible\');document.body.style.overflow=\'\';location.reload()">Close</button>';
      rhtml += '</div></div>';
      resultBox.innerHTML = rhtml;
      resultBox.style.display = '';
      pendingFiles = [];
      parsedData = [];
    } catch (e) {
      progressFill.style.width = '100%';
      progressLabel.textContent = 'Error: ' + e.message;
      confirmBtn.disabled = false;
    }
  });

  // --- Cancel ---
  cancelBtn.addEventListener('click', closeModal);
  modal.addEventListener('click', function(e) {
    if (e.target === modal) closeModal();
  });

  function closeModal() {
    modal.classList.remove('visible');
    document.body.style.overflow = '';
    pendingFiles = [];
    parsedData = [];
  }

  function esc(s) { var d = document.createElement('div'); d.textContent = String(s); return d.innerHTML; }
})();
</script>
"""


# ---------------------------------------------------------------------------
# Inline HTML: generic error page
# ---------------------------------------------------------------------------

def _error_html(message: str) -> str:
    return (
        _head_html("Error — WealthEagle",
                    "body{display:flex;align-items:center;justify-content:center;padding:1rem}")
        + f"""<body>
<div class="auth-card" style="max-width:440px;text-align:center">
  <button class="theme-toggle auth-theme-toggle" onclick="toggleTheme()"><span class="theme-icon"></span></button>
  <div style="font-size:2.5rem;margin-bottom:1rem">&#9888;</div>
  <h2 style="font-size:1.1rem;font-weight:600;margin-bottom:1.25rem">{message}</h2>
  <a class="btn btn-primary" href="/">Go home</a>
</div>
{_COMMON_JS}
</body>
</html>"""
    )


def _shared_expired_html() -> str:
    return (
        _head_html("Link Expired — WealthEagle",
                    "body{display:flex;align-items:center;justify-content:center;padding:1rem}")
        + f"""<body>
<div class="auth-card" style="max-width:440px;text-align:center">
  <button class="theme-toggle auth-theme-toggle" onclick="toggleTheme()"><span class="theme-icon"></span></button>
  <div style="font-size:2.5rem;margin-bottom:1rem">&#128279;</div>
  <h2 style="font-size:1.1rem;font-weight:600;margin-bottom:0.5rem">Share link expired or invalid</h2>
  <p style="color:var(--text-secondary);margin-bottom:1.25rem">This portfolio snapshot is no longer available.</p>
  <a class="btn btn-primary" href="/">Go home</a>
</div>
{_COMMON_JS}
</body>
</html>"""
    )




def _audit_log_html(username: str, role: str) -> str:
    extra_css = (
        "#filters{display:flex;gap:.75rem;margin-bottom:1rem;flex-wrap:wrap}"
        "#filters select,#filters input{margin-bottom:0}"
        ".ev-ok{color:var(--green)}.ev-fail{color:var(--red)}"
        ".audit-tbl td,.audit-tbl th{font-size:.82rem;padding:.35rem .5rem}"
    )
    return (
        _head_html("Audit Log — WealthEagle", extra_css, robots="noindex, nofollow")
        + f"""<body>
{_header_html(username, role, "admin")}
<div class="app-main">
  <h1 style="font-size:1.2rem;font-weight:700">Audit Log</h1>
  <div class="card">
    <div id="filters">
      <select id="fType"><option value="">All event types</option></select>
      <input id="fUser" type="text" placeholder="Filter by username" style="max-width:180px">
      <button class="btn btn-primary btn-sm" id="filterBtn">Filter</button>
    </div>
    <table class="data-table audit-tbl">
      <thead><tr><th>Time</th><th>Event</th><th>User</th><th>IP</th><th>Detail</th><th>OK</th></tr></thead>
      <tbody id="auditBody"></tbody>
    </table>
    <div style="margin-top:.75rem;display:flex;gap:.5rem">
      <button class="btn btn-secondary btn-sm" id="prevBtn" disabled>Previous</button>
      <button class="btn btn-secondary btn-sm" id="nextBtn">Next</button>
    </div>
  </div>
</div>
{_COMMON_JS}
<script>
let _offset = 0;
const _limit = 100;
async function loadEvents() {{
  const type = document.getElementById('fType').value;
  const user = document.getElementById('fUser').value.trim();
  let url = '/api/audit-events?limit=' + _limit + '&offset=' + _offset;
  if (type) url += '&type=' + encodeURIComponent(type);
  if (user) url += '&username=' + encodeURIComponent(user);
  const resp = await fetch(url);
  const data = await resp.json();
  const tbody = document.getElementById('auditBody');
  tbody.innerHTML = '';
  (data.events || []).forEach(e => {{
    const tr = document.createElement('tr');
    tr.innerHTML = '<td>' + (e.timestamp||'') + '</td><td>' + (e.event_type||'') + '</td>'
      + '<td>' + (e.username||'') + '</td><td>' + (e.ip_address||'') + '</td>'
      + '<td>' + (e.detail||'') + '</td>'
      + '<td class="' + (e.success ? 'ev-ok' : 'ev-fail') + '">' + (e.success ? '&#10003;' : '&#10007;') + '</td>';
    tbody.appendChild(tr);
  }});
  const sel = document.getElementById('fType');
  if (sel.options.length <= 1 && data.event_types) {{
    data.event_types.forEach(t => {{
      const o = document.createElement('option');
      o.value = t; o.textContent = t;
      sel.appendChild(o);
    }});
  }}
  document.getElementById('prevBtn').disabled = _offset === 0;
  document.getElementById('nextBtn').disabled = (data.events||[]).length < _limit;
}}
document.getElementById('filterBtn').addEventListener('click', () => {{ _offset = 0; loadEvents(); }});
document.getElementById('prevBtn').addEventListener('click', () => {{ _offset = Math.max(0, _offset - _limit); loadEvents(); }});
document.getElementById('nextBtn').addEventListener('click', () => {{ _offset += _limit; loadEvents(); }});
loadEvents();
</script>
</body>
</html>"""
    )



def _pricing_html(username: str = "", role: str = "guest") -> str:
    """Pricing page with feature comparison and Stripe checkout link."""
    stripe_url = STRIPE_CHECKOUT_URL
    cta_btn = (
        f'<a class="btn btn-primary btn-lg" href="{stripe_url}">Get Started</a>'
        if stripe_url
        else '<span class="btn btn-secondary btn-lg disabled">Coming soon</span>'
    )

    extra_css = r"""
/* ---- Pricing page ---- */
.pricing-page{max-width:860px;width:100%;margin:0 auto;padding:2.5rem 1rem;display:flex;flex-direction:column;gap:2.5rem}
.pricing-hero{text-align:center}
.pricing-hero h1{font-size:clamp(1.4rem,3.5vw,2rem);font-weight:700;letter-spacing:-0.03em;margin-bottom:0.5rem}
.pricing-hero p{font-size:0.95rem;color:var(--muted);max-width:500px;margin:0 auto}

/* Pricing cards */
.pricing-cards{display:grid;grid-template-columns:1fr 1fr;gap:1.5rem}
.pricing-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:1.75rem;display:flex;flex-direction:column}
.pricing-card.featured{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent)}
.pricing-card-header{margin-bottom:1.25rem}
.pricing-card-name{font-size:1rem;font-weight:700;margin-bottom:0.25rem}
.pricing-card-price{font-size:1.8rem;font-weight:700;color:var(--accent)}
.pricing-card-price .period{font-size:0.8rem;font-weight:500;color:var(--muted)}
.pricing-card-desc{font-size:0.8rem;color:var(--muted);margin-top:0.35rem}
.annual-badge{display:inline-block;font-size:0.68rem;font-weight:700;padding:0.15rem 0.5rem;border-radius:8px;background:rgba(52,211,153,0.12);color:var(--green);margin-left:0.5rem}
.pricing-card-features{list-style:none;display:flex;flex-direction:column;gap:0.5rem;flex:1;margin-bottom:1.25rem}
.pricing-card-features li{font-size:0.83rem;display:flex;align-items:flex-start;gap:0.5rem}
.pricing-card-features .check{color:var(--green);font-weight:700;flex-shrink:0}
.pricing-card-features .cross{color:var(--muted);flex-shrink:0;opacity:0.5}
.pricing-card .btn-lg{padding:0.7rem 1.5rem;font-size:0.92rem;width:100%;text-align:center}
.pricing-card .btn-lg.disabled{opacity:0.5;cursor:default;pointer-events:none}

/* Feature comparison table */
.comparison-section{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:1.5rem;overflow-x:auto}
.comparison-section h2{font-size:1rem;font-weight:700;margin-bottom:1rem}
.comparison-table{width:100%;border-collapse:collapse;font-size:0.83rem}
.comparison-table th,.comparison-table td{padding:0.6rem 0.75rem;text-align:left;border-bottom:1px solid var(--border)}
.comparison-table th{font-size:0.68rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--muted);font-weight:600}
.comparison-table th:not(:first-child),.comparison-table td:not(:first-child){text-align:center;width:100px}
.comparison-table .check-icon{color:var(--green);font-weight:700}
.comparison-table .cross-icon{color:var(--muted);opacity:0.4}
.comparison-table tbody tr:hover{background:var(--raised)}

/* FAQ section */
.faq-section h2{font-size:1rem;font-weight:700;margin-bottom:1rem}
.faq-item{border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:0.5rem;overflow:hidden}
.faq-question{display:flex;align-items:center;justify-content:space-between;padding:0.85rem 1rem;cursor:pointer;font-size:0.88rem;font-weight:600;background:var(--surface);transition:background 0.12s}
.faq-question:hover{background:var(--raised)}
.faq-chevron{font-size:0.7rem;color:var(--muted);transition:transform 0.2s}
.faq-item.open .faq-chevron{transform:rotate(180deg);color:var(--accent)}
.faq-answer{display:none;padding:0 1rem 1rem;font-size:0.83rem;color:var(--muted);line-height:1.6}
.faq-item.open .faq-answer{display:block}

@media (max-width:768px){
  .pricing-cards{grid-template-columns:1fr}
  .pricing-page{padding:1.5rem 0.75rem;gap:1.75rem}
}
"""

    return (
        _head_html("Pricing — WealthEagle Portfolio Analytics",
                   extra_css=extra_css,
                   description="Simple, transparent pricing for WealthEagle portfolio analytics and Slovenian tax reporting. Free demo included.",
                   canonical_path="/pricing",
                   robots="index, follow")
        + f"""<body>
{_header_html(username, role, "pricing")}
<div class="pricing-page">
  <section class="pricing-hero">
    <h1>Simple, transparent pricing</h1>
    <p>Everything you need to track your portfolio and file taxes — self-hosted and private.</p>
  </section>

  <section class="pricing-cards">
    <div class="pricing-card">
      <div class="pricing-card-header">
        <div class="pricing-card-name">Demo</div>
        <div class="pricing-card-price">Free</div>
        <div class="pricing-card-desc">Explore with sample data</div>
      </div>
      <ul class="pricing-card-features">
        <li><span class="check">&#10003;</span> Sample portfolio dashboard</li>
        <li><span class="cross">&#10005;</span> Upload your own data</li>
        <li><span class="cross">&#10005;</span> Tax exports</li>
        <li><span class="cross">&#10005;</span> Projections &amp; reports</li>
      </ul>
      <a class="btn btn-secondary btn-lg" href="/report">Try Demo</a>
    </div>
    <div class="pricing-card featured">
      <div class="pricing-card-header">
        <div class="pricing-card-name">Premium<span class="annual-badge">Save 20% yearly</span></div>
        <div class="pricing-card-price">&euro;9<span class="period">/month</span></div>
        <div class="pricing-card-desc">Or &euro;86/year (billed annually)</div>
      </div>
      <ul class="pricing-card-features">
        <li><span class="check">&#10003;</span> Upload your own data</li>
        <li><span class="check">&#10003;</span> Multi-asset tracking</li>
        <li><span class="check">&#10003;</span> eDavki XML tax export</li>
        <li><span class="check">&#10003;</span> FIRE / Monte Carlo projections</li>
        <li><span class="check">&#10003;</span> Email reports</li>
        <li><span class="check">&#10003;</span> Everything included</li>
      </ul>
      {cta_btn}
    </div>
  </section>

  <section class="comparison-section">
    <h2>Feature Comparison</h2>
    <table class="comparison-table">
      <thead>
        <tr><th>Feature</th><th>Demo</th><th>Premium</th></tr>
      </thead>
      <tbody>
        <tr><td>Sample portfolio dashboard</td><td class="check-icon">&#10003;</td><td class="check-icon">&#10003;</td></tr>
        <tr><td>Upload your own data</td><td class="cross-icon">&#10005;</td><td class="check-icon">&#10003;</td></tr>
        <tr><td>Multi-asset tracking (stocks, CFD, crypto, savings)</td><td class="cross-icon">&#10005;</td><td class="check-icon">&#10003;</td></tr>
        <tr><td>eDavki XML tax export</td><td class="cross-icon">&#10005;</td><td class="check-icon">&#10003;</td></tr>
        <tr><td>Dividend income &amp; withholding tax report</td><td class="cross-icon">&#10005;</td><td class="check-icon">&#10003;</td></tr>
        <tr><td>Tax-loss harvesting suggestions</td><td class="cross-icon">&#10005;</td><td class="check-icon">&#10003;</td></tr>
        <tr><td>FIRE / Monte Carlo projections</td><td class="cross-icon">&#10005;</td><td class="check-icon">&#10003;</td></tr>
        <tr><td>Email reports (weekly/monthly)</td><td class="cross-icon">&#10005;</td><td class="check-icon">&#10003;</td></tr>
        <tr><td>Investment notes</td><td class="cross-icon">&#10005;</td><td class="check-icon">&#10003;</td></tr>
        <tr><td>Real estate tracking</td><td class="cross-icon">&#10005;</td><td class="check-icon">&#10003;</td></tr>
        <tr><td>PDF tax summary export</td><td class="cross-icon">&#10005;</td><td class="check-icon">&#10003;</td></tr>
      </tbody>
    </table>
  </section>

  <section class="faq-section">
    <h2>Frequently Asked Questions</h2>
    <div class="faq-item">
      <div class="faq-question" tabindex="0" role="button" aria-expanded="false">
        <span>Where is my data stored?</span>
        <span class="faq-chevron">&#9660;</span>
      </div>
      <div class="faq-answer">Your data is stored on your own self-hosted server in a local SQLite database. No third-party services have access to your portfolio or trading data.</div>
    </div>
    <div class="faq-item">
      <div class="faq-question" tabindex="0" role="button" aria-expanded="false">
        <span>Which brokers are supported?</span>
        <span class="faq-chevron">&#9660;</span>
      </div>
      <div class="faq-answer">Currently supported: Revolut, Trading 212, IBKR (Interactive Brokers), Degiro, and Ilirika. CSV exports from these brokers are auto-detected on import.</div>
    </div>
    <div class="faq-item">
      <div class="faq-question" tabindex="0" role="button" aria-expanded="false">
        <span>Can I cancel anytime?</span>
        <span class="faq-chevron">&#9660;</span>
      </div>
      <div class="faq-answer">Yes. You can cancel your subscription at any time. Your data remains accessible and you can export everything before your plan expires.</div>
    </div>
    <div class="faq-item">
      <div class="faq-question" tabindex="0" role="button" aria-expanded="false">
        <span>What tax regimes are supported?</span>
        <span class="faq-chevron">&#9660;</span>
      </div>
      <div class="faq-answer">Slovenia (eDavki), Germany, and Austria tax reporting are supported. The system handles holding-period-based rates, FIFO matching, and generates the correct XML formats for each regime.</div>
    </div>
  </section>
<script>
document.querySelectorAll('.faq-question').forEach(function(q) {{
  function toggle() {{
    var item = q.parentElement;
    var isOpen = item.classList.toggle('open');
    q.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
  }}
  q.addEventListener('click', toggle);
  q.addEventListener('keydown', function(e) {{
    if (e.key === 'Enter' || e.key === ' ') {{ e.preventDefault(); toggle(); }}
  }});
}});
</script>
</div>
{_COMMON_JS}
</body>
</html>"""
    )


