"""Ticket management for co-founder role."""

import os
from urllib.parse import parse_qs

import stripe

from ..tickets import (
    create_ticket,
    get_tickets,
    get_all_tickets,
    add_comment,
    get_comments,
    ensure_credits,
    InsufficientCreditsError,
)
from ..users import get_user_by_id, get_users_db
from .auth import get_session
from .templates import page_env, FOUC_SCRIPT, COMMON_JS, html_response, json_response, redirect

STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8081")

if STRIPE_API_KEY:
    stripe.api_key = STRIPE_API_KEY


def serve_tickets_page(handler):
    """GET /tickets — tickets list page (cofounder/admin only)."""
    session = get_session(handler)
    if not session or session["role"] not in ("cofounder", "admin"):
        redirect(handler, "/login")
        return

    # Get user and ensure credits are fresh
    user = get_user_by_id(session["user_id"])
    if not user:
        redirect(handler, "/login")
        return

    if user.role == "cofounder":
        ensure_credits(user.id)
        # Refresh user to get updated credits
        user = get_user_by_id(session["user_id"])

    # Get tickets (own for cofounder, all for admin)
    if session["role"] == "admin":
        tickets = get_all_tickets()
    else:
        tickets = get_tickets(user.id)

    template = page_env.get_template("pages/tickets.html.j2")
    html = template.render(
        tickets=tickets,
        credits_remaining=user.credits_remaining if user.role == "cofounder" else None,
        username=session["username"],
        role=session["role"],
        fouc_script=FOUC_SCRIPT,
        common_js=COMMON_JS,
        show_header=True,
        active_page="tickets"
    )
    html_response(handler, html)


def serve_ticket_detail(handler, ticket_id: int):
    """GET /tickets/{id} — ticket detail page with comments."""
    session = get_session(handler)
    if not session or session["role"] not in ("cofounder", "admin"):
        redirect(handler, "/login")
        return

    # Get the ticket
    if session["role"] == "admin":
        all_tickets = get_all_tickets()
    else:
        all_tickets = get_tickets(session["user_id"])

    ticket = next((t for t in all_tickets if t["id"] == ticket_id), None)
    if not ticket:
        # Ticket not found or not authorized
        redirect(handler, "/tickets")
        return

    # Get comments
    comments = get_comments(ticket_id)

    # Enrich comments with usernames
    for comment in comments:
        comment_user = get_user_by_id(comment["user_id"])
        comment["username"] = comment_user.username if comment_user else "Unknown"

    template = page_env.get_template("pages/ticket_detail.html.j2")
    html = template.render(
        ticket=ticket,
        comments=comments,
        username=session["username"],
        role=session["role"],
        user_id=session["user_id"],
        fouc_script=FOUC_SCRIPT,
        common_js=COMMON_JS,
        show_header=True,
        active_page="tickets"
    )
    html_response(handler, html)


def handle_create_ticket(handler):
    """POST /tickets — create a new ticket."""
    session = get_session(handler)
    if not session or session["role"] not in ("cofounder", "admin"):
        json_response(handler, {"error": "Forbidden"}, status=403)
        return

    # Parse form data
    length = int(handler.headers.get("Content-Length", 0))
    body = handler.rfile.read(length).decode("utf-8")
    params = parse_qs(body)

    ticket_type = params.get("type", [""])[0]
    title = params.get("title", [""])[0]
    description = params.get("description", [""])[0]

    # Validate
    if not ticket_type or ticket_type not in ("bug", "idea"):
        json_response(handler, {"error": "Invalid ticket type"}, status=400)
        return
    if not title or not description:
        json_response(handler, {"error": "Title and description are required"}, status=400)
        return

    # Create ticket (will deduct credit)
    try:
        ticket_id = create_ticket(
            user_id=session["user_id"],
            ticket_type=ticket_type,
            title=title,
            description=description
        )
        # Redirect to ticket detail
        handler.send_response(303)
        handler.send_header("Location", f"/tickets/{ticket_id}")
        handler.end_headers()
    except InsufficientCreditsError:
        # Return error - user has no credits
        json_response(handler, {"error": "No credits remaining"}, status=402)


def handle_add_comment(handler, ticket_id: int):
    """POST /tickets/{id}/comments — add a comment to a ticket."""
    session = get_session(handler)
    if not session or session["role"] not in ("cofounder", "admin"):
        json_response(handler, {"error": "Forbidden"}, status=403)
        return

    # Verify user has access to this ticket
    if session["role"] == "admin":
        all_tickets = get_all_tickets()
    else:
        all_tickets = get_tickets(session["user_id"])

    ticket = next((t for t in all_tickets if t["id"] == ticket_id), None)
    if not ticket:
        json_response(handler, {"error": "Ticket not found"}, status=404)
        return

    # Parse form data
    length = int(handler.headers.get("Content-Length", 0))
    body = handler.rfile.read(length).decode("utf-8")
    params = parse_qs(body)

    comment_body = params.get("body", [""])[0]
    if not comment_body:
        json_response(handler, {"error": "Comment body is required"}, status=400)
        return

    # Add comment
    add_comment(ticket_id=ticket_id, user_id=session["user_id"], body=comment_body)

    # Redirect back to ticket detail
    handler.send_response(303)
    handler.send_header("Location", f"/tickets/{ticket_id}")
    handler.end_headers()


