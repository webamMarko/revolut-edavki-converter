"""E2E accessibility + responsive verification for SAA-577-5 (SAA-637).

Covers the SAA-577-5 polish-pass checklist on the real Tax page:
1. Expand/collapse chevrons expose aria-expanded/aria-controls and toggle on click.
2. Pagination announces "Page X of Y" via an aria-live="polite" region.
3. Pagination + toggle controls are reachable and operable via keyboard
   (focus, Enter, Space) using native <button>/<select> elements.
4. The .pagination container wraps and stays within the viewport on mobile.
5. axe-core reports no new serious/critical violations on the tax page.
"""
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AXE_SOURCE_PATH = PROJECT_ROOT / "ux-audit" / ".axe-core.min.js"

MOBILE_VIEWPORT = {"width": 390, "height": 844}


def _goto_tax(page, server_url):
    page.add_init_script("localStorage.setItem('tour_completed', 'true')")
    page.goto(f"{server_url}/report")
    page.click('[data-page="tax"]')
    page.wait_for_selector('[data-role="taxTable"] tbody tr', state="visible", timeout=10000)
    page.wait_for_timeout(300)


def _login(page, server_url, username, password):
    page.goto(f"{server_url}/login")
    page.fill('input[name="username"]', username)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')
    page.wait_for_url(f"{server_url}/", timeout=5000)


class TestExpandToggleAria:
    """AC1: every expand/collapse chevron exposes aria-expanded and toggles correctly."""

    def test_dt_toggle_buttons_have_aria_expanded_false_initially(self, premium_desktop_page, server_url):
        page = premium_desktop_page
        _goto_tax(page, server_url)
        toggles = page.locator('#page-tax [data-role="taxTable"] .dt-toggle')
        count = toggles.count()
        assert count >= 1, "expected at least one Tax Summary row with a .dt-toggle"
        for i in range(count):
            toggle = toggles.nth(i)
            assert toggle.get_attribute("aria-expanded") == "false"
            detail_id = toggle.get_attribute("aria-controls")
            assert detail_id, "expand toggle must have aria-controls"
            assert page.locator(f"#{detail_id}").count() == 1

    def test_click_toggle_expands_and_collapses(self, premium_desktop_page, server_url):
        page = premium_desktop_page
        _goto_tax(page, server_url)
        toggle = page.locator('#page-tax [data-role="taxTable"] .dt-toggle').first
        detail_id = toggle.get_attribute("aria-controls")
        detail_row = page.locator(f"#{detail_id}")

        toggle.click()
        assert toggle.get_attribute("aria-expanded") == "true"
        assert detail_row.is_visible()

        toggle.click()
        assert toggle.get_attribute("aria-expanded") == "false"
        assert not detail_row.is_visible()

    def test_keyboard_enter_toggles_expand_state(self, premium_desktop_page, server_url):
        page = premium_desktop_page
        _goto_tax(page, server_url)
        toggle = page.locator('#page-tax [data-role="taxTable"] .dt-toggle').first
        toggle.focus()
        page.keyboard.press("Enter")
        assert toggle.get_attribute("aria-expanded") == "true"

    def test_keyboard_space_toggles_expand_state(self, premium_desktop_page, server_url):
        page = premium_desktop_page
        _goto_tax(page, server_url)
        toggle = page.locator('#page-tax [data-role="taxTable"] .dt-toggle').first
        toggle.focus()
        page.keyboard.press("Space")
        assert toggle.get_attribute("aria-expanded") == "true"


class TestPaginationAriaLive:
    """AC2: pagination exposes a .pagination-info aria-live="polite" region."""

    def test_pagination_info_has_aria_live_polite(self, premium_desktop_page, server_url):
        page = premium_desktop_page
        _goto_tax(page, server_url)
        info = page.locator('#page-tax [data-role="taxPagination"] .pagination-info')
        assert info.count() == 1
        assert info.get_attribute("aria-live") == "polite"
        text = info.text_content()
        assert "Page" in text and "of" in text and "total" in text

    def test_pagination_controls_are_native_focusable_elements(self, premium_desktop_page, server_url):
        page = premium_desktop_page
        _goto_tax(page, server_url)
        pag = page.locator('#page-tax [data-role="taxPagination"]')
        assert pag.locator(".pagination-prev").evaluate("el => el.tagName") == "BUTTON"
        assert pag.locator(".pagination-next").evaluate("el => el.tagName") == "BUTTON"
        size_select = pag.locator(".pagination-size-select")
        assert size_select.evaluate("el => el.tagName") == "SELECT"
        assert size_select.get_attribute("aria-label") == "Rows per page"


