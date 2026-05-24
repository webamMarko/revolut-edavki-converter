"""Admin functionality: user management, audit log, Stripe webhooks."""

import hashlib
import hmac
import json
import os
import secrets
from urllib.parse import parse_qs, urlparse

from .auth import get_session, get_client_ip
from .templates import page_env, FOUC_SCRIPT, COMMON_JS, html_response, json_response, redirect

APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8080")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")


def verify_stripe_signature(body: bytes, sig_header: str, secret: str) -> bool:
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


# ------------------------------------------------------------------
# Route handlers
# ------------------------------------------------------------------

def serve_admin_page(handler):
    """GET /admin — admin user management page."""
    session = get_session(handler)
    if not session or session["role"] != "admin":
        redirect(handler, "/login")
        return
    from ..users import list_users
    users = list_users()
    template = page_env.get_template("pages/admin.html.j2")
    html = template.render(
        users=users,
        current_username=session["username"],
        fouc_script=FOUC_SCRIPT,
        common_js=COMMON_JS,
        show_header=True,
        show_drop_import=True,
    )
    html_response(handler, html)


def serve_audit_log(handler):
    """GET /admin/audit-log — audit log page."""
    session = get_session(handler)
    if not session or session["role"] != "admin":
        redirect(handler, "/login")
        return

    template = page_env.get_template("pages/audit_log.html.j2")
    html = template.render(
        username=session["username"],
        role=session["role"],
        fouc_script=FOUC_SCRIPT,
        common_js=COMMON_JS,
        show_header=True,
        show_drop_import=False,
        active_page="admin"
    )
    html_response(handler, html)


def api_audit_events(handler):
    """GET /api/audit-events — query audit events (admin only)."""
    session = get_session(handler)
    if not session or session["role"] != "admin":
        json_response(handler, {"error": "Forbidden"}, status=403)
        return
    from ..audit import query_events, get_event_types
    qs = parse_qs(urlparse(handler.path).query)
    event_type = qs.get("type", [None])[0]
    username = qs.get("username", [None])[0]
    limit = min(int(qs.get("limit", ["200"])[0]), 1000)
    offset = int(qs.get("offset", ["0"])[0])
    events = query_events(event_type=event_type, username=username, limit=limit, offset=offset)
    types = get_event_types()
    json_response(handler, {"events": events, "event_types": types})


def serve_admin_users_json(handler):
    """GET /admin/users — user list JSON (admin only)."""
    session = get_session(handler)
    if not session or session["role"] != "admin":
        json_response(handler, {"error": "Forbidden"}, status=403)
        return
    from ..users import list_users
    users = list_users()
    json_response(handler, [
        {"id": u.id, "username": u.username, "email": u.email, "role": u.role,
         "has_password": bool(u.password_hash), "invite_pending": bool(u.invite_token),
         "created_at": u.created_at, "last_login": u.last_login}
        for u in users
    ])


def handle_admin_create_user(handler):
    """POST /admin/users — create a new user and send invite."""
    session = get_session(handler)
    if not session or session["role"] != "admin":
        json_response(handler, {"error": "Forbidden"}, status=403)
        return

    body = handler._read_body()
    try:
        data = json.loads(body)
        email = data.get("email", "").strip().lower()
        role = data.get("role", "premium")
    except Exception:
        json_response(handler, {"error": "Invalid JSON"}, status=400)
        return

    if not email or "@" not in email:
        json_response(handler, {"error": "Valid email required"}, status=400)
        return
    if role not in ("premium", "admin"):
        json_response(handler, {"error": "Role must be premium or admin"}, status=400)
        return

    from ..users import create_user, get_user_by_email
    if get_user_by_email(email):
        json_response(handler, {"error": "A user with that email already exists"}, status=409)
        return

    user, raw_token = create_user(email, role=role)
    invite_url = f"{APP_BASE_URL}/invite/{raw_token}"

    # Send invite email
    sent = False
    try:
        from ..email_service import send_invite
        send_invite(email, invite_url, user.username)
        sent = True
    except Exception:
        pass  # Don't fail the creation if email fails

    from ..audit import log_event
    log_event("admin_create_user", username=session["username"],
              ip_address=get_client_ip(handler), detail=f"created {user.username} ({email}) role={role}")

    json_response(handler, {
        "ok": True,
        "username": user.username,
        "invite_url": invite_url,
        "email_sent": sent,
    })


