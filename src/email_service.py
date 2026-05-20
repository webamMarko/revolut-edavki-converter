"""Email delivery via Resend API (https://resend.com).

Uses only stdlib urllib — no requests/httpx dependency.
"""

import json
import os
import urllib.request
import urllib.error

_RESEND_API_URL = "https://api.resend.com/emails"


def _api_key() -> str:
    key = os.environ.get("RESEND_API_KEY", "")
    if not key:
        raise RuntimeError("RESEND_API_KEY environment variable is not set")
    return key


def _from_address() -> str:
    return os.environ.get("RESEND_FROM", "noreply@example.com")


def send_invite(to_email: str, invite_url: str, username: str) -> None:
    """Send a portfolio invite email via Resend."""
    subject = "You're invited to your portfolio dashboard"
    html_body = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:32px">
      <h2 style="font-size:1.3rem;margin-bottom:1rem">Welcome to your portfolio dashboard</h2>
      <p>Hi <strong>{username}</strong>,</p>
      <p>Your account has been created. Click the button below to set your password
         and access your personal portfolio dashboard.</p>
      <p style="margin:2rem 0">
        <a href="{invite_url}"
           style="background:#f59e0b;color:#000;padding:12px 24px;border-radius:6px;
                  text-decoration:none;font-weight:700;display:inline-block">
          Set password &amp; log in
        </a>
      </p>
      <p style="color:#666;font-size:0.85rem">
        This link expires in 24 hours. If you did not expect this email, you can ignore it.
      </p>
      <p style="color:#999;font-size:0.8rem;margin-top:2rem">
        {invite_url}
      </p>
    </div>
    """
    text_body = (
        f"Hi {username},\n\n"
        f"Your portfolio account has been created. Set your password here:\n\n"
        f"{invite_url}\n\n"
        f"This link expires in 24 hours.\n"
    )
    _send(to_email, subject, html_body, text_body)


def send_password_reset(to_email: str, reset_url: str) -> None:
    """Send a password reset email via Resend."""
    subject = "Reset your WealthEagle password"
    html_body = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:32px">
      <h2 style="font-size:1.3rem;margin-bottom:1rem">Reset your password</h2>
      <p>We received a request to reset your WealthEagle password.</p>
      <p>Click the button below to choose a new password. This link expires in 1 hour.</p>
      <p style="margin:2rem 0">
        <a href="{reset_url}"
           style="background:#f59e0b;color:#000;padding:12px 24px;border-radius:6px;
                  text-decoration:none;font-weight:700;display:inline-block">
          Reset password
        </a>
      </p>
      <p style="color:#666;font-size:0.85rem">
        If you did not request this, you can safely ignore this email. Your password will not change.
      </p>
      <p style="color:#999;font-size:0.8rem;margin-top:2rem">
        {reset_url}
      </p>
    </div>
    """
    text_body = (
        f"Reset your WealthEagle password here:\n\n"
        f"{reset_url}\n\n"
        f"This link expires in 1 hour.\n"
        f"If you did not request this, ignore this email.\n"
    )
    _send(to_email, subject, html_body, text_body)


def _send(to_email: str, subject: str, html: str, text: str) -> None:
    payload = json.dumps({
        "from": _from_address(),
        "to": [to_email],
        "subject": subject,
        "html": html,
        "text": text,
    }).encode()

    req = urllib.request.Request(
        _RESEND_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {_api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status >= 400:
                body = resp.read().decode()
                raise RuntimeError(f"Resend API error {resp.status}: {body}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"Resend API error {e.code}: {body}") from e
