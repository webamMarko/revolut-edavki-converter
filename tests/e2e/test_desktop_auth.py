"""Desktop authentication and access control tests."""

from conftest import _login


class TestLoginPage:
    def test_login_page_renders(self, desktop_page, server_url):
        desktop_page.goto(f"{server_url}/login")
        assert desktop_page.locator('input[name="username"]').is_visible()
        assert desktop_page.locator('input[name="password"]').is_visible()
        assert desktop_page.locator('button[type="submit"]').is_visible()

    def test_login_with_valid_credentials(
        self, desktop_page, server_url, premium_credentials
    ):
        _login(desktop_page, server_url, *premium_credentials)
        # Should be on the home page now
        assert desktop_page.url.rstrip("/") == server_url.rstrip("/") or \
               desktop_page.url == f"{server_url}/"
        # Header shows the username
        header = desktop_page.locator("#headerRight")
        assert "premium" in header.text_content().lower()

    def test_login_with_invalid_credentials(self, desktop_page, server_url):
        desktop_page.goto(f"{server_url}/login")
        desktop_page.fill('input[name="username"]', "premium")
        desktop_page.fill('input[name="password"]', "wrongpassword")
        desktop_page.click('button[type="submit"]')
        # Should stay on login page with an error
        assert desktop_page.locator(".error").is_visible()


class TestLogout:
    def test_logout(self, desktop_page, server_url, premium_credentials):
        _login(desktop_page, server_url, *premium_credentials)
        desktop_page.goto(f"{server_url}/logout")
        # Should redirect back to /
        desktop_page.wait_for_url(f"{server_url}/", timeout=5000)
        # Guest banner should be visible again
        assert desktop_page.locator("#guestBanner").is_visible()


class TestGuestAccess:
    def test_guest_sees_demo_card(self, desktop_page, server_url):
        desktop_page.goto(server_url)
        assert desktop_page.locator("#guestBanner").is_visible()
        assert desktop_page.locator("#guestReportCard").is_visible()

    def test_guest_can_view_demo_report(self, desktop_page, server_url):
        desktop_page.goto(f"{server_url}/report")
        # Report should load with summary cards
        desktop_page.wait_for_selector("#summary .metric-card", timeout=10000)
        cards = desktop_page.locator("#summary .metric-card")
        assert cards.count() >= 4

    def test_guest_cannot_access_import(self, desktop_page, server_url):
        desktop_page.goto(f"{server_url}/import")
        # Should redirect to /login
        assert "/login" in desktop_page.url

    def test_guest_cannot_access_admin(self, desktop_page, server_url):
        desktop_page.goto(f"{server_url}/admin")
        assert "/login" in desktop_page.url


class TestAuthenticatedAccess:
    def test_premium_sees_upload_form(
        self, premium_desktop_page, server_url
    ):
        premium_desktop_page.goto(server_url)
        assert premium_desktop_page.locator("#dropZone").is_visible()
        assert premium_desktop_page.locator("#uploadBtn").is_visible()

    def test_admin_sees_admin_link(self, admin_desktop_page, server_url):
        admin_desktop_page.goto(server_url)
        header = admin_desktop_page.locator("#headerRight")
        assert "Admin" in header.text_content()
