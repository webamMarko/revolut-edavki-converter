"""Authentication and session management."""

import os
import time
from http.cookies import SimpleCookie
from typing import Optional
from urllib.parse import parse_qs

from .templates import page_env, FOUC_SCRIPT, COMMON_JS, html_response, json_response, redirect

# Rate limiting: sliding window per IP for login attempts
RATE_LIMIT_MAX_ATTEMPTS = 5
RATE_LIMIT_WINDOW_SECONDS = 900  # 15 minutes
_login_attempts: dict[str, list[float]] = {}  # ip -> [timestamps]

SESSION_TTL = 86400 * 7  # 7 days
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8081")


def get_client_ip(handler) -> str:
    """Extract client IP from request headers or socket."""
    forwarded = handler.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return handler.client_address[0] if handler.client_address else "unknown"


def check_rate_limit(ip: str) -> Optional[int]:
    """Return seconds until retry is allowed, or None if not rate-limited."""
    now = time.time()
    attempts = _login_attempts.get(ip, [])
    attempts = [t for t in attempts if now - t < RATE_LIMIT_WINDOW_SECONDS]
    _login_attempts[ip] = attempts
    if len(attempts) >= RATE_LIMIT_MAX_ATTEMPTS:
        oldest = attempts[0]
        return int(oldest + RATE_LIMIT_WINDOW_SECONDS - now) + 1
    return None


def record_login_attempt(ip: str) -> None:
    """Record a login attempt for rate limiting."""
    _login_attempts.setdefault(ip, []).append(time.time())


def get_session_token(handler) -> Optional[str]:
    """Extract raw session token from cookie (used as staging key)."""
    cookie_header = handler.headers.get("Cookie", "")
    if not cookie_header:
        return None
    c = SimpleCookie()
    c.load(cookie_header)
    morsel = c.get("session")
    return morsel.value if morsel else None


def get_session(handler) -> Optional[dict]:
    """Return session dict {user_id, username, role} or None."""
    from ..users import get_session as _db_get_session
    cookie_header = handler.headers.get("Cookie", "")
    if not cookie_header:
        return None
    c = SimpleCookie()
    c.load(cookie_header)
    morsel = c.get("session")
    if not morsel:
        return None
    return _db_get_session(morsel.value)


def create_session(user) -> str:
    """Create a persistent DB-backed session token for a User object."""
    from ..users import create_session as _db_create_session
    return _db_create_session(user)


# ------------------------------------------------------------------
# Route handlers
# ------------------------------------------------------------------

def serve_login_page(handler, error: str = ""):
    """GET /login — login form."""
    template = page_env.get_template("pages/login.html.j2")
    html = template.render(
        error=error,
        app_base_url=APP_BASE_URL.rstrip("/"),
        fouc_script=FOUC_SCRIPT,
        common_js=COMMON_JS,
        show_header=False,
        show_drop_import=False
    )
    html_response(handler, html)


def handle_login(handler):
    """POST /login — authenticate user."""
    from ..audit import log_event
    ip = get_client_ip(handler)

    retry_after = check_rate_limit(ip)
    if retry_after is not None:
        handler.send_response(429)
        handler.send_header("Retry-After", str(retry_after))
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler._add_security_headers()
        handler.end_headers()
        template = page_env.get_template("pages/login.html.j2")
        html = template.render(
            error=f"Too many login attempts. Please try again in {retry_after // 60 + 1} minutes.",
            app_base_url=APP_BASE_URL.rstrip("/"),
            fouc_script=FOUC_SCRIPT,
            common_js=COMMON_JS,
            show_header=False,
            show_drop_import=False
        )
        handler.wfile.write(html.encode("utf-8"))
        log_event("login_rate_limited", ip_address=ip)
        return

    body = handler._read_body()
    fields = parse_qs(body.decode("utf-8", errors="replace"))
    username_or_email = fields.get("username", [""])[0].strip()
    password = fields.get("password", [""])[0]

    from ..users import authenticate
    try:
        user = authenticate(username_or_email, password)
    except Exception:
        serve_login_page(handler, error="Login service unavailable. Please try again later.")
        return
    if not user:
        record_login_attempt(ip)
        log_event("login_failed", username=username_or_email, ip_address=ip, success=False)
        serve_login_page(handler, error="Invalid username or password.")
        return

    _login_attempts.pop(ip, None)
    log_event("login_success", username=user.username, ip_address=ip)
    token = create_session(user)
    handler.send_response(302)
    handler.send_header("Location", "/")
    handler.send_header(
        "Set-Cookie",
        f"session={token}; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL}; Path=/"
    )
    handler.end_headers()


