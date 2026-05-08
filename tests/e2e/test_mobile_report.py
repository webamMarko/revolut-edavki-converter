"""Mobile report page tests — layout, navigation, touch, filters."""

import pytest


class TestMobileLayout:
    def test_mobile_topbar_visible(self, premium_mobile_page, server_url):
        premium_mobile_page.goto(f"{server_url}/report")
        premium_mobile_page.wait_for_selector("#summary", timeout=15000)
        assert premium_mobile_page.locator(".mobile-topbar").is_visible()

    def test_sidebar_brand_hidden(self, premium_mobile_page, server_url):
        premium_mobile_page.goto(f"{server_url}/report")
        premium_mobile_page.wait_for_selector("#summary", timeout=15000)
        assert not premium_mobile_page.locator(".sidebar-brand").is_visible()

    def test_sidebar_footer_hidden(self, premium_mobile_page, server_url):
        premium_mobile_page.goto(f"{server_url}/report")
        premium_mobile_page.wait_for_selector("#summary", timeout=15000)
        assert not premium_mobile_page.locator(".sidebar-footer").is_visible()

    def test_sidebar_is_bottom_tab_bar(self, premium_mobile_page, server_url):
        premium_mobile_page.goto(f"{server_url}/report")
        premium_mobile_page.wait_for_selector("#summary", timeout=15000)

        sidebar = premium_mobile_page.locator(".sidebar")
        box = sidebar.bounding_box()
        assert box is not None
        # Sidebar should be near the bottom of the viewport (844px height)
        assert box["y"] > 400

        # Nav items should be horizontal (first two have similar y position)
        items = premium_mobile_page.locator(".nav-item")
        if items.count() >= 2:
            box0 = items.nth(0).bounding_box()
            box1 = items.nth(1).bounding_box()
            assert box0 is not None and box1 is not None
            # Same row: y positions should be close
            assert abs(box0["y"] - box1["y"]) < 10


class TestMobileTheme:
    def test_mobile_theme_toggle(self, premium_mobile_page, server_url):
        premium_mobile_page.goto(f"{server_url}/report")
        premium_mobile_page.wait_for_selector("#summary", timeout=15000)

        premium_mobile_page.locator("#themeToggleMobile").click()
        theme = premium_mobile_page.evaluate(
            "document.documentElement.getAttribute('data-theme')"
        )
        assert theme == "light"

        premium_mobile_page.locator("#themeToggleMobile").click()
        theme = premium_mobile_page.evaluate(
            "document.documentElement.getAttribute('data-theme')"
        )
        assert theme is None


class TestMobileNavigation:
    def test_mobile_nav_tap(self, premium_mobile_page, server_url):
        premium_mobile_page.goto(f"{server_url}/report")
        premium_mobile_page.wait_for_selector("#summary", timeout=15000)

        pages = ["charts", "positions", "tax", "history"]
        for page_name in pages:
            nav = premium_mobile_page.locator(f'.nav-item[data-page="{page_name}"]')
            if nav.is_visible():
                nav.click()
                premium_mobile_page.wait_for_timeout(300)
                assert premium_mobile_page.locator(f"#page-{page_name}").is_visible()

    def test_mobile_swipe_navigation(self, premium_mobile_page, server_url):
        premium_mobile_page.goto(f"{server_url}/report")
        premium_mobile_page.wait_for_selector("#summary", timeout=15000)

        # Verify we start on overview
        assert premium_mobile_page.locator("#page-overview").is_visible()

        # Swipe left: overview -> charts
        premium_mobile_page.evaluate("""() => {
            const el = document.querySelector('.content');
            const rect = el.getBoundingClientRect();
            const y = rect.top + rect.height / 2;
            const startX = rect.left + rect.width * 0.75;
            const endX = rect.left + rect.width * 0.1;
            const now = Date.now();

            el.dispatchEvent(new TouchEvent('touchstart', {
                touches: [new Touch({identifier: 0, target: el, clientX: startX, clientY: y})],
                bubbles: true
            }));
            // Simulate fast swipe by dispatching touchend immediately
            el.dispatchEvent(new TouchEvent('touchend', {
                changedTouches: [new Touch({identifier: 0, target: el, clientX: endX, clientY: y})],
                bubbles: true
            }));
        }""")
        premium_mobile_page.wait_for_timeout(400)
        assert premium_mobile_page.locator("#page-charts").is_visible()

        # Swipe right: charts -> overview
        premium_mobile_page.evaluate("""() => {
            const el = document.querySelector('.content');
            const rect = el.getBoundingClientRect();
            const y = rect.top + rect.height / 2;
            const startX = rect.left + rect.width * 0.1;
            const endX = rect.left + rect.width * 0.75;

            el.dispatchEvent(new TouchEvent('touchstart', {
                touches: [new Touch({identifier: 0, target: el, clientX: startX, clientY: y})],
                bubbles: true
            }));
            el.dispatchEvent(new TouchEvent('touchend', {
                changedTouches: [new Touch({identifier: 0, target: el, clientX: endX, clientY: y})],
                bubbles: true
            }));
        }""")
        premium_mobile_page.wait_for_timeout(400)
        assert premium_mobile_page.locator("#page-overview").is_visible()


