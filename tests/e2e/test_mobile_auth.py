"""Mobile authentication tests."""

from conftest import _login


class TestMobileAuth:
    def test_login_mobile(self, mobile_page, server_url, premium_credentials):
        _login(mobile_page, server_url, *premium_credentials)
        assert mobile_page.url.rstrip("/") == server_url.rstrip("/") or \
               mobile_page.url == f"{server_url}/"

    def test_guest_home_mobile(self, mobile_page, server_url):
        mobile_page.goto(server_url)
        mobile_page.wait_for_timeout(300)

        banner = mobile_page.locator("#guestBanner")
        assert banner.is_visible()
        # Banner should fit within the viewport
        box = banner.bounding_box()
        assert box is not None
        assert box["x"] >= 0
        assert box["x"] + box["width"] <= 390 + 5  # small tolerance