def handle_logout(handler):
    """GET /logout — end session."""
    from ..audit import log_event
    from ..users import delete_session as _db_delete_session
    session = get_session(handler)
    if session:
        log_event("logout", username=session["username"], ip_address=get_client_ip(handler))
    cookie_header = handler.headers.get("Cookie", "")
    c = SimpleCookie()
    c.load(cookie_header)
    morsel = c.get("session")
    if morsel:
        _db_delete_session(morsel.value)
    handler.send_response(302)
    handler.send_header("Location", "/")
    handler.send_header(
        "Set-Cookie",
        "session=; HttpOnly; SameSite=Lax; Max-Age=0; Path=/"
    )
    handler.end_headers()


def handle_magic_login(handler, token: str):
    """GET /login/magic/<token> — passwordless login."""
    from ..users import consume_magic_token
    from .templates import error_response
    user = consume_magic_token(token)
    if not user:
        error_response(handler, "This login link is invalid, expired, or has already been used.")
        return
    session_token = create_session(user)
    handler.send_response(302)
    handler.send_header("Location", "/report")
    handler.send_header(
        "Set-Cookie",
        f"session={session_token}; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL}; Path=/"
    )
    handler.end_headers()


# ------------------------------------------------------------------
# Invite (set password)
# ------------------------------------------------------------------

def serve_invite_page(handler, token: str, error: str = ""):
    """GET /invite/<token> — invite acceptance form."""
    from ..users import get_user_by_invite_token
    from .templates import error_response
    user = get_user_by_invite_token(token)
    if not user:
        error_response(handler, "This invite link is invalid or has expired.")
        return
    template = page_env.get_template("pages/invite.html.j2")
    html = template.render(
        token=token,
        email=user.email,
        error=error,
        fouc_script=FOUC_SCRIPT,
        common_js=COMMON_JS,
        show_header=False,
        show_drop_import=False
    )
    html_response(handler, html)


def handle_invite_accept(handler, token: str):
    """POST /invite/<token> — accept invite and set password."""
    from ..users import accept_invite
    from .templates import error_response
    body = handler._read_body()
    fields = parse_qs(body.decode("utf-8", errors="replace"))
    password = fields.get("password", [""])[0]
    confirm = fields.get("confirm", [""])[0]

    if not password or len(password) < 8:
        serve_invite_page(handler, token, error="Password must be at least 8 characters.")
        return
    if password != confirm:
        serve_invite_page(handler, token, error="Passwords do not match.")
        return

    user = accept_invite(token, password)
    if not user:
        error_response(handler, "This invite link is invalid or has expired.")
        return

    session_token = create_session(user)
    handler.send_response(302)
    handler.send_header("Location", "/")
    handler.send_header(
        "Set-Cookie",
        f"session={session_token}; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL}; Path=/"
    )
    handler.end_headers()


# ------------------------------------------------------------------
# Password reset
# ------------------------------------------------------------------

def serve_reset_password_page(handler, error: str = "", success: str = ""):
    """GET /reset-password — password reset request form."""
    template = page_env.get_template("pages/reset_password_request.html.j2")
    html = template.render(
        error=error,
        success=success,
        fouc_script=FOUC_SCRIPT,
        common_js=COMMON_JS,
        show_header=False,
        show_drop_import=False
    )
    html_response(handler, html)


def handle_reset_password_request(handler):
    """POST /reset-password — request password reset."""
    from ..users import create_password_reset_token
    body = handler._read_body()
    fields = parse_qs(body.decode("utf-8", errors="replace"))
    email = fields.get("email", [""])[0].strip().lower()
    if not email:
        serve_reset_password_page(handler, error="Please enter your email address.")
        return
    token = create_password_reset_token(email)
    if token:
        reset_url = f"{APP_BASE_URL}/reset-password/{token}"
        try:
            from ..email_service import send_password_reset
            send_password_reset(email, reset_url)
        except Exception:
            pass
    # Always show success (don't leak whether email exists)
    serve_reset_password_page(
        handler,
        success="If that email is registered, you will receive a password reset link shortly."
    )