class TestMobileFilters:
    def test_mobile_asset_filter_toggles(self, premium_mobile_page, server_url):
        premium_mobile_page.goto(f"{server_url}/report")
        premium_mobile_page.wait_for_selector("#summary", timeout=15000)

        mobile_filters = premium_mobile_page.locator("#mobileFilters")
        if not mobile_filters.is_visible():
            pytest.skip("Mobile filters not visible (single asset class)")

        toggles = premium_mobile_page.locator("#mobileAssetToggles .toggle-btn")
        active_count = 0
        for i in range(toggles.count()):
            if "active" in (toggles.nth(i).get_attribute("class") or ""):
                active_count += 1

        if active_count <= 1:
            pytest.skip("Cannot toggle off the only active asset class")

        # Toggle off the first active button
        for i in range(toggles.count()):
            btn = toggles.nth(i)
            if "active" in (btn.get_attribute("class") or ""):
                btn.click()
                premium_mobile_page.wait_for_timeout(300)
                assert "active" not in btn.get_attribute("class")
                # Re-activate
                btn.click()
                premium_mobile_page.wait_for_timeout(300)
                break

    def test_mobile_fire_toggle(self, premium_mobile_page, server_url):
        premium_mobile_page.goto(f"{server_url}/report")
        premium_mobile_page.wait_for_selector("#summary", timeout=15000)

        fire_btn = premium_mobile_page.locator("#mobileFireToggleBtn")
        if not fire_btn.is_visible():
            pytest.skip("FIRE toggle not visible (no FIRE config)")

        fire_btn.click()
        premium_mobile_page.wait_for_timeout(300)
        assert "active" in fire_btn.get_attribute("class")

        # Toggle off
        fire_btn.click()
        premium_mobile_page.wait_for_timeout(300)
        assert "active" not in fire_btn.get_attribute("class")