def handle_update_status(handler, ticket_id: int):
    """POST /tickets/{id}/status — update ticket status (admin only)."""
    session = get_session(handler)
    if not session or session["role"] != "admin":
        json_response(handler, {"error": "Forbidden"}, status=403)
        return

    # Parse form data
    length = int(handler.headers.get("Content-Length", 0))
    body = handler.rfile.read(length).decode("utf-8")
    params = parse_qs(body)

    new_status = params.get("status", [""])[0]
    if new_status not in ("new", "in_progress", "done"):
        json_response(handler, {"error": "Invalid status"}, status=400)
        return

    # Update ticket status
    from ..users import get_users_db
    conn = get_users_db()
    try:
        conn.execute(
            "UPDATE tickets SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (new_status, ticket_id)
        )
        conn.commit()
    finally:
        conn.close()

    # Redirect back to ticket detail
    handler.send_response(303)
    handler.send_header("Location", f"/tickets/{ticket_id}")
    handler.end_headers()


# ------------------------------------------------------------------
# Co-founder purchase flow (Tasks 25-26)
# ------------------------------------------------------------------


def serve_cofounder_page(handler):
    """GET /cofounder — cofounder license purchase page."""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        # Only premium/admin can see the cofounder purchase page
        redirect(handler, "/login")
        return

    # Get pricing from system_settings
    conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT value FROM system_settings WHERE key = ?",
            ("cofounder_price_eur",)
        ).fetchone()
        price_eur = row["value"] if row else "249"
    finally:
        conn.close()

    template = page_env.get_template("pages/cofounder.html.j2")
    html = template.render(
        price_eur=price_eur,
        username=session["username"],
        role=session["role"],
        fouc_script=FOUC_SCRIPT,
        common_js=COMMON_JS,
        show_header=True,
        stripe_public_key=os.environ.get("STRIPE_PUBLIC_KEY", ""),
    )
    html_response(handler, html)


def handle_cofounder_checkout(handler):
    """POST /cofounder/checkout — create Stripe Checkout session."""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        json_response(handler, {"error": "Forbidden"}, status=403)
        return

    if not STRIPE_API_KEY:
        json_response(handler, {"error": "Stripe not configured"}, status=500)
        return

    # Get user and ensure they have a stripe_customer_id
    user = get_user_by_id(session["user_id"])
    if not user:
        json_response(handler, {"error": "User not found"}, status=404)
        return

    conn = get_users_db()
    try:
        # Get or create Stripe customer ID
        if not user.stripe_customer_id:
            try:
                customer = stripe.Customer.create(email=user.email)
                stripe_customer_id = customer.id
                conn.execute(
                    "UPDATE users SET stripe_customer_id = ? WHERE id = ?",
                    (stripe_customer_id, user.id)
                )
                conn.commit()
            except stripe.error.StripeError:
                json_response(handler, {"error": "Failed to create customer"}, status=500)
                return
        else:
            stripe_customer_id = user.stripe_customer_id

        # Get pricing from system_settings
        row = conn.execute(
            "SELECT value FROM system_settings WHERE key = ?",
            ("cofounder_price_eur",)
        ).fetchone()
        price_eur = row["value"] if row else "249"

        # Create Stripe Checkout session
        try:
            # Note: In production, you'd use a Stripe price ID from your account
            # For now, we use a fixed amount (in cents)
            price_cents = int(float(price_eur) * 100)

            session_obj = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[
                    {
                        "price_data": {
                            "currency": "eur",
                            "product_data": {
                                "name": "Co-Founder License",
                                "description": "Unlock unlimited tickets and credits"
                            },
                            "unit_amount": price_cents,
                        },
                        "quantity": 1,
                    }
                ],
                mode="payment",
                customer=stripe_customer_id,
                metadata={"purpose": "cofounder_licence"},
                success_url=f"{APP_BASE_URL}/account?upgrade=success",
                cancel_url=f"{APP_BASE_URL}/cofounder",
            )

            json_response(handler, {"checkout_url": session_obj.url})
        except stripe.error.StripeError as e:
            json_response(handler, {"error": f"Stripe error: {str(e)}"}, status=500)
    finally:
        conn.close()
