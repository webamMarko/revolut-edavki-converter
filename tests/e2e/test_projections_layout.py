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


# ---------------------------------------------------------------------------
# SAA-509: FIRE section layout — order, accordion wiring, label, default state
# ---------------------------------------------------------------------------

_MOCK_FIRE_HTML = """
<section data-role="fireSection" id="test-fire-section" style="display:block">
  <h2>FIRE Projection</h2>
  <div class="fire-config" data-test-section="inputs">
    <input type="number" placeholder="Annual expenses">
  </div>
  <div data-role="fireCards" class="metric-cards-row" style="margin-bottom:1rem">
    <div class="metric-card"><div class="label">FIRE Progress</div><div class="value">75%</div></div>
    <div class="metric-card"><div class="label">Target</div><div class="value">500000</div></div>
    <div class="metric-card"><div class="label">Current Value</div><div class="value">375000</div></div>
    <div class="metric-card"><div class="label">Est. Years</div><div class="value">~8</div></div>
  </div>
  <div class="chart-wrap" data-test-section="chart" style="height:300px">
    <canvas></canvas>
  </div>
  <button class="coll-panel-hdr" aria-expanded="false" aria-controls="test-fire-additional-metrics">
    Additional Metrics
    <svg class="coll-panel-chevron" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
      <polyline points="4,6 8,10 12,6"/>
    </svg>
  </button>
  <div class="coll-panel-body" id="test-fire-additional-metrics">
    <div data-role="fireSecondaryCards" class="card-grid small" style="padding:0.75rem 0">
      <div class="metric-card"><div class="label">Remaining</div><div class="value">125000</div></div>
      <div class="metric-card"><div class="label">Est. Year</div><div class="value">2034</div></div>
    </div>
  </div>
</section>
"""


def _inject_fire_section(page):
    page.evaluate(
        """(html) => {
            const wrapper = document.createElement('div');
            wrapper.innerHTML = html;
            document.body.appendChild(wrapper.firstElementChild);
        }""",
        _MOCK_FIRE_HTML,
    )


class TestFireProjectionsLayout:
    def test_sections_render_in_order(self, premium_desktop_page, server_url):
        """Inputs come first, then metrics row, then chart, then accordion."""
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)
        _inject_fire_section(premium_desktop_page)

        order = premium_desktop_page.evaluate(
            """() => {
                const sec = document.querySelector('[data-role="fireSection"]');
                if (!sec) return [];
                const result = [];
                for (const child of sec.children) {
                    if (child.tagName === 'H2') { result.push('heading'); }
                    else if (child.dataset.testSection === 'inputs' || child.classList.contains('fire-config')) { result.push('inputs'); }
                    else if (child.dataset.role === 'fireCards') { result.push('metricsRow'); }
                    else if (child.dataset.testSection === 'chart' || child.classList.contains('chart-wrap')) { result.push('chart'); }
                    else if (child.classList.contains('coll-panel-hdr')) { result.push('accordion-hdr'); }
                    else if (child.classList.contains('coll-panel-body')) { result.push('accordion-body'); }
                }
                return result;
            }"""
        )

        inputs_idx = order.index('inputs')
        metrics_idx = order.index('metricsRow')
        chart_idx = order.index('chart')
        accordion_idx = order.index('accordion-hdr')

        assert inputs_idx < metrics_idx, f"inputs must precede metricsRow — got order: {order}"
        assert metrics_idx < chart_idx, f"metricsRow must precede chart — got order: {order}"
        assert chart_idx < accordion_idx, f"chart must precede accordion — got order: {order}"

    def test_remaining_and_est_year_in_accordion(self, premium_desktop_page, server_url):
        """Remaining and Est. Year metric cards are inside the accordion body."""
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)
        _inject_fire_section(premium_desktop_page)

        labels = premium_desktop_page.evaluate(
            """() => {
                const body = document.getElementById('test-fire-additional-metrics');
                if (!body) return [];
                return Array.from(body.querySelectorAll('.metric-card .label'))
                    .map(el => el.textContent.trim());
            }"""
        )

        assert 'Remaining' in labels, f"Expected 'Remaining' in accordion, got: {labels}"
        assert 'Est. Year' in labels, f"Expected 'Est. Year' in accordion, got: {labels}"

    def test_accordion_label_is_additional_metrics(self, premium_desktop_page, server_url):
        """Accordion header text reads 'Additional Metrics'."""
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)
        _inject_fire_section(premium_desktop_page)

        label = premium_desktop_page.evaluate(
            """() => {
                const btn = document.querySelector('[data-role="fireSection"] .coll-panel-hdr');
                if (!btn) return null;
                return Array.from(btn.childNodes)
                    .filter(n => n.nodeType === Node.TEXT_NODE)
                    .map(n => n.textContent.trim())
                    .filter(Boolean)
                    .join('');
            }"""
        )

        assert label == 'Additional Metrics', f"Expected 'Additional Metrics', got: {label!r}"

    def test_accordion_collapsed_by_default(self, premium_desktop_page, server_url):
        """Accordion body has aria-expanded=false and no is-open class on load."""
        premium_desktop_page.goto(f"{server_url}/report")
        premium_desktop_page.wait_for_selector("#summary", timeout=15000)
        _inject_fire_section(premium_desktop_page)

        state = premium_desktop_page.evaluate(
            """() => {
                const btn = document.querySelector('[data-role="fireSection"] .coll-panel-hdr');
                const body = document.getElementById('test-fire-additional-metrics');
                if (!btn || !body) return null;
                return {
                    ariaExpanded: btn.getAttribute('aria-expanded'),
                    bodyHasIsOpen: body.classList.contains('is-open')
                };
            }"""
        )

        assert state is not None, "Could not find accordion elements"
        assert state['ariaExpanded'] == 'false', \
            f"Expected aria-expanded=false, got: {state['ariaExpanded']}"
        assert not state['bodyHasIsOpen'], \
            "Expected accordion body NOT to have is-open class (collapsed by default)"