def serve_reset_password_confirm_page(handler, token: str, error: str = ""):
    """GET /reset-password/<token> — password reset confirmation form."""
    from ..users import get_users_db
    from .templates import error_response
    from datetime import datetime, timezone

    conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT * FROM password_reset_tokens WHERE token = ? AND used_at IS NULL",
            (token,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        error_response(handler, "This password reset link is invalid or has already been used.")
        return
    try:
        expires = datetime.fromisoformat(row["expires_at"])
        if datetime.now(timezone.utc) > expires:
            error_response(handler, "This password reset link has expired. Please request a new one.")
            return
    except ValueError:
        pass
    template = page_env.get_template("pages/reset_password_confirm.html.j2")
    html = template.render(
        token=token,
        error=error,
        fouc_script=FOUC_SCRIPT,
        common_js=COMMON_JS,
        show_header=False,
        show_drop_import=False
    )
    html_response(handler, html)


def handle_reset_password_confirm(handler, token: str):
    """POST /reset-password/<token> — confirm password reset."""
    from ..users import consume_password_reset_token
    from ..audit import log_event
    from .templates import error_response

    body = handler._read_body()
    fields = parse_qs(body.decode("utf-8", errors="replace"))
    password = fields.get("password", [""])[0]
    confirm = fields.get("confirm", [""])[0]
    if not password or len(password) < 8:
        serve_reset_password_confirm_page(handler, token, error="Password must be at least 8 characters.")
        return
    if password != confirm:
        serve_reset_password_confirm_page(handler, token, error="Passwords do not match.")
        return
    user = consume_password_reset_token(token, password)
    if not user:
        error_response(handler, "This password reset link is invalid, expired, or already used.")
        return
    log_event("password_reset", username=user.username, ip_address=get_client_ip(handler))
    session_token = create_session(user)
    handler.send_response(302)
    handler.send_header("Location", "/")
    handler.send_header(
        "Set-Cookie",
        f"session={session_token}; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL}; Path=/"
    )
    handler.end_headers()


# ------------------------------------------------------------------
# Account management
# ------------------------------------------------------------------

def serve_account_page(handler):
    """GET /account — account settings."""
    session = get_session(handler)
    if not session:
        redirect(handler, "/login")
        return
    from ..users import get_user_by_id

    STRIPE_BILLING_PORTAL_URL = os.environ.get("STRIPE_BILLING_PORTAL_URL", "")

    user = get_user_by_id(session["user_id"])
    template = page_env.get_template("pages/account.html.j2")
    html = template.render(
        username=session["username"],
        role=session["role"],
        email=user.email if user else "",
        subscription_status=(user.stripe_subscription_status or "—") if user else "—",
        billing_portal_url=STRIPE_BILLING_PORTAL_URL,
        fouc_script=FOUC_SCRIPT,
        common_js=COMMON_JS,
        show_header=True,
        show_drop_import=False,
    )
    html_response(handler, html)


def handle_change_password(handler):
    """POST /account/change-password — change password."""
    session = get_session(handler)
    if not session:
        json_response(handler, {"error": "Not authenticated"}, 401)
        return
    body = handler._read_body()
    fields = parse_qs(body.decode("utf-8", errors="replace"))
    current_pw = fields.get("current_password", [""])[0]
    new_pw = fields.get("new_password", [""])[0]
    confirm_pw = fields.get("confirm_password", [""])[0]

    from ..users import get_user_by_id, verify_password, change_password
    from ..audit import log_event

    user = get_user_by_id(session["user_id"])
    if not user:
        json_response(handler, {"error": "User not found"}, 400)
        return
    if user.password_hash and not verify_password(user.password_hash, current_pw):
        json_response(handler, {"error": "Current password is incorrect."}, 400)
        return
    if not new_pw or len(new_pw) < 8:
        json_response(handler, {"error": "New password must be at least 8 characters."}, 400)
        return
    if new_pw != confirm_pw:
        json_response(handler, {"error": "Passwords do not match."}, 400)
        return
    change_password(session["user_id"], new_pw)
    log_event("password_change", username=session["username"], ip_address=get_client_ip(handler))
    json_response(handler, {"ok": True})


def handle_delete_account(handler):
    """POST /account/delete — delete account."""
    session = get_session(handler)
    if not session:
        json_response(handler, {"error": "Not authenticated"}, 401)
        return
    if session["role"] == "admin":
        json_response(handler, {"error": "Admin accounts cannot be self-deleted."}, 403)
        return
    from ..users import delete_user, delete_session as _db_delete_session
    # Delete session first
    token = get_session_token(handler)
    if token:
        _db_delete_session(token)
    delete_user(session["user_id"])
    handler.send_response(302)
    handler.send_header("Location", "/")
    handler.send_header(
        "Set-Cookie",
        "session=; HttpOnly; SameSite=Lax; Max-Age=0; Path=/"
    )
    handler.end_headers()
