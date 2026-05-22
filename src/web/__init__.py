"""Web UI module for portfolio management.

Modular structure:
- templates.py — Jinja2 environment and response helpers
- auth.py — authentication and session management
- admin.py — user management and admin features
- portfolio.py — portfolio operations (import, sync, reports)
- api.py — JSON API endpoints
- server.py — HTTP server and request routing
"""

from .server import start_server, UploadHandler

__all__ = ["start_server", "UploadHandler"]
