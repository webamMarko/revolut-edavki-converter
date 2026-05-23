"""Test /account page functionality."""

from conftest import _login


class TestAccountPage:
    def test_account_page_renders_for_premium_user(
        self, desktop_page, server_url, premium_credentials
    ):
        """Test that /account page loads successfully for premium users."""
        _login(desktop_page, server_url, *premium_credentials)

        # Navigate to /account
        desktop_page.goto(f"{server_url}/account")

        # Wait for page to load
        desktop_page.wait_for_load_state("networkidle", timeout=10000)

        # Check that the page loaded (not redirected to login)
        assert "/account" in desktop_page.url

        # Check for account page elements
        assert desktop_page.locator("h1").filter(has_text="Account Settings").is_visible()
        assert desktop_page.locator("text=Username:").is_visible()
        assert desktop_page.locator("text=Email:").is_visible()
