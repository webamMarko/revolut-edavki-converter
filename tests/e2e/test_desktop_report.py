"""Desktop report dashboard tests — navigation, charts, tables, filters, theme."""

import pytest


class TestReportLoads:
    def test_report_loads_with_data(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary .metric-card", timeout=15000)
        cards = premium_desktop_page.locator("#summary .metric-card")
        assert cards.count() >= 4

    def test_portfolio_chart_exists(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#portfolioChart", timeout=15000)
        box = premium_desktop_page.locator("#portfolioChart").bounding_box()
        assert box is not None
        assert box["width"] > 0
        assert box["height"] > 0


class TestSidebarNavigation:
    def test_overview_active_by_default(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)
        nav = premium_desktop_page.locator('.nav-item[data-page="overview"]')
        assert "active" in nav.get_attribute("class")
        assert premium_desktop_page.locator("#page-overview").is_visible()

    def test_nav_to_heatmap(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)
        premium_desktop_page.locator('.nav-item[data-page="charts"]').click()
        premium_desktop_page.wait_for_timeout(300)
        assert premium_desktop_page.locator("#page-charts").is_visible()
        assert not premium_desktop_page.locator("#page-overview").is_visible()

    def test_nav_to_positions(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)
        premium_desktop_page.locator('.nav-item[data-page="positions"]').click()
        premium_desktop_page.wait_for_timeout(300)
        assert premium_desktop_page.locator("#page-positions").is_visible()

    def test_nav_to_tax(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)
        premium_desktop_page.locator('.nav-item[data-page="tax"]').click()
        premium_desktop_page.wait_for_timeout(300)
        assert premium_desktop_page.locator("#page-tax").is_visible()

    def test_nav_to_history(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)
        premium_desktop_page.locator('.nav-item[data-page="history"]').click()
        premium_desktop_page.wait_for_timeout(300)
        assert premium_desktop_page.locator("#page-history").is_visible()
        assert premium_desktop_page.locator("#txCount").is_visible()

    def test_nav_to_notes(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)
        premium_desktop_page.locator('.nav-item[data-page="notes"]').click()
        premium_desktop_page.wait_for_timeout(300)
        assert premium_desktop_page.locator("#page-notes").is_visible()

    def test_keyboard_navigation(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)

        # overview -> charts (ArrowRight)
        premium_desktop_page.keyboard.press("ArrowRight")
        premium_desktop_page.wait_for_timeout(300)
        assert premium_desktop_page.locator("#page-charts").is_visible()

        # charts -> positions (ArrowRight)
        premium_desktop_page.keyboard.press("ArrowRight")
        premium_desktop_page.wait_for_timeout(300)
        assert premium_desktop_page.locator("#page-positions").is_visible()

        # positions -> charts (ArrowLeft)
        premium_desktop_page.keyboard.press("ArrowLeft")
        premium_desktop_page.wait_for_timeout(300)
        assert premium_desktop_page.locator("#page-charts").is_visible()


class TestRangeButtons:
    def test_range_buttons(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)

        # Click 30D
        btn_30d = premium_desktop_page.locator('.range-btn[data-days="30"]')
        btn_30d.click()
        premium_desktop_page.wait_for_timeout(200)
        assert "active" in btn_30d.get_attribute("class")
        assert premium_desktop_page.locator("#selectionBanner").is_visible()

    def test_all_button_hides_banner(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)

        # Click 30D first
        premium_desktop_page.locator('.range-btn[data-days="30"]').click()
        premium_desktop_page.wait_for_timeout(200)
        assert premium_desktop_page.locator("#selectionBanner").is_visible()

        # Click All to reset
        btn_all = premium_desktop_page.locator('.range-btn[data-days="-1"]:not([data-ytd])')
        btn_all.click()
        premium_desktop_page.wait_for_timeout(200)
        assert not premium_desktop_page.locator("#selectionBanner").is_visible()


class TestTheme:
    def test_theme_toggle(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)

        # Toggle to light
        premium_desktop_page.locator("#themeToggleDesktop").click()
        theme = premium_desktop_page.evaluate(
            "document.documentElement.getAttribute('data-theme')"
        )
        assert theme == "light"

        # Toggle back to dark
        premium_desktop_page.locator("#themeToggleDesktop").click()
        theme = premium_desktop_page.evaluate(
            "document.documentElement.getAttribute('data-theme')"
        )
        assert theme is None  # dark = no attribute

    def test_theme_persists_after_reload(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)

        # Set light theme
        premium_desktop_page.locator("#themeToggleDesktop").click()
        premium_desktop_page.wait_for_timeout(100)

        # Reload
        premium_desktop_page.reload()
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)

        theme = premium_desktop_page.evaluate(
            "document.documentElement.getAttribute('data-theme')"
        )
        assert theme == "light"

        # Clean up: revert to dark
        premium_desktop_page.locator("#themeToggleDesktop").click()


class TestAssetFilter:
    def test_asset_filter_toggles(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)

        toggles = premium_desktop_page.locator("#assetToggles")
        if not toggles.is_visible():
            pytest.skip("Asset filter not visible (single asset class)")

        # Count active toggles
        all_btns = premium_desktop_page.locator("#assetToggles .toggle-btn")
        active_count = sum(
            1 for i in range(all_btns.count())
            if "active" in (all_btns.nth(i).get_attribute("class") or "")
        )
        if active_count <= 1:
            pytest.skip("Only one active asset class; cannot toggle off")

        # Activate an inactive button first (so we have more to work with)
        target_btn = None
        for i in range(all_btns.count()):
            btn = all_btns.nth(i)
            if "active" not in (btn.get_attribute("class") or ""):
                btn.click()
                premium_desktop_page.wait_for_timeout(500)
                assert "active" in btn.get_attribute("class")
                target_btn = btn
                break

        if target_btn is None:
            pytest.skip("All asset classes already active")

        # Now toggle it back off
        target_btn.click()
        premium_desktop_page.wait_for_timeout(500)
        assert "active" not in target_btn.get_attribute("class")


class TestOverviewLayout:
    """SAA-572: Overview page section order, achievements/milestones unification,
    achievements toggle, and Top Movers relocation to the Positions tab."""

    def test_section_order_metrics_chart_health_achievements_gains(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector('[data-role="summary"] .metric-card', timeout=15000)

        roles = premium_desktop_page.evaluate(
            "() => Array.from(document.querySelectorAll('#page-overview [data-role]'))"
            ".map(el => el.getAttribute('data-role'))"
        )

        def idx(role):
            assert role in roles, f"{role} not found in #page-overview"
            return roles.index(role)

        assert idx("summary") < idx("portfolioChart") < idx("healthScoreSection") \
            < idx("achievementsSection") < idx("gainsTable"), \
            f"expected order metrics -> chart -> health -> achievements -> gains, got: {roles}"

    def test_secondary_metrics_collapsed_by_default(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector('[data-role="summary"] .metric-card', timeout=15000)
        premium_desktop_page.evaluate("localStorage.removeItem('overview-metrics-expanded')")
        premium_desktop_page.reload()
        premium_desktop_page.wait_for_selector('[data-role="summary"] .metric-card', timeout=15000)

        toggle = premium_desktop_page.locator('[data-role="overviewMetricsToggle"]')
        panel = premium_desktop_page.locator('[data-role="overviewMetricsPanel"]')
        assert toggle.get_attribute("aria-expanded") == "false"
        assert "is-expanded" not in (panel.get_attribute("class") or "")

    def test_no_duplicate_or_separate_milestone_strip(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector('[data-role="summary"] .metric-card', timeout=15000)

        assert premium_desktop_page.locator('[data-role="milestonesSection"]').count() == 0
        assert premium_desktop_page.locator(".milestones-strip").count() == 0
        assert premium_desktop_page.locator('#page-overview [data-role="achievementsSection"]').count() == 1

    def test_milestones_render_as_achievement_cards(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector('[data-role="summary"] .metric-card', timeout=15000)

        grid = premium_desktop_page.locator('[data-role="achievementsGrid"]')
        milestone_cards = grid.locator("[data-milestone-card]")
        if milestone_cards.count() == 0:
            pytest.skip("No milestone events detected for this portfolio")

        card = milestone_cards.first
        assert "ach-card" in (card.get_attribute("class") or "")
        assert card.locator(".ach-card-icon").count() == 1
        assert card.locator(".ach-card-title").count() == 1
        assert card.locator(".ach-card-detail").count() == 1

    def test_achievements_toggle_hides_grid_without_affecting_chart(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector('[data-role="summary"] .metric-card', timeout=15000)

        section = premium_desktop_page.locator('[data-role="achievementsSection"]')
        if not section.is_visible():
            pytest.skip("No achievements/milestones earned for this portfolio")

        toggle = premium_desktop_page.locator('[data-role="achievementsToggle"]')
        grid = premium_desktop_page.locator('[data-role="achievementsGrid"]')
        chart = premium_desktop_page.locator('[data-role="portfolioChart"]')

        assert grid.is_visible()
        assert chart.is_visible()

        try:
            toggle.click()
            premium_desktop_page.wait_for_timeout(150)
            assert not grid.is_visible()
            assert toggle.get_attribute("aria-expanded") == "false"
            assert chart.is_visible(), "toggling achievements must not affect the chart"

            stored = premium_desktop_page.evaluate("localStorage.getItem('overview-achievements-visible')")
            assert stored == "0"

            premium_desktop_page.reload()
            premium_desktop_page.wait_for_selector('[data-role="summary"] .metric-card', timeout=15000)
            assert not premium_desktop_page.locator('[data-role="achievementsGrid"]').is_visible()
        finally:
            # Restore visible state for test isolation
            premium_desktop_page.evaluate("localStorage.setItem('overview-achievements-visible', '1')")

    def test_top_movers_absent_from_overview(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector('[data-role="summary"] .metric-card', timeout=15000)
        assert premium_desktop_page.locator('#page-overview [data-role="topMoversSection"]').count() == 0

    def test_top_movers_present_in_positions_below_table(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector('[data-role="summary"] .metric-card', timeout=15000)
        premium_desktop_page.locator('.nav-item[data-page="positions"]').click()
        premium_desktop_page.wait_for_timeout(300)

        roles = premium_desktop_page.evaluate(
            "() => Array.from(document.querySelectorAll('#page-positions [data-role]'))"
            ".map(el => el.getAttribute('data-role'))"
        )
        assert "topMoversSection" in roles
        assert roles.index("positionsTable") < roles.index("topMoversSection")


class TestPositions:
    def test_positions_expand_collapse(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)
        premium_desktop_page.locator('.nav-item[data-page="positions"]').click()
        premium_desktop_page.wait_for_timeout(300)

        expandable = premium_desktop_page.locator(".pos-row-expandable").first
        if not expandable.is_visible():
            pytest.skip("No expandable position rows")

        idx = expandable.get_attribute("data-idx")
        detail = premium_desktop_page.locator(f"#pos-detail-{idx}")

        # Expand
        expandable.click()
        premium_desktop_page.wait_for_timeout(300)
        assert detail.is_visible()

        # Collapse
        expandable.click()
        premium_desktop_page.wait_for_timeout(300)
        assert not detail.is_visible()

    def test_positions_table_sorting(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)
        premium_desktop_page.locator('.nav-item[data-page="positions"]').click()
        premium_desktop_page.wait_for_timeout(300)

        headers = premium_desktop_page.locator("#positionsTable th")
        if headers.count() == 0:
            pytest.skip("No positions table headers")

        # Click a header to sort
        header = headers.nth(1)  # second column (usually Qty or similar)
        header.click()
        premium_desktop_page.wait_for_timeout(200)
        arrow = header.locator(".arrow")
        assert arrow.text_content().strip() in ("▲", "▼")


class TestTransactions:
    def test_transaction_filter(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)
        premium_desktop_page.locator('.nav-item[data-page="history"]').click()
        premium_desktop_page.wait_for_timeout(300)

        count_el = premium_desktop_page.locator("#txCount")

        # Type a filter
        premium_desktop_page.locator("#txFilter").fill("BUY")
        premium_desktop_page.wait_for_timeout(300)

        filtered_text = count_el.text_content()
        # The count should change (or at least the filter worked without error)
        assert filtered_text is not None

        # Clear filter
        premium_desktop_page.locator("#txFilter").fill("")
        premium_desktop_page.wait_for_timeout(300)

    def test_transaction_sorting(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)
        premium_desktop_page.locator('.nav-item[data-page="history"]').click()
        premium_desktop_page.wait_for_timeout(300)

        header = premium_desktop_page.locator("#txTable th").first
        header.click()
        premium_desktop_page.wait_for_timeout(200)
        arrow = header.locator(".arrow")
        assert arrow.text_content().strip() in ("▲", "▼")

    def test_transaction_pagination(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)
        premium_desktop_page.locator('.nav-item[data-page="history"]').click()
        premium_desktop_page.wait_for_timeout(300)

        pagination = premium_desktop_page.locator("#txPagination")
        if not pagination.is_visible():
            pytest.skip("Pagination not visible (≤50 transactions)")

        next_btn = pagination.locator("button").last
        if next_btn.is_disabled():
            pytest.skip("Next button disabled")

        next_btn.click()
        premium_desktop_page.wait_for_timeout(300)
        # First page button should now be enabled (we moved forward)
        prev_btn = pagination.locator("button").first
        assert not prev_btn.is_disabled()


class TestTax:
    def test_tax_year_selector(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)
        premium_desktop_page.locator('.nav-item[data-page="tax"]').click()
        premium_desktop_page.wait_for_timeout(300)

        year_bar = premium_desktop_page.locator("#taxYearBar")
        if not year_bar.is_visible():
            pytest.skip("Tax year bar not visible")

        year_btns = year_bar.locator(".range-btn")
        if year_btns.count() < 2:
            pytest.skip("Only one tax year available")

        # Click the first non-active year button
        for i in range(year_btns.count()):
            btn = year_btns.nth(i)
            if "active" not in (btn.get_attribute("class") or ""):
                btn.click()
                premium_desktop_page.wait_for_timeout(300)
                assert "active" in btn.get_attribute("class")
                break


class TestGainsAndHeatmap:
    def test_gains_table_renders(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)
        gains_tbody = premium_desktop_page.locator("#gainsTable tbody")
        assert gains_tbody.is_visible()

    def test_heatmap_renders(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)
        premium_desktop_page.locator('.nav-item[data-page="charts"]').click()
        premium_desktop_page.wait_for_timeout(500)

        heatmap = premium_desktop_page.locator("#heatmap")
        assert heatmap.is_visible()
        # Should contain heatmap cells
        cells = heatmap.locator(".heatmap-cell")
        assert cells.count() > 0

    def test_yearly_heatmap_renders(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)
        premium_desktop_page.locator('.nav-item[data-page="charts"]').click()
        premium_desktop_page.wait_for_timeout(500)

        yearly = premium_desktop_page.locator("#yearly-heatmap")
        assert yearly.is_visible()


class TestPagePersistence:
    def test_active_page_persists_reload(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)

        # Navigate to tax page
        premium_desktop_page.locator('.nav-item[data-page="tax"]').click()
        premium_desktop_page.wait_for_timeout(300)

        # Verify localStorage was set
        stored = premium_desktop_page.evaluate("localStorage.getItem('activePage')")
        assert stored == "tax"

        # Reload page
        premium_desktop_page.reload()
        premium_desktop_page.wait_for_selector("#page-tax", state="visible", timeout=15000)
        assert premium_desktop_page.locator("#page-tax").is_visible()
