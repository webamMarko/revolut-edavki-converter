"""HTTP server setup, routing, and middleware."""

import os
import signal
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from .templates import TEMPLATES_DIR
from . import auth, admin, portfolio, api, exports, import_wizard, tickets

FORCE_HTTPS = os.environ.get("FORCE_HTTPS", "").lower() in ("true", "1", "yes")
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8080")


class UploadHandler(BaseHTTPRequestHandler):
    """HTTP request handler with routing to modular endpoints."""

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
        """Add security headers to response."""
        if FORCE_HTTPS:
            self.send_header("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")

    def _read_body(self, length: Optional[int] = None) -> bytes:
        """Read request body."""
        if length is None:
            length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length)

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def do_GET(self):
        if self._enforce_https():
            return
        path = urlparse(self.path).path

        # Admin routes
        if path == "/admin/audit-log":
            admin.serve_audit_log(self)
        elif path == "/api/audit-events":
            admin.api_audit_events(self)
        elif path == "/admin":
            admin.serve_admin_page(self)
        elif path == "/admin/users":
            admin.serve_admin_users_json(self)

        # Auth routes
        elif path == "/login":
            auth.serve_login_page(self)
        elif path == "/logout":
            auth.handle_logout(self)
        elif path.startswith("/login/magic/"):
            token = path[len("/login/magic/"):]
            auth.handle_magic_login(self, token)
        elif path.startswith("/invite/"):
            token = path[len("/invite/"):]
            auth.serve_invite_page(self, token)
        elif path == "/reset-password":
            auth.serve_reset_password_page(self)
        elif path.startswith("/reset-password/"):
            token = path[len("/reset-password/"):]
            auth.serve_reset_password_confirm_page(self, token)
        elif path == "/account":
            auth.serve_account_page(self)

        # Ticket routes
        elif path == "/tickets":
            tickets.serve_tickets_page(self)
        elif path.startswith("/tickets/"):
            # Extract ticket ID from path
            try:
                ticket_id = int(path.split("/")[2])
                tickets.serve_ticket_detail(self, ticket_id)
            except (IndexError, ValueError):
                auth.serve_error_page(self, 404, "Ticket not found")

        # Portfolio routes
        elif path == "/":
            portfolio.serve_upload_page(self)
        elif path == "/status":
            portfolio.serve_status(self)
        elif path == "/report":
            portfolio.serve_report(self)
        elif path == "/import":
            import_wizard.serve_import_wizard(self)
        elif path == "/export/edavki":
            exports.handle_export_edavki(self)
        elif path == "/export/fifo-csv":
            exports.handle_export_fifo_csv(self)
        elif path == "/export/tax-pdf":
            exports.handle_export_tax_pdf(self)
        elif path == "/export/doh-div":
            exports.handle_export_doh_div(self)
        elif path == "/settings":
            portfolio.serve_settings_page(self)
        elif path == "/pricing":
            portfolio.serve_pricing_page(self)
        elif path == "/cofounder":
            tickets.serve_cofounder_page(self)

        # API routes
        elif path == "/api/portfolios":
            api.api_get_portfolios(self)
        elif path == "/api/dividend-summary":
            api.handle_dividend_summary(self)
        elif path == "/api/email-preferences":
            api.api_get_email_preferences(self)
        elif path == "/api/edavki-filed":
            api.api_get_edavki_filed(self)
        elif path.startswith("/api/analytics/"):
            scope = path[len("/api/analytics/"):]
            api.api_get_analytics(self, scope)
        elif path == "/api/notes":
            api.api_list_notes(self)
        elif path == "/api/onboarding-status":
            api.api_onboarding_status(self)
        elif path == "/api/shares":
            api.api_list_shares(self)
        elif path == "/api/goals":
            api.api_list_goals(self)
        elif path.startswith("/api/goals/") and path.endswith("/projection"):
            goal_id = path[len("/api/goals/"):-len("/projection")]
            if goal_id.isdigit():
                api.api_goal_projection(self, int(goal_id))
            else:
                self.send_error(404)
        elif path.startswith("/api/goals/"):
            goal_id = path[len("/api/goals/"):]
            if goal_id.isdigit():
                api.api_get_goal(self, int(goal_id))
            else:
                self.send_error(404)

        # Shared portfolio
        elif path.startswith("/s/"):
            token = path[3:]
            api.serve_shared_portfolio(self, token)

        # Static files
        elif path == "/static/common.css":
            self._serve_static_css()
        elif path == "/static/logo.png":
            self._serve_logo()
        elif path == "/manifest.json":
            self._serve_manifest()
        elif path == "/sw.js":
            self._serve_service_worker()
        elif path.startswith("/static/icons/"):
            icon_name = path[len("/static/icons/"):]
            self._serve_icon(icon_name)
        elif path == "/robots.txt":
            self._serve_robots_txt()
        elif path == "/sitemap.xml":
            self._serve_sitemap_xml()

        else:
            self.send_error(404)

    def do_POST(self):
        if self._enforce_https():
            return
        path = urlparse(self.path).path

        # Auth routes
        if path == "/login":
            auth.handle_login(self)
        elif path.startswith("/invite/"):
            token = path[len("/invite/"):]
            auth.handle_invite_accept(self, token)
        elif path == "/reset-password":
            auth.handle_reset_password_request(self)
        elif path.startswith("/reset-password/"):
            token = path[len("/reset-password/"):]
            auth.handle_reset_password_confirm(self, token)
        elif path == "/account/change-password":
            auth.handle_change_password(self)
        elif path == "/account/delete":
            auth.handle_delete_account(self)

        # Ticket routes
        elif path == "/tickets":
            tickets.handle_create_ticket(self)
        elif path == "/cofounder/checkout":
            tickets.handle_cofounder_checkout(self)
        elif path.endswith("/comments"):
            # /tickets/{id}/comments
            try:
                ticket_id = int(path.split("/")[2])
                tickets.handle_add_comment(self, ticket_id)
            except (IndexError, ValueError):
                auth.serve_error_page(self, 404, "Ticket not found")
        elif path.endswith("/status"):
            # /tickets/{id}/status
            try:
                ticket_id = int(path.split("/")[2])
                tickets.handle_update_status(self, ticket_id)
            except (IndexError, ValueError):
                auth.serve_error_page(self, 404, "Ticket not found")

        # Admin routes
        elif path == "/admin/users":
            admin.handle_admin_create_user(self)
        elif path.startswith("/admin/users/") and path.endswith("/role"):
            parts = path.split("/")
            # /admin/users/{id}/role
            if len(parts) == 5:
                admin.handle_admin_set_role(self, parts[3])
        elif path == "/admin/settings":
            admin.handle_admin_settings(self)
        elif path == "/webhook/stripe":
            admin.handle_stripe_webhook(self)

        # Portfolio routes
        elif path == "/upload":
            portfolio.handle_upload(self)
        elif path == "/sync":
            portfolio.handle_sync(self)
        elif path == "/import/preview":
            import_wizard.handle_import_preview(self)
        elif path == "/import/validate":
            import_wizard.handle_import_validate(self)
        elif path == "/import/run":
            import_wizard.handle_import_run(self)

        # API routes
        elif path == "/api/portfolios":
            api.api_create_portfolio(self)
        elif path == "/api/switch-portfolio":
            api.api_switch_portfolio(self)
        elif path == "/api/notes":
            api.api_create_note(self)
        elif path == "/api/onboarding-complete":
            api.api_onboarding_complete(self)
        elif path == "/api/demo-toggle":
            api.api_demo_toggle(self)
        elif path == "/api/email-preferences":
            api.api_save_email_preferences(self)
        elif path == "/api/edavki-filed":
            api.api_save_edavki_filed(self)
        elif path == "/api/shares":
            api.api_create_share(self)
        elif path.startswith("/api/shares/") and path.endswith("/delete"):
            share_id = path[len("/api/shares/"):-len("/delete")]
            api.api_delete_share(self, share_id)
        elif path == "/api/goals":
            api.api_create_goal(self)
        elif path.startswith("/api/goals/") and path.endswith("/delete"):
            goal_id = path[len("/api/goals/"):-len("/delete")]
            if goal_id.isdigit():
                api.api_delete_goal(self, int(goal_id))
            else:
                self.send_error(404)

        else:
            self.send_error(404)

    def do_PUT(self):
        if self._enforce_https():
            return
        path = urlparse(self.path).path
        parts = path.split("/")
        # /api/portfolios/<id>
        if len(parts) == 4 and parts[1] == "api" and parts[2] == "portfolios" and parts[3].isdigit():
            api.api_update_portfolio(self, int(parts[3]))
        # /api/notes/<id>
        elif len(parts) == 4 and parts[1] == "api" and parts[2] == "notes" and parts[3].isdigit():
            api.api_update_note(self, int(parts[3]))
        # /api/goals/<id>
        elif len(parts) == 4 and parts[1] == "api" and parts[2] == "goals" and parts[3].isdigit():
            api.api_update_goal(self, int(parts[3]))
        else:
            self.send_error(404)

    def do_DELETE(self):
        if self._enforce_https():
            return
        path = urlparse(self.path).path
        parts = path.split("/")
        # /api/portfolios/<id>
        if len(parts) == 4 and parts[1] == "api" and parts[2] == "portfolios" and parts[3].isdigit():
            api.api_delete_portfolio(self, int(parts[3]))
        # /api/notes/<id>
        elif len(parts) == 4 and parts[1] == "api" and parts[2] == "notes" and parts[3].isdigit():
            api.api_delete_note(self, int(parts[3]))
        # /api/goals/<id>
        elif len(parts) == 4 and parts[1] == "api" and parts[2] == "goals" and parts[3].isdigit():
            api.api_delete_goal(self, int(parts[3]))
        else:
            self.send_error(404)

    # ------------------------------------------------------------------
    # Static file serving
    # ------------------------------------------------------------------

    def _serve_static_css(self):
        """Serve common.css with caching headers."""
        css_path = TEMPLATES_DIR / "assets" / "common.css"
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

    def _serve_manifest(self):
        """Serve PWA manifest.json."""
        manifest_path = TEMPLATES_DIR / "assets" / "manifest.json"
        try:
            with open(manifest_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/manifest+json; charset=utf-8")
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404)

    def _serve_service_worker(self):
        """Serve PWA service worker (sw.js)."""
        sw_path = TEMPLATES_DIR / "assets" / "sw.js"
        try:
            with open(sw_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            # Service workers should not be cached aggressively to allow quick updates
            self.send_header("Cache-Control", "no-cache, must-revalidate")
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404)

    def _serve_icon(self, icon_name):
        """Serve PWA icon files."""
        # Validate icon name to prevent directory traversal
        allowed_icons = {
            "icon-192.png",
            "icon-512.png",
            "apple-touch-icon.png",
            "favicon-32.png",
            "favicon-16.png",
            "favicon.ico",
        }
        if icon_name not in allowed_icons:
            self.send_error(404)
            return

        icon_path = TEMPLATES_DIR / "assets" / "icons" / icon_name
        try:
            with open(icon_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            # Set correct content-type based on file extension
            content_type = "image/x-icon" if icon_name.endswith(".ico") else "image/png"
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "public, max-age=86400")  # 24 hours
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404)

    def _serve_logo(self):
        """Serve the WealthEagle logo."""
        logo_path = TEMPLATES_DIR / "assets" / "logo.png"
        try:
            with open(logo_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "public, max-age=86400")  # 24 hours
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404)

    def _serve_robots_txt(self):
        """Serve robots.txt."""
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
        """Serve sitemap.xml."""
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
    watch_dirs = [
        Path(__file__).resolve().parent.parent,                    # src/
        Path(__file__).resolve().parent.parent / "templates",      # src/templates/
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
