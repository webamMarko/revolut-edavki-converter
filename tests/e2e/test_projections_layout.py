"""MetricCardsRow component layout tests — desktop/tablet/mobile responsive behaviour."""

import pytest

# ---------------------------------------------------------------------------
# Viewports
# ---------------------------------------------------------------------------
DESKTOP_WIDTH = 1280
TABLET_WIDTH = 750   # between 389px and 768px breakpoints → 2×2 grid
MOBILE_WIDTH = 375   # below 389px breakpoint → single column stack


def _inject_mcr(page, count=4):
    """Inject a .metric-cards-row with *count* mock .metric-card children into the DOM."""
    page.evaluate(
        """(count) => {
            const wrapper = document.createElement('div');
            wrapper.id = 'test-metric-cards-row';
            wrapper.className = 'metric-cards-row';
            for (let i = 0; i < count; i++) {
                const card = document.createElement('div');
                card.className = 'metric-card';
                card.textContent = 'Card ' + (i + 1);
                wrapper.appendChild(card);
            }
            document.body.appendChild(wrapper);
        }""",
        count,
    )


def _computed(page, selector, prop):
    return page.evaluate(
        """([sel, prop]) => {
            const el = document.querySelector(sel);
            if (!el) return null;
            return window.getComputedStyle(el)[prop];
        }""",
        [selector, prop],
    )


def _get_children_count(page, selector):
    return page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            return el ? el.children.length : 0;
        }""",
        selector,
    )


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------
class TestMetricCardsRow:
    def test_four_cards_render_in_flex_container(self, premium_desktop_page, server_url):
        """4 metric cards are children of the .metric-cards-row flex container."""
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)

        _inject_mcr(premium_desktop_page, count=4)

        count = _get_children_count(premium_desktop_page, "#test-metric-cards-row")
        assert count == 4

        display = _computed(premium_desktop_page, "#test-metric-cards-row", "display")
        assert display == "flex"

    def test_flex_row_on_desktop(self, premium_desktop_page, server_url):
        """flex-direction is 'row' at desktop viewport (1280px)."""
        premium_desktop_page.set_viewport_size({"width": DESKTOP_WIDTH, "height": 720})
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)

        _inject_mcr(premium_desktop_page, count=4)

        display = _computed(premium_desktop_page, "#test-metric-cards-row", "display")
        flex_dir = _computed(premium_desktop_page, "#test-metric-cards-row", "flexDirection")
        assert display == "flex"
        assert flex_dir == "row"

    def test_two_column_grid_on_tablet(self, premium_desktop_page, server_url):
        """2×2 grid layout at tablet viewport (750px)."""
        premium_desktop_page.set_viewport_size({"width": TABLET_WIDTH, "height": 1024})
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)

        _inject_mcr(premium_desktop_page, count=4)

        display = _computed(premium_desktop_page, "#test-metric-cards-row", "display")
        columns = _computed(
            premium_desktop_page, "#test-metric-cards-row", "gridTemplateColumns"
        )
        assert display == "grid"
        # Two equal columns — the computed value contains two column widths
        parts = columns.split()
        assert len(parts) == 2, f"Expected 2-column grid, got gridTemplateColumns={columns!r}"

    def test_column_stack_on_mobile(self, premium_desktop_page, server_url):
        """flex-direction is 'column' at mobile viewport (375px ≤ 389px breakpoint)."""
        premium_desktop_page.set_viewport_size({"width": MOBILE_WIDTH, "height": 812})
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)

        _inject_mcr(premium_desktop_page, count=4)

        display = _computed(premium_desktop_page, "#test-metric-cards-row", "display")
        flex_dir = _computed(premium_desktop_page, "#test-metric-cards-row", "flexDirection")
        assert display == "flex"
        assert flex_dir == "column"
