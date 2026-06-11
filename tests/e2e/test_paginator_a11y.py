"""E2E accessibility tests for the createPaginator component (SAA-577-5 / SAA-637).

The live Tax Summary table only has enough fixture rows for a single page,
so multi-page behaviors (page-change announcements, Tab order across
prev/page/next controls) are exercised here against Paginator.js mounted
in isolation with synthetic multi-page data.
"""
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PAGINATOR_JS = (
    PROJECT_ROOT / "src" / "templates" / "assets" / "components" / "Paginator.js"
).read_text(encoding="utf-8")


def _mount_paginator(page, server_url, item_count=25):
    page.goto(f"{server_url}/login")
    page.add_script_tag(content=PAGINATOR_JS)
    page.evaluate(
        """(n) => {
            const div = document.createElement('div');
            div.id = 'pgTest';
            document.body.appendChild(div);
            window.__pg = createPaginator(div, {});
            window.__pg.setData(Array.from({ length: n }, (_, i) => i));
            window.__pg.render();
        }""",
        item_count,
    )


def _focused(page):
    return page.evaluate(
        """() => {
            const el = document.activeElement;
            return { tag: el.tagName, cls: el.className, page: el.dataset ? el.dataset.page : null };
        }"""
    )


class TestAriaLiveAnnouncements:
    def test_pagination_info_is_aria_live_polite(self, desktop_page, server_url):
        page = desktop_page
        _mount_paginator(page, server_url)
        info = page.locator("#pgTest .pagination-info")
        assert info.get_attribute("aria-live") == "polite"
        assert info.text_content().strip() == "Page 1 of 3 (25 total)"

    def test_clicking_next_updates_pagination_info(self, desktop_page, server_url):
        page = desktop_page
        _mount_paginator(page, server_url)
        page.locator("#pgTest .pagination-next").click()
        info = page.locator("#pgTest .pagination-info")
        assert info.text_content().strip() == "Page 2 of 3 (25 total)"
        assert info.get_attribute("aria-live") == "polite"


class TestKeyboardActivation:
    def test_enter_activates_next_button(self, desktop_page, server_url):
        page = desktop_page
        _mount_paginator(page, server_url)
        page.locator("#pgTest .pagination-next").focus()
        page.keyboard.press("Enter")
        info = page.locator("#pgTest .pagination-info")
        assert info.text_content().strip() == "Page 2 of 3 (25 total)"

    def test_space_activates_page_button(self, desktop_page, server_url):
        page = desktop_page
        _mount_paginator(page, server_url)
        page3 = page.locator('#pgTest .pagination-page[data-page="2"]')
        page3.focus()
        page.keyboard.press("Space")
        info = page.locator("#pgTest .pagination-info")
        assert info.text_content().strip() == "Page 3 of 3 (25 total)"


class TestTabOrder:
    def test_tab_order_skips_disabled_controls_on_first_page(self, desktop_page, server_url):
        """On page 1, prev and the active page-1 button are disabled and must be skipped."""
        page = desktop_page
        _mount_paginator(page, server_url)

        page.locator("#pgTest .pagination-size-select").focus()
        assert _focused(page)["cls"] == "pagination-size-select"

        # prev and the active page-1 button (data-page="0") are disabled and
        # must be skipped entirely by the browser's Tab order.
        page.keyboard.press("Tab")
        first = _focused(page)
        assert first["cls"] == "pagination-page" and first["page"] == "1", first

        page.keyboard.press("Tab")
        second = _focused(page)
        assert second["cls"] == "pagination-page" and second["page"] == "2", second

        page.keyboard.press("Tab")
        third = _focused(page)
        assert third["cls"] == "pagination-next", third

    def test_disabled_prev_button_not_focusable(self, desktop_page, server_url):
        page = desktop_page
        _mount_paginator(page, server_url)
        prev = page.locator("#pgTest .pagination-prev")
        assert prev.get_attribute("disabled") is not None

    def test_tab_order_on_middle_page_includes_prev(self, desktop_page, server_url):
        """On page 2, prev becomes enabled and joins the Tab sequence."""
        page = desktop_page
        _mount_paginator(page, server_url)
        page.locator("#pgTest .pagination-next").click()  # -> page 2

        page.locator("#pgTest .pagination-size-select").focus()
        page.keyboard.press("Tab")
        first = _focused(page)
        assert first["cls"] == "pagination-prev", first

        page.keyboard.press("Tab")
        second = _focused(page)
        assert second["cls"] == "pagination-page" and second["page"] == "0", second


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
