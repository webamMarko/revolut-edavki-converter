"""Lightweight web UI for CSV upload, import, and portfolio dashboard.

Multi-user mode: session cookies, per-user SQLite databases, role-based access.
Roles: guest (unauthenticated, sees demo portfolio), premium (own DB), admin (+ user management).
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import time
from http.cookies import SimpleCookie
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# ---------------------------------------------------------------------------
# Environment / constants
# ---------------------------------------------------------------------------

DATA_DIR = Path(os.environ.get("REVOLUT_DATA_DIR", "/data"))
DEMO_DB  = DATA_DIR / "_demo" / "portfolio.db"

APP_BASE_URL           = os.environ.get("APP_BASE_URL", "http://localhost:8080")
STRIPE_WEBHOOK_SECRET  = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

SESSION_TTL = 86400 * 7  # 7 days

# In-process session store: token -> {user_id, username, role, expires}
_SESSIONS: dict[str, dict] = {}

# Import wizard staging: token -> {path, dir, filename, expires}
_IMPORT_STAGING: dict[str, dict] = {}


def _detect_asset_class_from_headers(headers: list) -> str | None:
    """Detect asset class from CSV header list."""
    cols = {h.strip() for h in headers}
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


def _portfolio_conn(user: dict | None):
    """Return a DB connection for the given session user (or demo DB if no user)."""
    from .db import get_connection
    if user and user["role"] in ("premium", "admin"):
        return get_connection(db_path=_user_db_path(user["username"]))
    return get_connection(db_path=DEMO_DB)


def _create_session(user) -> str:
    """Create a session token for a User object and store it."""
    token = secrets.token_urlsafe(32)
    _SESSIONS[token] = {
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
        "expires": time.time() + SESSION_TTL,
    }
    return token


def _get_session(handler) -> dict | None:
    """Return session dict or None."""
    cookie_header = handler.headers.get("Cookie", "")
    if not cookie_header:
        return None
    c = SimpleCookie()
    c.load(cookie_header)
    morsel = c.get("session")
    if not morsel:
        return None
    token = morsel.value
    session = _SESSIONS.get(token)
    if not session:
        return None
    if session["expires"] < time.time():
        del _SESSIONS[token]
        return None
    return session


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

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def do_GET(self):
        path = urlparse(self.path).path
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
        elif path.startswith("/invite/"):
            token = path[len("/invite/"):]
            self._serve_invite_page(token)
        elif path == "/admin":
            self._serve_admin_page()
        elif path == "/admin/users":
            self._serve_admin_users_json()
        elif path == "/api/notes":
            self._api_list_notes()
        elif path == "/import":
            self._serve_import_wizard()
        else:
            self.send_error(404)

    def do_POST(self):
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
        elif path == "/api/notes":
            self._api_create_note()
        elif path == "/import/preview":
            self._handle_import_preview()
        elif path == "/import/run":
            self._handle_import_run()
        else:
            self.send_error(404)

    def do_PUT(self):
        path = urlparse(self.path).path
        parts = path.split("/")
        # /api/notes/<id>
        if len(parts) == 4 and parts[1] == "api" and parts[2] == "notes" and parts[3].isdigit():
            self._api_update_note(int(parts[3]))
        else:
            self.send_error(404)

    def do_DELETE(self):
        path = urlparse(self.path).path
        parts = path.split("/")
        # /api/notes/<id>
        if len(parts) == 4 and parts[1] == "api" and parts[2] == "notes" and parts[3].isdigit():
            self._api_delete_note(int(parts[3]))
        else:
            self.send_error(404)

    # ------------------------------------------------------------------
    # Login / logout
    # ------------------------------------------------------------------

    def _serve_login_page(self, error: str = ""):
        html = _login_html(error)
        self._html_response(html)

    def _handle_login(self):
        body = self._read_body()
        fields = parse_qs(body.decode("utf-8", errors="replace"))
        username_or_email = fields.get("username", [""])[0].strip()
        password = fields.get("password", [""])[0]

        from .users import authenticate
        user = authenticate(username_or_email, password)
        if not user:
            self._serve_login_page(error="Invalid username or password.")
            return

        token = _create_session(user)
        self.send_response(302)
        self.send_header("Location", "/")
        self.send_header(
            "Set-Cookie",
            f"session={token}; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL}; Path=/"
        )
        self.end_headers()

    def _handle_logout(self):
        cookie_header = self.headers.get("Cookie", "")
        c = SimpleCookie()
        c.load(cookie_header)
        morsel = c.get("session")
        if morsel and morsel.value in _SESSIONS:
            del _SESSIONS[morsel.value]
        self.send_response(302)
        self.send_header("Location", "/")
        self.send_header(
            "Set-Cookie",
            "session=; HttpOnly; SameSite=Lax; Max-Age=0; Path=/"
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
        self._html_response(_invite_html(token, user.email, error))

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
        if session:
            self._redirect("/report")
            return
        # Inject user info into the page for the JS to use
        user_json = json.dumps({
            "username": session["username"] if session else None,
            "role": session["role"] if session else "guest",
        })
        html = _UPLOAD_HTML.replace("__USER_JSON__", user_json)
        self._html_response(html)

    # ------------------------------------------------------------------
    # Status (JSON)
    # ------------------------------------------------------------------

    def _serve_status(self):
        session = _get_session(self)
        conn = _portfolio_conn(session)
        db_path = _user_db_path(session["username"]) if session and session["role"] in ("premium", "admin") else DEMO_DB
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
                    results.append({
                        "filename": filename,
                        "total": result.total,
                        "new": result.new,
                        "skipped": result.skipped,
                    })
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

        conn = get_connection(db_path=_user_db_path(session["username"]))
        try:
            sync_all(conn, verbose=self.verbose)
            self._json_response({"ok": True})
        except Exception as e:
            self._json_response({"error": str(e)}, status=500)
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def _serve_report(self):
        session = _get_session(self)
        from .analytics import compute_analytics
        from .tax import compute_tax_report
        from .html_report import (generate_html_report, query_transactions,
                                   query_real_estate, query_fire_config,
                                   query_investment_notes)
        from datetime import datetime

        conn = _portfolio_conn(session)
        try:
            analytics = compute_analytics(conn, scope="all")
            tax_by_year = {}
            try:
                years_with_tx = [
                    int(r[0]) for r in conn.execute(
                        "SELECT DISTINCT strftime('%Y', date) FROM transactions "
                        "WHERE asset_class != 'realestate' ORDER BY 1"
                    ).fetchall()
                ]
                for yr in years_with_tx:
                    try:
                        tax_by_year[yr] = compute_tax_report(conn, year=yr, include_unrealized=False, scope="all")
                    except Exception:
                        pass
            except Exception:
                pass
            transactions = query_transactions(conn)
            per_class = {}
            for ac in [r[0] for r in conn.execute("SELECT DISTINCT asset_class FROM transactions").fetchall()]:
                try:
                    per_class[ac] = compute_analytics(conn, scope=ac)
                except Exception:
                    pass
            re_data = query_real_estate(conn)
            fire_cfg = query_fire_config(conn)
            notes = query_investment_notes(conn)
            html = generate_html_report(analytics, tax_by_year, transactions, per_class=per_class,
                                        real_estate=re_data, fire_config=fire_cfg,
                                        investment_notes=notes, conn=conn)
            # Inject current user into D so client JS can gate the edit UI.
            # The report template emits:  <script>const D={...};</script>
            # We append D.user right after the D assignment closes.
            user_payload = json.dumps({
                "id": session["user_id"],
                "username": session["username"],
                "role": session["role"],
            }) if session else "null"
            html = html.replace(
                "<script>const D=",
                f"<script>const D=",
                1,
            )
            # Find the </script> that closes the D= block and inject before it
            d_script_end = html.find(";</script>", html.find("<script>const D="))
            if d_script_end != -1:
                html = html[:d_script_end] + f";D.user={user_payload}" + html[d_script_end:]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"Error generating report: {e}".encode("utf-8"))
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
        self._html_response(_admin_html(users, session["username"]))

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
        except Exception as e:
            pass  # Don't fail the creation if email fails

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

        if event.get("type") == "checkout.session.completed":
            obj = event.get("data", {}).get("object", {})
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
            from .notes import add_note, get_note
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
    # Import wizard
    # ------------------------------------------------------------------

    def _serve_import_wizard(self):
        session = _get_session(self)
        if not session or session["role"] not in ("premium", "admin"):
            self._redirect("/login")
            return
        self._html_response(_import_wizard_html())

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

    def _read_body(self, length: int | None = None) -> bytes:
        if length is None:
            length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length)

    def _html_response(self, html: str, status: int = 200):
        encoded = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _json_response(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, path: str):
        self.send_response(302)
        self.send_header("Location", path)
        self.end_headers()


# ---------------------------------------------------------------------------
# Server entry point
# ---------------------------------------------------------------------------

def start_server(host="0.0.0.0", port=8080, verbose=False):
    """Start the web server."""
    UploadHandler.verbose = verbose
    server = ThreadingHTTPServer((host, port), UploadHandler)
    print(f"Server running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


# ---------------------------------------------------------------------------
# Inline HTML: login page
# ---------------------------------------------------------------------------

def _login_html(error: str = "") -> str:
    error_block = f'<p class="error">{error}</p>' if error else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Login — Portfolio</title>
<style>
:root {{--bg:#0a0c10;--surface:#111520;--border:#1e2a3a;--text:#dce4f0;--muted:#556075;
       --accent:#f59e0b;--red:#f87171;--radius:10px}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
      background:var(--bg);color:var(--text);min-height:100vh;
      display:flex;align-items:center;justify-content:center;padding:1rem}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);
       padding:2rem;width:100%;max-width:380px}}
label{{display:block;font-size:0.72rem;font-weight:600;color:var(--muted);
       text-transform:uppercase;letter-spacing:.06em;margin-bottom:.3rem}}
input{{width:100%;padding:.55rem .75rem;border:1px solid var(--border);border-radius:6px;
       background:var(--bg);color:var(--text);font-size:.9rem;font-family:inherit;margin-bottom:1rem}}
input:focus{{outline:none;border-color:var(--accent)}}
button{{width:100%;padding:.65rem;background:var(--accent);color:#000;font-weight:700;
        font-size:.9rem;font-family:inherit;border:none;border-radius:6px;cursor:pointer}}
button:hover{{opacity:.9}}
.error{{color:var(--red);font-size:.82rem;margin-bottom:1rem;text-align:center}}
.logo{{text-align:center;margin-bottom:1.5rem;font-size:1.5rem;font-weight:700;letter-spacing:-0.03em}}
.logo span{{color:var(--accent)}}
</style>
</head>
<body>
<div class="card">
  <div class="logo"><a href="/" style="text-decoration:none;color:inherit">Portfolio<span>.</span></a></div>
  {error_block}
  <form method="POST" action="/login">
    <label>Username or email</label>
    <input type="text" name="username" required autofocus autocomplete="username">
    <label>Password</label>
    <input type="password" name="password" required autocomplete="current-password">
    <button type="submit">Log in</button>
  </form>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Inline HTML: invite / set-password page
# ---------------------------------------------------------------------------

def _invite_html(token: str, email: str, error: str = "") -> str:
    error_block = f'<p class="error">{error}</p>' if error else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Set Password — Portfolio</title>
<style>
:root {{--bg:#0a0c10;--surface:#111520;--border:#1e2a3a;--text:#dce4f0;--muted:#556075;
       --accent:#f59e0b;--red:#f87171;--radius:10px}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
      background:var(--bg);color:var(--text);min-height:100vh;
      display:flex;align-items:center;justify-content:center;padding:1rem}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);
       padding:2rem;width:100%;max-width:400px}}
h1{{font-size:1.2rem;font-weight:700;margin-bottom:.5rem;text-align:center}}
.sub{{font-size:.82rem;color:var(--muted);text-align:center;margin-bottom:1.5rem}}
label{{display:block;font-size:.72rem;font-weight:600;color:var(--muted);
       text-transform:uppercase;letter-spacing:.06em;margin-bottom:.3rem}}
input{{width:100%;padding:.55rem .75rem;border:1px solid var(--border);border-radius:6px;
       background:var(--bg);color:var(--text);font-size:.9rem;font-family:inherit;margin-bottom:1rem}}
input:focus{{outline:none;border-color:var(--accent)}}
button{{width:100%;padding:.65rem;background:var(--accent);color:#000;font-weight:700;
        font-size:.9rem;font-family:inherit;border:none;border-radius:6px;cursor:pointer}}
button:hover{{opacity:.9}}
.error{{color:var(--red);font-size:.82rem;margin-bottom:1rem;text-align:center}}
</style>
</head>
<body>
<div class="card">
  <h1>Set your password</h1>
  <p class="sub">Account: <strong>{email}</strong></p>
  {error_block}
  <form method="POST" action="/invite/{token}">
    <label>Password</label>
    <input type="password" name="password" required minlength="8" autocomplete="new-password">
    <label>Confirm password</label>
    <input type="password" name="confirm" required minlength="8" autocomplete="new-password">
    <button type="submit">Set password &amp; log in</button>
  </form>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Inline HTML: generic error page
# ---------------------------------------------------------------------------

def _error_html(message: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Error</title>
<style>body{{font-family:sans-serif;background:#0a0c10;color:#dce4f0;
             display:flex;align-items:center;justify-content:center;min-height:100vh}}
.box{{text-align:center;padding:2rem}}</style></head>
<body><div class="box"><h2>&#9888; {message}</h2>
<p style="margin-top:1rem"><a href="/" style="color:#f59e0b">Go home</a></p>
</div></body></html>"""