class TestMobileResponsiveElements:
    def test_mobile_summary_cards_2col(self, premium_mobile_page, server_url):
        premium_mobile_page.goto(f"{server_url}/report")
        premium_mobile_page.wait_for_selector("#summary .metric-card", timeout=15000)

        cards = premium_mobile_page.locator("#summary .metric-card")
        if cards.count() < 2:
            pytest.skip("Not enough metric cards")

        box0 = cards.nth(0).bounding_box()
        box1 = cards.nth(1).bounding_box()
        assert box0 is not None and box1 is not None
        # Two-column: cards should be on the same row (similar y)
        assert abs(box0["y"] - box1["y"]) < 10

    def test_mobile_chart_height(self, premium_mobile_page, server_url):
        premium_mobile_page.goto(f"{server_url}/report")
        premium_mobile_page.wait_for_selector("#portfolioChart", timeout=15000)

        chart_wrap = premium_mobile_page.locator(".chart-wrap").first
        box = chart_wrap.bounding_box()
        assert box is not None
        # Mobile chart height should be ~220px (per CSS)
        assert 180 < box["height"] < 260

    def test_mobile_chart_hint_hidden(self, premium_mobile_page, server_url):
        premium_mobile_page.goto(f"{server_url}/report")
        premium_mobile_page.wait_for_selector("#summary", timeout=15000)

        hint = premium_mobile_page.locator(".chart-hint")
        if hint.count() > 0:
            assert not hint.first.is_visible()

    def test_mobile_positions_expand(self, premium_mobile_page, server_url):
        premium_mobile_page.goto(f"{server_url}/report")
        premium_mobile_page.wait_for_selector("#summary", timeout=15000)
        premium_mobile_page.locator('.nav-item[data-page="positions"]').click()
        premium_mobile_page.wait_for_timeout(300)

        expandable = premium_mobile_page.locator(".pos-row-expandable").first
        if not expandable.is_visible():
            pytest.skip("No expandable position rows")

        idx = expandable.get_attribute("data-idx")
        expandable.click()
        premium_mobile_page.wait_for_timeout(300)
        detail = premium_mobile_page.locator(f"#pos-detail-{idx}")
        assert detail.is_visible()

    def test_mobile_transaction_filter(self, premium_mobile_page, server_url):
        premium_mobile_page.goto(f"{server_url}/report")
        premium_mobile_page.wait_for_selector("#summary", timeout=15000)
        premium_mobile_page.locator('.nav-item[data-page="history"]').click()
        premium_mobile_page.wait_for_timeout(300)

        tx_filter = premium_mobile_page.locator("#txFilter")
        assert tx_filter.is_visible()

        # Filter should be full width on mobile
        box = tx_filter.bounding_box()
        assert box is not None
        assert box["width"] > 300  # should be close to full viewport

        tx_filter.fill("BUY")
        premium_mobile_page.wait_for_timeout(300)
        assert premium_mobile_page.locator("#txCount").is_visible()

    def test_mobile_range_buttons_wrap(self, premium_mobile_page, server_url):
        premium_mobile_page.goto(f"{server_url}/report")
        premium_mobile_page.wait_for_selector("#summary", timeout=15000)

        buttons = premium_mobile_page.locator(".range-bar .range-btn")
        if buttons.count() < 3:
            pytest.skip("Not enough range buttons to test wrapping")

        # Collect y positions of visible buttons
        visible_boxes = []
        for i in range(buttons.count()):
            box = buttons.nth(i).bounding_box()
            if box:
                visible_boxes.append(box)

        # At least some buttons should be visible
        assert len(visible_boxes) >= 2
        # First visible button should be within the viewport width
        assert visible_boxes[0]["x"] >= 0
        assert visible_boxes[0]["x"] + visible_boxes[0]["width"] <= 400

    def test_mobile_notes_modal_fullscreen(self, premium_mobile_page, server_url):
        premium_mobile_page.goto(f"{server_url}/report")
        premium_mobile_page.wait_for_selector("#summary", timeout=15000)
        premium_mobile_page.locator('.nav-item[data-page="notes"]').click()
        premium_mobile_page.wait_for_timeout(300)

        add_btn = premium_mobile_page.locator("#btnAddNote")
        if not add_btn.is_visible():
            pytest.skip("Add note button not visible")

        add_btn.click()
        premium_mobile_page.wait_for_timeout(300)

        modal = premium_mobile_page.locator(".note-modal")
        box = modal.bounding_box()
        assert box is not None
        # Modal should take up most of the viewport height on mobile
        assert box["height"] > 500  # viewport is 844px

        # Close
        premium_mobile_page.keyboard.press("Escape")