def handle_admin_set_role(handler, user_id_str: str):
    """POST /admin/users/<id>/role — change user role."""
    session = get_session(handler)
    if not session or session["role"] != "admin":
        json_response(handler, {"error": "Forbidden"}, status=403)
        return

    body = handler._read_body()
    try:
        data = json.loads(body)
        role = data.get("role", "")
    except Exception:
        json_response(handler, {"error": "Invalid JSON"}, status=400)
        return

    try:
        user_id = int(user_id_str)
    except ValueError:
        json_response(handler, {"error": "Invalid user id"}, status=400)
        return

    from ..users import set_role
    from ..audit import log_event
    ok = set_role(user_id, role)
    if ok:
        log_event("role_change", username=session["username"],
                  ip_address=get_client_ip(handler), detail=f"user_id={user_id} new_role={role}")
    json_response(handler, {"ok": ok})


# ------------------------------------------------------------------
# Stripe webhook
# ------------------------------------------------------------------

def handle_stripe_webhook(handler):
    """POST /webhook/stripe — handle Stripe events."""
    body = handler._read_body()
    sig_header = handler.headers.get("Stripe-Signature", "")

    if STRIPE_WEBHOOK_SECRET and not verify_stripe_signature(body, sig_header, STRIPE_WEBHOOK_SECRET):
        handler.send_error(400, "Invalid signature")
        return

    try:
        event = json.loads(body)
    except Exception:
        handler.send_error(400, "Invalid JSON")
        return

    event_type = event.get("type", "")
    obj = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        # Check if this is a cofounder licence purchase
        metadata = obj.get("metadata", {})
        purpose = metadata.get("purpose", "")
        stripe_customer_id = obj.get("customer", "")

        if purpose == "cofounder_licence":
            # Cofounder one-time purchase → upgrade existing user to cofounder
            if stripe_customer_id:
                from ..users import get_user_by_id, set_role, get_users_db
                from datetime import datetime, timezone

                # Find user by stripe_customer_id
                conn = get_users_db()
                try:
                    row = conn.execute(
                        "SELECT id FROM users WHERE stripe_customer_id = ?",
                        (stripe_customer_id,)
                    ).fetchone()
                    if row:
                        user_id = row["id"]
                        # Upgrade role to cofounder
                        set_role(user_id, "cofounder", conn=conn)
                        # Initialize credits
                        now_iso = datetime.now(timezone.utc).isoformat()
                        conn.execute(
                            "UPDATE users SET credits_remaining = 100, credits_last_reset = ? WHERE id = ?",
                            (now_iso, user_id)
                        )
                        conn.commit()
                finally:
                    conn.close()
        else:
            # Standard subscription purchase → create premium user + send invite
            email = obj.get("customer_details", {}).get("email") or obj.get("customer_email", "")
            if email:
                from ..users import create_stripe_user
                user, raw_token = create_stripe_user(email, stripe_customer_id)
                if raw_token:
                    invite_url = f"{APP_BASE_URL}/invite/{raw_token}"
                    try:
                        from ..email_service import send_invite
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
            from ..users import update_stripe_subscription_status
            update_stripe_subscription_status(stripe_customer_id, status)

    elif event_type == "invoice.payment_failed":
        # Payment failure → downgrade to guest immediately
        stripe_customer_id = obj.get("customer", "")
        if stripe_customer_id:
            from ..users import update_stripe_subscription_status
            update_stripe_subscription_status(stripe_customer_id, "past_due")

    elif event_type == "invoice.payment_succeeded":
        # Payment recovered → re-activate premium
        stripe_customer_id = obj.get("customer", "")
        if stripe_customer_id:
            from ..users import update_stripe_subscription_status
            update_stripe_subscription_status(stripe_customer_id, "active")

    json_response(handler, {"received": True})
