"""Shared fixtures for Playwright E2E tests.

Starts a real web server in a daemon thread, bootstraps users + test data,
and provides authenticated browser page fixtures for desktop and mobile.
"""

import os
import shutil
import socket
import threading
import time
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError

import pytest

# ---------------------------------------------------------------------------
# Project root (for locating example CSVs and demo DB)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Viewport constants
# ---------------------------------------------------------------------------
DESKTOP_VIEWPORT = {"width": 1280, "height": 720}
MOBILE_VIEWPORT = {"width": 390, "height": 844}


# ---------------------------------------------------------------------------
# Session-scoped: temp data directory
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def tmp_data_dir(tmp_path_factory):
    """Create a temp directory tree mimicking the production data layout."""
    base = tmp_path_factory.mktemp("e2e_data")
    (base / "_system").mkdir()
    (base / "_demo").mkdir()
    (base / "admin").mkdir()
    (base / "premium").mkdir()

    # Copy the demo portfolio DB so guests see real data
    demo_src = PROJECT_ROOT / "data" / "_demo" / "portfolio.db"
    if demo_src.exists():
        shutil.copy2(demo_src, base / "_demo" / "portfolio.db")

    return base


# ---------------------------------------------------------------------------
# Session-scoped: start the web server once
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def server_url(tmp_data_dir):
    """Boot the app on a random port and yield the base URL."""

    # Must set env var BEFORE importing src modules that cache it at import time
    os.environ["REVOLUT_DATA_DIR"] = str(tmp_data_dir)

    # Now safe to import app modules
    import src.web as web_module
    from src.web import UploadHandler
    from src.users import (
        get_users_db, ensure_bootstrap_admin, create_user, accept_invite,
    )
    from src.db import get_connection
    from src.importer import import_csv
    from http.server import ThreadingHTTPServer

    # Monkey-patch the module-level constants that were cached before env was set
    web_module.DATA_DIR = Path(tmp_data_dir)
    web_module.DEMO_DB = Path(tmp_data_dir) / "_demo" / "portfolio.db"

    # ---- Bootstrap users ----
    users_conn = get_users_db()

    # Admin user
    ensure_bootstrap_admin("admin@test.com", "adminpass", conn=users_conn)

    # Premium user
    user, raw_token = create_user("premium@test.com", role="premium", conn=users_conn)
    accept_invite(raw_token, "premiumpass", conn=users_conn)
    users_conn.close()

    # ---- Import test data into premium user's portfolio DB ----
    premium_db = tmp_data_dir / "premium" / "portfolio.db"
    conn = get_connection(db_path=premium_db)
    for csv_name in [
        "sample_transactions.csv",
        "crypto.csv",
        "cfds.csv",
        "savings.csv",
    ]:
        csv_path = PROJECT_ROOT / "examples" / csv_name
        if csv_path.exists():
            import_csv(conn, str(csv_path))
    conn.close()

    # ---- Find a free port ----
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    # ---- Start server in daemon thread ----
    server = ThreadingHTTPServer(("127.0.0.1", port), UploadHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"

    # ---- Wait until server is ready ----
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            urlopen(f"{base_url}/login", timeout=1)
            break
        except (URLError, ConnectionError, OSError):
            time.sleep(0.1)
    else:
        raise RuntimeError(f"Server did not start within 10 s on {base_url}")

    yield base_url

    server.shutdown()


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def admin_credentials():
    return ("admin", "adminpass")


@pytest.fixture(scope="session")
def premium_credentials():
    return ("premium", "premiumpass")


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------
def _login(page, server_url, username, password):
    """Log in via the web form and wait for redirect to /."""
    page.goto(f"{server_url}/login")
    page.fill('input[name="username"]', username)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')
    page.wait_for_url(f"{server_url}/", timeout=5000)


# ---------------------------------------------------------------------------
# Desktop page fixtures (function-scoped: fresh context per test)
# ---------------------------------------------------------------------------
@pytest.fixture()
def desktop_page(browser, server_url):
    """Unauthenticated desktop page."""
    context = browser.new_context(viewport=DESKTOP_VIEWPORT)
    page = context.new_page()
    yield page
    context.close()


@pytest.fixture()
def premium_desktop_page(browser, server_url, premium_credentials):
    """Authenticated premium-user desktop page."""
    context = browser.new_context(viewport=DESKTOP_VIEWPORT)
    page = context.new_page()
    _login(page, server_url, *premium_credentials)
    yield page
    context.close()


@pytest.fixture()
def admin_desktop_page(browser, server_url, admin_credentials):
    """Authenticated admin-user desktop page."""
    context = browser.new_context(viewport=DESKTOP_VIEWPORT)
    page = context.new_page()
    _login(page, server_url, *admin_credentials)
    yield page
    context.close()


# ---------------------------------------------------------------------------
# Mobile page fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def mobile_page(browser, server_url):
    """Unauthenticated mobile page."""
    context = browser.new_context(
        viewport=MOBILE_VIEWPORT,
        has_touch=True,
        is_mobile=True,
    )
    page = context.new_page()
    yield page
    context.close()


@pytest.fixture()
def premium_mobile_page(browser, server_url, premium_credentials):
    """Authenticated premium-user mobile page."""
    context = browser.new_context(
        viewport=MOBILE_VIEWPORT,
        has_touch=True,
        is_mobile=True,
    )
    page = context.new_page()
    _login(page, server_url, *premium_credentials)
    yield page
    context.close()


@pytest.fixture()
def admin_mobile_page(browser, server_url, admin_credentials):
    """Authenticated admin-user mobile page."""
    context = browser.new_context(
        viewport=MOBILE_VIEWPORT,
        has_touch=True,
        is_mobile=True,
    )
    page = context.new_page()
    _login(page, server_url, *admin_credentials)
    yield page
    context.close()