class TestKeyboardNavigation:
    """AC3: pagination size select is reachable and operable via keyboard."""

    def test_pagination_size_select_is_keyboard_operable(self, premium_desktop_page, server_url):
        page = premium_desktop_page
        _goto_tax(page, server_url)
        size_select = page.locator('#page-tax [data-role="taxPagination"] .pagination-size-select')
        size_select.focus()
        assert page.evaluate("() => document.activeElement.className") == "pagination-size-select"

        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        page.wait_for_timeout(150)
        # Changing the page size resets to page 1 and re-renders the info text
        info = page.locator('#page-tax [data-role="taxPagination"] .pagination-info')
        assert info.text_content().startswith("Page 1 of")


class TestMobilePaginationLayout:
    """AC4: .pagination wraps and stays within the viewport on mobile widths."""

    def test_pagination_wraps_and_fits_viewport(self, browser, server_url, premium_credentials):
        context = browser.new_context(viewport=MOBILE_VIEWPORT)
        page = context.new_page()
        try:
            _login(page, server_url, *premium_credentials)
            _goto_tax(page, server_url)

            pag = page.locator('#page-tax [data-role="taxPagination"]')
            flex_wrap = pag.evaluate("el => getComputedStyle(el).flexWrap")
            assert flex_wrap == "wrap"

            children = pag.locator(":scope > *")
            for i in range(children.count()):
                box = children.nth(i).bounding_box()
                if box is None:
                    continue
                assert box["x"] + box["width"] <= MOBILE_VIEWPORT["width"] + 1, (
                    f"pagination child {i} overflows the {MOBILE_VIEWPORT['width']}px viewport: {box}"
                )
        finally:
            context.close()


class TestAxeAudit:
    """AC5: axe-core reports no new violations on the SAA-577 pagination/expand-toggle controls.

    Runs a full audit of #page-tax (with a row expanded so the detail
    markup is covered too), then asserts that none of the reported
    violations target the pagination controls or expand/collapse toggles
    introduced by SAA-577. The page also has pre-existing, unrelated
    violations (color-contrast on .pos/.neg table cells from the global
    theme, the tax-subtab buttons, and the export <select>'s missing
    label) that predate this epic and are out of scope for this
    pagination/responsiveness polish pass.
    """

    NEW_CONTROL_MARKERS = (
        "pagination",
        "dt-toggle",
        "pos-chevron",
    )

    def test_no_violations_on_pagination_and_toggle_controls(self, premium_desktop_page, server_url):
        if not AXE_SOURCE_PATH.exists():
            pytest.skip("axe-core source not cached at ux-audit/.axe-core.min.js")

        page = premium_desktop_page
        _goto_tax(page, server_url)

        # Expand a row so the SAA-577 detail markup is also covered by the audit.
        page.locator('#page-tax [data-role="taxTable"] .dt-toggle').first.click()

        axe_source = AXE_SOURCE_PATH.read_text(encoding="utf-8")
        page.evaluate(axe_source)

        result = page.evaluate("""() => {
            return new Promise((resolve) => {
                axe.run(document.querySelector('#page-tax'), {
                    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'best-practice'] }
                }).then(resolve);
            });
        }""")

        new_control_violations = [
            {"id": v["id"], "impact": v["impact"], "target": n["target"]}
            for v in result["violations"]
            for n in v["nodes"]
            if any(marker in t for t in n["target"] for marker in self.NEW_CONTROL_MARKERS)
        ]
        assert new_control_violations == [], json.dumps(new_control_violations, indent=2)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
