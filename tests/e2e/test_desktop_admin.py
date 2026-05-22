"""Desktop admin page tests."""



class TestAdminPage:
    def test_admin_page_loads(self, admin_desktop_page, server_url):
        admin_desktop_page.goto(f"{server_url}/admin")
        admin_desktop_page.wait_for_timeout(500)
        # Should show the admin heading
        heading = admin_desktop_page.locator("h1, h2").first
        assert "Admin" in heading.text_content() or "User" in heading.text_content()

    def test_admin_users_table_has_rows(self, admin_desktop_page, server_url):
        admin_desktop_page.goto(f"{server_url}/admin")
        admin_desktop_page.wait_for_timeout(500)
        # Table should have at least the admin and premium user
        rows = admin_desktop_page.locator("table tbody tr")
        assert rows.count() >= 2

    def test_admin_create_user(self, admin_desktop_page, server_url):
        admin_desktop_page.goto(f"{server_url}/admin")
        admin_desktop_page.wait_for_timeout(500)

        email_input = admin_desktop_page.locator("#newEmail")
        email_input.fill("newuser@test.com")
        admin_desktop_page.locator("#createBtn").click()
        admin_desktop_page.wait_for_timeout(1000)

        msg = admin_desktop_page.locator("#createMsg")
        # Should show success with the generated username
        assert msg.is_visible()
        text = msg.text_content()
        assert "newuser" in text.lower() or "created" in text.lower() or "invite" in text.lower()

    def test_admin_duplicate_user(self, admin_desktop_page, server_url):
        admin_desktop_page.goto(f"{server_url}/admin")
        admin_desktop_page.wait_for_timeout(500)

        # Try creating with the premium user's email (already exists)
        email_input = admin_desktop_page.locator("#newEmail")
        email_input.fill("premium@test.com")
        admin_desktop_page.locator("#createBtn").click()
        admin_desktop_page.wait_for_timeout(1000)

        msg = admin_desktop_page.locator("#createMsg")
        assert msg.is_visible()
        # Should contain an error about existing user
        text = msg.text_content().lower()
        assert "exists" in text or "already" in text or "error" in text


class TestAdminAccessControl:
    def test_premium_cannot_access_admin(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/admin")
        # Should redirect to /login or show forbidden
        assert "/login" in premium_desktop_page.url or \
               premium_desktop_page.locator("text=Forbidden").is_visible() or \
               premium_desktop_page.locator("text=Log in").is_visible()