# ---------------------------------------------------------------------------
# Inline HTML: admin page
# ---------------------------------------------------------------------------

def _admin_html(users, current_username: str) -> str:
    rows = ""
    for u in users:
        invite_badge = '<span style="color:#f59e0b;font-size:.75rem">invite pending</span>' if u.invite_token else ""
        role_options = "".join(
            f'<option value="{r}" {"selected" if r == u.role else ""}>{r}</option>'
            for r in ("guest", "premium", "admin")
        )
        rows += f"""<tr>
          <td>{u.id}</td>
          <td>{u.username}</td>
          <td>{u.email}</td>
          <td>
            <select data-uid="{u.id}" class="role-select" {"disabled" if u.username == current_username else ""}>
              {role_options}
            </select>
            {invite_badge}
          </td>
          <td style="color:#556075;font-size:.8rem">{(u.last_login or u.created_at)[:10]}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Admin — Portfolio</title>
<style>
:root{{--bg:#0a0c10;--surface:#111520;--raised:#181e2e;--border:#1e2a3a;--text:#dce4f0;
      --muted:#556075;--accent:#f59e0b;--green:#34d399;--red:#f87171;--radius:10px}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
      background:var(--bg);color:var(--text);padding:2rem}}
h1{{font-size:1.2rem;font-weight:700;margin-bottom:1.5rem}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);
       padding:1.5rem;margin-bottom:1.5rem}}
.card h2{{font-size:.95rem;font-weight:600;margin-bottom:1rem}}
table{{width:100%;border-collapse:collapse;font-size:.85rem}}
th,td{{padding:.5rem .75rem;text-align:left;border-bottom:1px solid var(--border)}}
th{{font-size:.67rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:600}}
select{{background:var(--raised);color:var(--text);border:1px solid var(--border);
        border-radius:4px;padding:.2rem .4rem;font-size:.82rem;cursor:pointer}}
.form-row{{display:flex;gap:.75rem;margin-top:.5rem;flex-wrap:wrap}}
input[type=email],select.new-role{{padding:.5rem .75rem;border:1px solid var(--border);
  border-radius:6px;background:var(--raised);color:var(--text);font-size:.85rem;font-family:inherit}}
input[type=email]{{flex:1;min-width:200px}}
button{{padding:.5rem 1.2rem;background:var(--accent);color:#000;font-weight:700;
        font-size:.85rem;font-family:inherit;border:none;border-radius:6px;cursor:pointer}}
button:hover{{opacity:.9}}
.msg{{font-size:.82rem;margin-top:.5rem}}
.nav{{margin-bottom:1.5rem;font-size:.85rem}}
.nav a{{color:var(--accent);text-decoration:none}}
</style>
</head>
<body>
<p class="nav"><a href="/">&#8592; Back to dashboard</a></p>
<h1>Admin — User Management</h1>

<div class="card">
  <h2>Create user &amp; send invite</h2>
  <div class="form-row">
    <input type="email" id="newEmail" placeholder="user@example.com">
    <select id="newRole" class="new-role">
      <option value="premium">Premium</option>
      <option value="admin">Admin</option>
    </select>
    <button id="createBtn">Create &amp; send invite</button>
  </div>
  <p id="createMsg" class="msg"></p>
</div>

<div class="card">
  <h2>All users</h2>
  <table>
    <thead><tr><th>#</th><th>Username</th><th>Email</th><th>Role</th><th>Last seen</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>

<script>
document.getElementById('createBtn').addEventListener('click', async () => {{
  const email = document.getElementById('newEmail').value.trim();
  const role = document.getElementById('newRole').value;
  const msg = document.getElementById('createMsg');
  if (!email) {{ msg.textContent = 'Enter an email address.'; return; }}
  const resp = await fetch('/admin/users', {{
    method: 'POST',
    headers: {{'Content-Type':'application/json'}},
    body: JSON.stringify({{email, role}})
  }});
  const data = await resp.json();
  if (data.ok) {{
    msg.style.color = '#34d399';
    msg.textContent = data.email_sent
      ? 'Invite sent to ' + email + ' (username: ' + data.username + ')'
      : 'User created. Invite URL: ' + data.invite_url;
    document.getElementById('newEmail').value = '';
    setTimeout(() => location.reload(), 2000);
  }} else {{
    msg.style.color = '#f87171';
    msg.textContent = data.error;
  }}
}});

document.querySelectorAll('.role-select').forEach(sel => {{
  sel.addEventListener('change', async () => {{
    const uid = sel.dataset.uid;
    const role = sel.value;
    const resp = await fetch('/admin/users/' + uid + '/role', {{
      method: 'POST',
      headers: {{'Content-Type':'application/json'}},
      body: JSON.stringify({{role}})
    }});
    const data = await resp.json();
    if (!data.ok) alert('Failed to update role.');
  }});
}});
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Self-contained HTML upload page (main UI)
# ---------------------------------------------------------------------------

_UPLOAD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Revolut eDavki — Import</title>
<style>
:root {
  --bg: #f5f6fa; --card: #fff; --text: #1a1a2e; --muted: #6b7280;
  --border: #e5e7eb; --blue: #4285f4; --green: #16a34a; --red: #dc2626;
  --hover: #f9fafb;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f172a; --card: #1e293b; --text: #e2e8f0; --muted: #94a3b8;
    --border: #334155; --hover: #293548;
  }
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.5;
  min-height: 100vh; display: flex; flex-direction: column; align-items: center;
}
header {
  width: 100%; background: var(--card); border-bottom: 1px solid var(--border);
  padding: 1.25rem 2rem; display: flex; align-items: center; justify-content: space-between;
}
header h1 { font-size: 1.3rem; font-weight: 700; }
.header-right { display: flex; align-items: center; gap: 1rem; font-size: .85rem; color: var(--muted); }
.header-right a { color: var(--blue); text-decoration: none; font-weight: 600; }
main { max-width: 700px; width: 100%; padding: 2rem 1rem; display: flex; flex-direction: column; gap: 1.5rem; }
.card {
  background: var(--card); border: 1px solid var(--border); border-radius: 10px;
  padding: 1.5rem;
}
.card h2 { font-size: 1.1rem; margin-bottom: 1rem; }
.guest-banner {
  background: #fef9ec; border: 1px solid #f59e0b; border-radius: 10px;
  padding: 1rem 1.25rem; font-size: .9rem;
}
@media (prefers-color-scheme: dark) { .guest-banner { background: rgba(245,158,11,.08); } }
.drop-zone {
  border: 2px dashed var(--border); border-radius: 10px; padding: 2.5rem 1.5rem;
  text-align: center; cursor: pointer; transition: all 0.15s ease;
  position: relative;
}
.drop-zone:hover, .drop-zone.dragover { border-color: var(--blue); background: rgba(66,133,244,0.04); }
.drop-zone .icon { font-size: 2.5rem; margin-bottom: 0.5rem; }
.drop-zone .label { font-size: 0.95rem; color: var(--muted); }
.drop-zone .label strong { color: var(--blue); }
.drop-zone .hint { font-size: 0.75rem; color: var(--muted); margin-top: 0.35rem; }
.drop-zone input[type="file"] { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
.file-list { margin-top: 0.75rem; display: flex; flex-direction: column; gap: 0.35rem; }
.file-item {
  display: flex; align-items: center; gap: 0.5rem; padding: 0.4rem 0.75rem;
  background: var(--bg); border-radius: 6px; font-size: 0.85rem;
}
.file-item .name { flex: 1; font-weight: 500; }
.file-item .size { color: var(--muted); font-size: 0.8rem; }
.file-item .remove { cursor: pointer; color: var(--red); font-weight: 700; padding: 0 0.25rem; border: none; background: none; font-size: 1rem; }
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 0.5rem;
  padding: 0.6rem 1.5rem; border-radius: 8px; font-size: 0.9rem; font-weight: 600;
  cursor: pointer; border: none; transition: all 0.15s ease; text-decoration: none;
}
.btn-primary { background: var(--blue); color: #fff; }
.btn-primary:hover { opacity: 0.9; }
.btn-primary:disabled { opacity: 0.4; cursor: default; }
.btn-secondary { background: var(--bg); color: var(--text); border: 1px solid var(--border); }
.btn-secondary:hover { background: var(--hover); }
.btn-group { display: flex; gap: 0.75rem; margin-top: 1rem; flex-wrap: wrap; }
.progress { display: none; margin-top: 1rem; }
.progress.active { display: block; }
.progress-bar { height: 4px; background: var(--border); border-radius: 4px; overflow: hidden; }
.progress-bar .fill { height: 100%; background: var(--blue); transition: width 0.3s ease; border-radius: 4px; }
.progress-label { font-size: 0.8rem; color: var(--muted); margin-top: 0.35rem; }
.results { margin-top: 1rem; display: none; }
.results.active { display: block; }
.result-item {
  display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem;
  border-bottom: 1px solid var(--border); font-size: 0.85rem;
}
.result-item:last-child { border-bottom: none; }
.result-item .status { font-size: 1.2rem; }
.result-item .info { flex: 1; }
.result-item .info .filename { font-weight: 600; }
.result-item .info .detail { color: var(--muted); font-size: 0.8rem; }
.result-item .info .error { color: var(--red); font-size: 0.8rem; }
.status-bar {
  background: var(--card); border: 1px solid var(--border); border-radius: 10px;
  padding: 1rem 1.25rem; display: flex; align-items: center; gap: 1.25rem;
  flex-wrap: wrap; font-size: 0.85rem;
}
.status-item { display: flex; align-items: center; gap: 0.35rem; }
.status-item .num { font-weight: 700; }
.status-item .lbl { color: var(--muted); }
.actions { display: none; }
.actions.active { display: flex; gap: 0.75rem; flex-wrap: wrap; margin-top: 1rem; }
</style>
</head>
<body>

<header>
  <h1 style="font-size:1.3rem;font-weight:700;letter-spacing:-0.03em">Portfolio<span style="color:var(--blue)">.</span></h1>
  <div class="header-right" id="headerRight"></div>
</header>

<main>
  <div id="statusBar" class="status-bar" style="display:none"></div>
  <div id="guestBanner" style="display:none" class="guest-banner">
    &#128275; You're viewing the <strong>demo portfolio</strong>.
    <a href="/login" style="color:#f59e0b;font-weight:700">Log in</a> to view your own data.
  </div>
  <div id="guestReportCard" class="card" style="display:none;text-align:center;padding:2rem">
    <div style="font-size:1.05rem;font-weight:600;margin-bottom:0.5rem">Demo Portfolio</div>
    <div style="color:var(--muted);font-size:0.85rem;margin-bottom:1.25rem">Explore the portfolio dashboard with sample data.</div>
    <a class="btn btn-primary" href="/report">View Demo Report</a>
  </div>

  <div id="uploadCard" class="card">
    <h2>Upload CSV Files</h2>

    <div class="drop-zone" id="dropZone">
      <div class="icon">&#128196;</div>
      <div class="label">Drop files here or <strong>browse</strong></div>
      <div class="hint">CSV or Excel — stocks, CFD, crypto, or savings (auto-detected)</div>
      <input type="file" id="fileInput" accept=".csv,.xlsx,.xls" multiple>
    </div>

    <div id="fileList" class="file-list"></div>

    <div class="btn-group">
      <button class="btn btn-primary" id="uploadBtn" disabled>Upload &amp; Import</button>
    </div>

    <div class="progress" id="progress">
      <div class="progress-bar"><div class="fill" id="progressFill" style="width:0%"></div></div>
      <div class="progress-label" id="progressLabel">Importing...</div>
    </div>

    <div class="results" id="results"></div>

    <div class="actions" id="actions">
      <button class="btn btn-secondary" id="syncBtn">Sync Prices</button>
      <a class="btn btn-primary" href="/report" target="_blank">View Report</a>
      <button class="btn btn-secondary" id="resetBtn">Import More</button>
    </div>
  </div>
</main>

<script>
const _USER = __USER_JSON__;

(function() {
  // --- Header ---
  const hr = document.getElementById('headerRight');
  if (_USER.username) {
    let links = '<span>' + _USER.username + ' (' + _USER.role + ')</span>';
    links += ' <a href="/report">Report</a>';
    links += ' | <a href="/import">Import Wizard</a>';
    if (_USER.role === 'admin') links += ' | <a href="/admin">Admin</a>';
    links += ' | <a href="/logout">Log out</a>';
    hr.innerHTML = links;
  } else {
    hr.innerHTML = '<a href="/login">Log in</a>';
    document.getElementById('guestBanner').style.display = '';
  }

  // --- Hide upload for guests, show report link instead ---
  const isPremium = _USER.role === 'premium' || _USER.role === 'admin';
  if (!isPremium) {
    document.getElementById('uploadCard').style.display = 'none';
    document.getElementById('guestReportCard').style.display = '';
  }

  const fileInput = document.getElementById('fileInput');
  const dropZone = document.getElementById('dropZone');
  const fileList = document.getElementById('fileList');
  const uploadBtn = document.getElementById('uploadBtn');
  const progress = document.getElementById('progress');
  const progressFill = document.getElementById('progressFill');
  const progressLabel = document.getElementById('progressLabel');
  const resultsEl = document.getElementById('results');
  const actionsEl = document.getElementById('actions');
  const statusBar = document.getElementById('statusBar');
  const syncBtn = document.getElementById('syncBtn');
  const resetBtn = document.getElementById('resetBtn');

  let selectedFiles = [];

  fetch('/status').then(r=>r.json()).then(data => {
    if (data.has_data) {
      const items = [];
      items.push(`<span class="num">${data.transaction_count}</span> <span class="lbl">transactions</span>`);
      items.push(`<span class="num">${data.ticker_count}</span> <span class="lbl">tickers</span>`);
      if (data.date_range) items.push(`<span class="lbl">${data.date_range[0]} to ${data.date_range[1]}</span>`);
      if (data.asset_classes) {
        const tags = Object.entries(data.asset_classes).map(([k,v]) => k + ': ' + v).join(', ');
        items.push(`<span class="lbl">${tags}</span>`);
      }
      statusBar.innerHTML = items.map(i => `<div class="status-item">${i}</div>`).join('');
      statusBar.style.display = '';
    }
  }).catch(()=>{});

  if (!isPremium) return;

  dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
  dropZone.addEventListener('drop', e => {
    e.preventDefault(); dropZone.classList.remove('dragover'); addFiles(e.dataTransfer.files);
  });
  fileInput.addEventListener('change', () => { addFiles(fileInput.files); fileInput.value = ''; });

  function addFiles(fl) {
    for (const f of fl) {
      const ext = f.name.split('.').pop().toLowerCase();
      if (!['csv','xlsx','xls'].includes(ext)) continue;
      if (selectedFiles.some(sf => sf.name === f.name && sf.size === f.size)) continue;
      selectedFiles.push(f);
    }
    renderFileList();
  }

  function renderFileList() {
    uploadBtn.disabled = selectedFiles.length === 0;
    fileList.innerHTML = selectedFiles.map((f, i) => {
      const size = f.size < 1024 ? f.size + ' B'
        : f.size < 1048576 ? (f.size/1024).toFixed(1) + ' KB'
        : (f.size/1048576).toFixed(1) + ' MB';
      return `<div class="file-item">
        <span class="name">${esc(f.name)}</span>
        <span class="size">${size}</span>
        <button class="remove" data-idx="${i}">&times;</button>
      </div>`;
    }).join('');
    fileList.querySelectorAll('.remove').forEach(btn => {
      btn.addEventListener('click', () => { selectedFiles.splice(+btn.dataset.idx, 1); renderFileList(); });
    });
  }

  function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

  uploadBtn.addEventListener('click', async () => {
    if (!selectedFiles.length) return;
    uploadBtn.disabled = true;
    progress.classList.add('active');
    resultsEl.classList.remove('active');
    actionsEl.classList.remove('active');
    progressFill.style.width = '30%';
    progressLabel.textContent = 'Uploading ' + selectedFiles.length + ' file(s)...';
    const form = new FormData();
    selectedFiles.forEach(f => form.append('files', f));
    try {
      progressFill.style.width = '60%';
      progressLabel.textContent = 'Importing...';
      const resp = await fetch('/upload', { method: 'POST', body: form });
      const data = await resp.json();
      progressFill.style.width = '100%';
      if (data.error) { progressLabel.textContent = 'Error: ' + data.error; uploadBtn.disabled = false; return; }
      progressLabel.textContent = 'Done!';
      resultsEl.innerHTML = data.results.map(r => {
        if (r.error) return `<div class="result-item"><span class="status">&#10060;</span>
          <div class="info"><div class="filename">${esc(r.filename)}</div><div class="error">${esc(r.error)}</div></div></div>`;
        const icon = r.new > 0 ? '&#9989;' : '&#9898;';
        return `<div class="result-item"><span class="status">${icon}</span>
          <div class="info"><div class="filename">${esc(r.filename)}</div>
          <div class="detail">${r.new} new, ${r.skipped} skipped (of ${r.total} rows)</div></div></div>`;
      }).join('');
      resultsEl.classList.add('active');
      actionsEl.classList.add('active');
      selectedFiles = []; renderFileList();
    } catch (e) {
      progressFill.style.width = '100%';
      progressLabel.textContent = 'Error: ' + e.message;
      uploadBtn.disabled = false;
    }
  });

  syncBtn.addEventListener('click', async () => {
    syncBtn.disabled = true; syncBtn.textContent = 'Syncing...';
    try {
      const resp = await fetch('/sync', { method: 'POST' });
      const data = await resp.json();
      syncBtn.textContent = data.ok ? 'Synced!' : 'Error: ' + data.error;
    } catch(e) { syncBtn.textContent = 'Error'; }
    setTimeout(() => { syncBtn.textContent = 'Sync Prices'; syncBtn.disabled = false; }, 3000);
  });

  resetBtn.addEventListener('click', () => {
    resultsEl.classList.remove('active'); actionsEl.classList.remove('active');
    progress.classList.remove('active'); progressFill.style.width = '0%';
    uploadBtn.disabled = true;
  });
})();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Inline HTML: import wizard page
# ---------------------------------------------------------------------------

def _import_wizard_html() -> str:
    return r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Import Wizard — Portfolio</title>
<style>
:root {
  --bg:#0a0c10;--surface:#111520;--raised:#181e2e;--border:#1e2a3a;
  --text:#dce4f0;--muted:#556075;--subtle:#2e3a4e;
  --accent:#f59e0b;--accent-dim:rgba(245,158,11,0.12);
  --green:#34d399;--red:#f87171;--blue:#60a5fa;
  --radius:10px;--radius-sm:6px;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
     background:var(--bg);color:var(--text);min-height:100vh;
     display:flex;flex-direction:column;align-items:center;}
header{width:100%;background:var(--surface);border-bottom:1px solid var(--border);
       padding:1rem 2rem;display:flex;align-items:center;gap:1rem;}
.logo{font-size:1.1rem;font-weight:700;letter-spacing:-0.03em;text-decoration:none;color:var(--text);}
.logo span{color:var(--accent);}
.back{font-size:.82rem;color:var(--muted);text-decoration:none;margin-left:auto;}
.back:hover{color:var(--text);}
main{width:100%;max-width:780px;padding:2rem 1rem;display:flex;flex-direction:column;gap:1.5rem;}

/* Progress steps */
.steps{display:flex;align-items:center;gap:0;margin-bottom:.5rem;}
.step{display:flex;align-items:center;gap:.5rem;font-size:.78rem;font-weight:600;
      color:var(--muted);padding:.4rem .75rem;border-radius:20px;}
.step.active{color:var(--accent);}
.step.done{color:var(--green);}
.step-num{width:20px;height:20px;border-radius:50%;border:2px solid currentColor;
          display:flex;align-items:center;justify-content:center;font-size:.7rem;flex-shrink:0;}
.step-sep{flex:1;height:1px;background:var(--border);margin:0 .25rem;max-width:40px;}

/* Cards */
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:1.5rem;}
.card h2{font-size:1rem;font-weight:600;margin-bottom:1rem;}

/* Drop zone */
.drop-zone{border:2px dashed var(--border);border-radius:var(--radius);padding:2.5rem 1.5rem;
           text-align:center;cursor:pointer;transition:all .15s;position:relative;}
.drop-zone:hover,.drop-zone.dragover{border-color:var(--accent);background:var(--accent-dim);}
.drop-zone .icon{font-size:2.2rem;margin-bottom:.5rem;}
.drop-zone .lbl{font-size:.9rem;color:var(--muted);}
.drop-zone .lbl strong{color:var(--accent);}
.drop-zone .hint{font-size:.72rem;color:var(--muted);margin-top:.3rem;}
.drop-zone input[type=file]{position:absolute;inset:0;opacity:0;cursor:pointer;}
.chosen-file{margin-top:.75rem;font-size:.83rem;font-weight:500;color:var(--text);}

/* Buttons */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:.4rem;
     padding:.5rem 1.25rem;border-radius:var(--radius-sm);font-size:.85rem;font-weight:600;
     cursor:pointer;border:none;transition:opacity .12s;font-family:inherit;}
.btn-primary{background:var(--accent);color:#000;}
.btn-primary:hover{opacity:.88;}
.btn-primary:disabled{opacity:.35;cursor:default;}
.btn-secondary{background:transparent;color:var(--muted);border:1px solid var(--border);}
.btn-secondary:hover{background:var(--raised);color:var(--text);}
.btn-group{display:flex;gap:.6rem;margin-top:1.25rem;flex-wrap:wrap;}

/* Asset class toggles */
.ac-toggles{display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:1.25rem;}
.ac-btn{padding:.3rem .85rem;border-radius:12px;font-size:.75rem;font-weight:700;
        cursor:pointer;border:1px solid var(--border);background:transparent;
        color:var(--muted);font-family:inherit;transition:all .12s;}
.ac-btn.active{background:var(--accent-dim);color:var(--accent);border-color:var(--accent);}

/* Preview table */
.preview-wrap{overflow-x:auto;margin-bottom:1.25rem;}
.preview-table{border-collapse:collapse;font-size:.75rem;width:100%;}
.preview-table th,.preview-table td{padding:.3rem .55rem;text-align:left;border-bottom:1px solid var(--border);white-space:nowrap;}
.preview-table thead th{font-weight:600;color:var(--accent);font-size:.68rem;text-transform:uppercase;letter-spacing:.05em;}

/* Mapping table */
.map-table{width:100%;border-collapse:collapse;font-size:.83rem;}
.map-table td{padding:.45rem .5rem;border-bottom:1px solid var(--border);vertical-align:middle;}
.map-table td:first-child{width:38%;font-weight:500;}
.map-table td:nth-child(2){width:10%;text-align:center;}
.map-table select{background:var(--raised);border:1px solid var(--border);border-radius:var(--radius-sm);
                  color:var(--text);font-family:inherit;font-size:.8rem;padding:.3rem .5rem;width:100%;}
.map-table select:focus{outline:none;border-color:var(--accent);}
.req-badge{font-size:.62rem;font-weight:700;padding:.1rem .4rem;border-radius:8px;
           background:rgba(248,113,113,.15);color:var(--red);}
.opt-badge{font-size:.62rem;font-weight:700;padding:.1rem .4rem;border-radius:8px;
           background:var(--raised);color:var(--muted);}

/* Step 3 summary */
.summary-list{display:flex;flex-direction:column;gap:.4rem;font-size:.83rem;}
.summary-row{display:flex;gap:.75rem;}
.summary-lbl{color:var(--muted);width:140px;flex-shrink:0;font-size:.75rem;font-weight:600;
             text-transform:uppercase;letter-spacing:.05em;}
.summary-val{color:var(--text);}

/* Error / success */
.error-msg{color:var(--red);font-size:.82rem;margin-top:.6rem;}
.success-box{background:rgba(52,211,153,.08);border:1px solid rgba(52,211,153,.25);
             border-radius:var(--radius-sm);padding:1rem;text-align:center;}
.success-box .big{font-size:1.1rem;font-weight:700;color:var(--green);margin-bottom:.4rem;}
.success-box .sub{font-size:.82rem;color:var(--muted);}
.success-links{display:flex;gap:.6rem;justify-content:center;margin-top:1rem;flex-wrap:wrap;}

/* Spinner */
@keyframes spin{to{transform:rotate(360deg)}}
.spin{display:inline-block;width:.85em;height:.85em;border:2px solid rgba(0,0,0,.3);
      border-top-color:#000;border-radius:50%;animation:spin .6s linear infinite;}
</style>
</head>
<body>
<header>
  <a class="logo" href="/">Portfolio<span>.</span></a>
  <a class="back" href="/">&#8592; Back</a>
</header>

<main>
  <!-- Progress bar -->
  <div class="steps" id="steps">
    <div class="step active" id="s1"><span class="step-num">1</span><span>Upload</span></div>
    <div class="step-sep"></div>
    <div class="step" id="s2"><span class="step-num">2</span><span>Map Columns</span></div>
    <div class="step-sep"></div>
    <div class="step" id="s3"><span class="step-num">3</span><span>Import</span></div>
  </div>

  <!-- Step 1: Upload -->
  <div class="card" id="step1">
    <h2>Upload CSV file</h2>
    <div class="drop-zone" id="dropZone">
      <div class="icon">&#128196;</div>
      <div class="lbl">Drop CSV here or <strong>browse</strong></div>
      <div class="hint">CSV only &mdash; comma or semicolon separated</div>
      <input type="file" id="fileInput" accept=".csv">
    </div>
    <div class="chosen-file" id="chosenFile"></div>
    <div class="error-msg" id="step1Err"></div>
    <div class="btn-group">
      <button class="btn btn-primary" id="previewBtn" disabled>Next: Map Columns</button>
    </div>
  </div>

  <!-- Step 2: Map Columns (hidden initially) -->
  <div class="card" id="step2" style="display:none">
    <h2>Map columns</h2>

    <div style="font-size:.78rem;color:var(--muted);margin-bottom:.75rem">
      Asset class: select what type of transactions this file contains.
    </div>
    <div class="ac-toggles" id="acToggles">
      <button class="ac-btn" data-ac="stock">Stock</button>
      <button class="ac-btn" data-ac="cfd">CFD</button>
      <button class="ac-btn" data-ac="crypto">Crypto</button>
      <button class="ac-btn" data-ac="savings">Savings</button>
    </div>

    <div style="font-size:.8rem;font-weight:600;color:var(--muted);margin-bottom:.4rem">CSV preview (first 5 rows)</div>
    <div class="preview-wrap"><table class="preview-table" id="previewTable"></table></div>

    <div style="font-size:.8rem;font-weight:600;color:var(--muted);margin-bottom:.4rem">Column mapping</div>
    <table class="map-table" id="mapTable"></table>

    <div class="error-msg" id="step2Err"></div>
    <div class="btn-group">
      <button class="btn btn-secondary" id="backBtn1">&#8592; Back</button>
      <button class="btn btn-primary" id="nextBtn2" disabled>Next: Review &amp; Import</button>
    </div>
  </div>

  <!-- Step 3: Review & Import (hidden initially) -->
  <div class="card" id="step3" style="display:none">
    <h2>Review &amp; import</h2>
    <div class="summary-list" id="summaryList"></div>
    <div class="error-msg" id="step3Err"></div>
    <div id="successBox" style="display:none"></div>
    <div class="btn-group" id="step3Btns">
      <button class="btn btn-secondary" id="backBtn2">&#8592; Back</button>
      <button class="btn btn-primary" id="importBtn">Import</button>
    </div>
  </div>
</main>

<script>
const DB_FIELDS = {
  stock:   { required: ["date","type"], optional: ["ticker","quantity","price_per_share","total_amount","currency","fx_rate"] },
  cfd:     { required: ["date","type","ticker"], optional: ["quantity","price_per_share","total_amount","currency","fx_rate"] },
  crypto:  { required: ["date","type","ticker"], optional: ["quantity","price_per_share","total_amount"] },
  savings: { required: ["date","type"], optional: ["ticker","quantity","price_per_share","total_amount","fx_rate"] },
};
const FIELD_LABELS = {
  date:"Date", ticker:"Ticker / Symbol", type:"Transaction Type",
  quantity:"Quantity", price_per_share:"Price per Share",
  total_amount:"Total Amount", currency:"Currency", fx_rate:"FX Rate",
};
const FIELD_ALIASES = {
  date:            ["date","started date","datevalue","settlementdate","started_date"],
  ticker:          ["ticker","symbol","financialinstrument"],
  type:            ["type","transactiontypename","transaction type"],
  quantity:        ["quantity","volume","volumevalue","quantity of shares","qty"],
  price_per_share: ["price per share","price","pricevalue","price_per_share"],
  total_amount:    ["total amount","amount","value","total_amount"],
  currency:        ["currency","ccy"],
  fx_rate:         ["fx rate","fxrate","fx_rate","exchange rate"],
};

let _headers = [], _rows = [], _filename = '', _rowCount = 0;
let _assetClass = null;

function esc(s) { const d = document.createElement('div'); d.textContent = String(s); return d.innerHTML; }

// --- Step indicators ---
function setStep(n) {
  [1,2,3].forEach(i => {
    const el = document.getElementById('s'+i);
    el.classList.remove('active','done');
    if (i < n) el.classList.add('done');
    else if (i === n) el.classList.add('active');
  });
}

// --- File pick ---
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const chosenFile = document.getElementById('chosenFile');
const previewBtn = document.getElementById('previewBtn');
const step1Err = document.getElementById('step1Err');

let _selectedFile = null;

dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault(); dropZone.classList.remove('dragover');
  const f = e.dataTransfer.files[0];
  if (f) setFile(f);
});
fileInput.addEventListener('change', () => { if (fileInput.files[0]) setFile(fileInput.files[0]); fileInput.value=''; });

function setFile(f) {
  if (!f.name.toLowerCase().endsWith('.csv')) {
    step1Err.textContent = 'Only CSV files are supported.'; return;
  }
  _selectedFile = f;
  chosenFile.textContent = f.name + ' (' + (f.size > 1048576 ? (f.size/1048576).toFixed(1)+' MB' : Math.ceil(f.size/1024)+' KB') + ')';
  previewBtn.disabled = false;
  step1Err.textContent = '';
}

// --- Step 1 → 2 ---
previewBtn.addEventListener('click', async () => {
  if (!_selectedFile) return;
  previewBtn.disabled = true;
  previewBtn.innerHTML = '<span class="spin"></span> Loading...';
  step1Err.textContent = '';
  const form = new FormData();
  form.append('file', _selectedFile);
  try {
    const resp = await fetch('/import/preview', { method: 'POST', body: form });
    const data = await resp.json();
    if (data.error) { step1Err.textContent = data.error; previewBtn.disabled = false; previewBtn.textContent = 'Next: Map Columns'; return; }
    _headers = data.headers;
    _rows = data.rows;
    _rowCount = data.row_count;
    _filename = data.filename;
    showStep2(data.detected_asset_class);
  } catch(e) {
    step1Err.textContent = 'Network error: ' + e.message;
    previewBtn.disabled = false;
    previewBtn.textContent = 'Next: Map Columns';
  }
});

// --- Step 2 setup ---
function showStep2(detectedClass) {
  document.getElementById('step1').style.display = 'none';
  document.getElementById('step2').style.display = '';
  setStep(2);

  // Asset class buttons
  _assetClass = detectedClass || 'stock';
  document.querySelectorAll('.ac-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.ac === _assetClass);
    btn.addEventListener('click', () => {
      _assetClass = btn.dataset.ac;
      document.querySelectorAll('.ac-btn').forEach(b => b.classList.toggle('active', b.dataset.ac === _assetClass));
      buildMapTable();
      validateStep2();
    });
  });

  buildPreviewTable();
  buildMapTable();
  validateStep2();
}

function buildPreviewTable() {
  const t = document.getElementById('previewTable');
  let html = '<thead><tr>' + _headers.map(h => '<th>'+esc(h)+'</th>').join('') + '</tr></thead><tbody>';
  _rows.forEach(row => {
    html += '<tr>' + _headers.map((_, i) => '<td>'+esc(row[i] !== undefined ? row[i] : '')+'</td>').join('') + '</tr>';
  });
  t.innerHTML = html + '</tbody>';
}

function bestMatch(field, headers) {
  const aliases = FIELD_ALIASES[field] || [];
  const hLower = headers.map(h => h.toLowerCase().trim());
  for (const alias of aliases) {
    const idx = hLower.indexOf(alias.toLowerCase());
    if (idx !== -1) return headers[idx];
  }
  return '';
}

function buildMapTable() {
  const ac = _assetClass || 'stock';
  const fields = DB_FIELDS[ac];
  const all = [...fields.required, ...fields.optional];
  const t = document.getElementById('mapTable');
  let html = '';
  all.forEach(field => {
    const isReq = fields.required.includes(field);
    const match = bestMatch(field, _headers);
    const opts = ['<option value="">— skip —</option>'] + _headers.map(h =>
      `<option value="${esc(h)}" ${h === match ? 'selected' : ''}>${esc(h)}</option>`
    );
    html += `<tr>
      <td>${FIELD_LABELS[field] || field}</td>
      <td>${isReq ? '<span class="req-badge">Required</span>' : '<span class="opt-badge">Optional</span>'}</td>
      <td><select data-field="${field}" data-req="${isReq ? '1' : '0'}">${opts.join('')}</select></td>
    </tr>`;
  });
  t.innerHTML = html;
  t.querySelectorAll('select').forEach(sel => sel.addEventListener('change', validateStep2));
}

function validateStep2() {
  const ac = _assetClass || 'stock';
  const required = DB_FIELDS[ac].required;
  const table = document.getElementById('mapTable');
  let ok = true;
  required.forEach(field => {
    const sel = table.querySelector(`select[data-field="${field}"]`);
    if (!sel || !sel.value) ok = false;
  });
  document.getElementById('nextBtn2').disabled = !ok;
  document.getElementById('step2Err').textContent = '';
}

// --- Step 2 → 3 ---
document.getElementById('nextBtn2').addEventListener('click', () => {
  showStep3();
});

function collectMapping() {
  const mapping = {};
  document.querySelectorAll('#mapTable select').forEach(sel => {
    if (sel.value) mapping[sel.dataset.field] = sel.value;
  });
  return mapping;
}

function showStep3() {
  document.getElementById('step2').style.display = 'none';
  document.getElementById('step3').style.display = '';
  setStep(3);

  const mapping = collectMapping();
  const mapLines = Object.entries(mapping).map(([k,v]) =>
    `<div class="summary-row"><span class="summary-lbl">${esc(FIELD_LABELS[k]||k)}</span><span class="summary-val">&#8594; ${esc(v)}</span></div>`
  ).join('');

  document.getElementById('summaryList').innerHTML = `
    <div class="summary-row"><span class="summary-lbl">File</span><span class="summary-val">${esc(_filename)}</span></div>
    <div class="summary-row"><span class="summary-lbl">Rows</span><span class="summary-val">${_rowCount}</span></div>
    <div class="summary-row"><span class="summary-lbl">Asset class</span><span class="summary-val" style="text-transform:capitalize">${esc(_assetClass)}</span></div>
    <div class="summary-row" style="margin-top:.5rem"><span class="summary-lbl" style="color:var(--text)">Column mapping</span></div>
    ${mapLines}
  `;
  document.getElementById('step3Err').textContent = '';
  document.getElementById('successBox').style.display = 'none';
  document.getElementById('step3Btns').style.display = '';
}

// --- Back buttons ---
document.getElementById('backBtn1').addEventListener('click', () => {
  document.getElementById('step2').style.display = 'none';
  document.getElementById('step1').style.display = '';
  previewBtn.disabled = false;
  previewBtn.textContent = 'Next: Map Columns';
  setStep(1);
});
document.getElementById('backBtn2').addEventListener('click', () => {
  document.getElementById('step3').style.display = 'none';
  document.getElementById('step2').style.display = '';
  setStep(2);
});

// --- Import ---
document.getElementById('importBtn').addEventListener('click', async () => {
  const btn = document.getElementById('importBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spin"></span> Importing...';
  document.getElementById('step3Err').textContent = '';

  const mapping = collectMapping();
  try {
    const resp = await fetch('/import/run', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ asset_class: _assetClass, mapping, filename: _filename }),
    });
    const data = await resp.json();
    if (data.error) {
      document.getElementById('step3Err').textContent = data.error;
      btn.disabled = false; btn.textContent = 'Import';
      return;
    }
    document.getElementById('step3Btns').style.display = 'none';
    const box = document.getElementById('successBox');
    box.style.display = '';
    box.innerHTML = `<div class="success-box">
      <div class="big">&#10003; Import complete</div>
      <div class="sub">${data.new} new &nbsp;&bull;&nbsp; ${data.skipped} skipped &nbsp;&bull;&nbsp; ${data.total} total rows</div>
      <div class="success-links">
        <a class="btn btn-primary" href="/report">View Report</a>
        <button class="btn btn-secondary" onclick="location.href='/import'">Import Another</button>
      </div>
    </div>`;
  } catch(e) {
    document.getElementById('step3Err').textContent = 'Network error: ' + e.message;
    btn.disabled = false; btn.textContent = 'Import';
  }
});
</script>
</body>
</html>"""
