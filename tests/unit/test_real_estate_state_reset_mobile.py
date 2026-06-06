"""TDD tests for SAA-552: State reset verification and mobile responsiveness.

Spec (from SAA-327 spec, Task 5):
- Toggle and accordion always start collapsed on page load/reload (no persistence)
- No localStorage/sessionStorage persistence of UI state
- Metrics stack vertically on mobile (<768px)
- Chart scales responsively (responsive:true, width follows container)
- Property table has horizontal scroll on mobile
"""
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RE_JS_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "sections" / "real_estate.js"
RE_HTML_PATH = PROJECT_ROOT / "src" / "templates" / "sections" / "real_estate.html.j2"
CSS_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "styles.css"
TOGGLE_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "components" / "ShowAllMetricsToggle.js"
PRIMARY_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "components" / "PrimaryMetrics.js"
SECONDARY_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "components" / "SecondaryMetrics.js"


def _js() -> str:
    return RE_JS_PATH.read_text(encoding="utf-8")


def _html() -> str:
    return RE_HTML_PATH.read_text(encoding="utf-8")


def _css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


def _toggle() -> str:
    return TOGGLE_PATH.read_text(encoding="utf-8")


def _all_re_js_sources() -> list[tuple[str, str]]:
    """Return (filename, content) for all real-estate JS source files."""
    paths = [
        RE_JS_PATH,
        TOGGLE_PATH,
        PRIMARY_PATH,
        SECONDARY_PATH,
        PROJECT_ROOT / "src" / "templates" / "assets" / "components" / "TimeRangeSelector.js",
    ]
    return [(p.name, p.read_text(encoding="utf-8")) for p in paths if p.exists()]


# ---------------------------------------------------------------------------
# Task 1: Toggle state defaults to collapsed on mount (no persistence)
# ---------------------------------------------------------------------------

class TestToggleDefaultCollapsed(unittest.TestCase):
    """Show-all-metrics toggle starts collapsed on every page load."""

    def test_secondary_container_hidden_by_default_in_html(self):
        """Test 1a: reCardsSecondary has display:none in the HTML source (collapsed by default)."""
        html = _html()
        idx = html.find("reCardsSecondary")
        self.assertGreater(idx, -1,
            "HTML must have a 'reCardsSecondary' container")
        tag_start = html.rfind("<", 0, idx)
        tag_end = html.find(">", idx)
        tag = html[tag_start:tag_end + 1]
        normalised = tag.replace(" ", "").replace('"', "").replace("'", "")
        self.assertIn("display:none", normalised,
            "reCardsSecondary must have display:none in HTML — collapsed by default, no JS needed")

    def test_toggle_initial_render_uses_expanded_false(self):
        """Test 1b: JS initialises the toggle with expanded=false (aria-expanded starts false)."""
        js = _js()
        # createShowAllMetricsToggle is called with `false` at init time
        self.assertIn("createShowAllMetricsToggle(false)", js,
            "JS must call createShowAllMetricsToggle(false) so toggle starts collapsed")

    def test_toggle_aria_expanded_not_set_true_at_init(self):
        """Test 1c: JS does NOT set aria-expanded='true' at module initialisation level."""
        js = _js()
        # The only place aria-expanded is set to 'true' must be inside a click handler,
        # not at the module scope / IIFE init.  We split on the click handler to check.
        click_idx = js.find("'click'")
        self.assertGreater(click_idx, -1, "JS must have a click handler")
        init_section = js[:click_idx]
        self.assertNotIn("setAttribute('aria-expanded', 'true')", init_section,
            "JS must not set aria-expanded='true' before the click handler is defined")

    def test_toggle_show_label_used_at_init(self):
        """Test 1d: Toggle component renders 'Show all metrics' text when expanded=false."""
        toggle = _toggle()
        self.assertIn("Show all metrics", toggle,
            "ShowAllMetricsToggle must render 'Show all metrics' for collapsed state")

    def test_secondary_display_change_only_inside_click_handler(self):
        """Test 1e: JS only reveals reCardsSecondary inside the click event handler."""
        js = _js()
        # The secondary container must only be revealed inside a click callback, never at init
        click_idx = js.find("'click'")
        self.assertGreater(click_idx, -1)
        init_section = js[:click_idx]
        # 'style.display = \'\'' would reveal the secondary — must not appear before click
        self.assertNotIn("reCardsSecondary", init_section.split("innerHTML")[0] if "innerHTML" in init_section else init_section,
            "reCardsSecondary must not be revealed (display='') before the click handler")


# ---------------------------------------------------------------------------
# Task 1 (continued): Accordion state defaults to collapsed on mount
# ---------------------------------------------------------------------------

class TestAccordionDefaultCollapsed(unittest.TestCase):
    """Property-details accordion starts collapsed on every page load."""

    def test_accordion_header_aria_expanded_false_in_html(self):
        """Test 1f: accordion header has aria-expanded='false' in the HTML source."""
        html = _html()
        self.assertIn('aria-expanded="false"', html,
            "property-details-header must have aria-expanded='false' as the HTML default")

    def test_panel_has_no_is_open_class_in_html(self):
        """Test 1g: property-details-panel does NOT have is-open class in HTML (collapsed)."""
        html = _html()
        panel_idx = html.find("property-details-panel")
        self.assertGreater(panel_idx, -1,
            "property-details-panel must exist in real_estate.html.j2")
        tag_start = html.rfind("<", 0, panel_idx)
        tag_end = html.find(">", panel_idx)
        tag = html[tag_start:tag_end + 1]
        self.assertNotIn("is-open", tag,
            "property-details-panel must NOT have is-open class in the HTML source")

    def test_css_panel_starts_zero_maxheight(self):
        """Test 1h: CSS sets max-height:0 on .property-details-panel (visually collapsed)."""
        css = _css()
        idx = css.find("property-details-panel")
        self.assertGreater(idx, -1)
        # Look for max-height: 0 within the base (non-.is-open) rule
        snippet = css[idx:idx + 200]
        self.assertIn("max-height: 0", snippet,
            ".property-details-panel must start with max-height:0 so it is collapsed on load")

    def test_accordion_aria_expanded_not_set_true_at_js_init(self):
        """Test 1i: JS accordion init does NOT call setAttribute('aria-expanded','true') on mount."""
        js = _js()
        # Find the accordion init IIFE
        accordion_idx = js.find("initPropertyDetailsAccordion")
        self.assertGreater(accordion_idx, -1,
            "JS must have initPropertyDetailsAccordion")
        # Find the first click listener registration after accordion init
        click_after = js.find("'click'", accordion_idx)
        self.assertGreater(click_after, -1)
        init_section = js[accordion_idx:click_after]
        self.assertNotIn("setAttribute('aria-expanded', 'true')", init_section,
            "Accordion init must not expand the panel — it must start collapsed")

    def test_accordion_panel_is_open_only_after_click(self):
        """Test 1j: JS accordion init registers a click listener and does not auto-invoke toggle."""
        js = _js()
        accordion_idx = js.find("initPropertyDetailsAccordion")
        self.assertGreater(accordion_idx, -1)
        # The IIFE ends with ')()' — find that closing after accordion_idx
        iife_end = js.find(")()", accordion_idx)
        self.assertGreater(iife_end, -1,
            "initPropertyDetailsAccordion must be an IIFE")
        iife_body = js[accordion_idx:iife_end + 4]
        # Must have a click listener registered (not a direct call)
        self.assertIn("addEventListener('click'", iife_body,
            "Accordion init must register click listener — not call toggle directly")
        # The IIFE must NOT directly call classList.add outside of a function body:
        # i.e., no bare 'panel.classList.add' before any 'function' keyword
        first_fn_def = iife_body.find("function toggle")
        self.assertGreater(first_fn_def, -1,
            "Accordion init must define a toggle function")
        pre_fn_section = iife_body[:first_fn_def]
        self.assertNotIn("classList.add('is-open')", pre_fn_section,
            "JS must not add is-open class before the toggle function is defined")


# ---------------------------------------------------------------------------
# Task 2: No localStorage/sessionStorage persistence of UI state
# ---------------------------------------------------------------------------

class TestNoLocalStoragePersistence(unittest.TestCase):
    """Toggle and accordion state must NOT be persisted to localStorage or sessionStorage."""

    def test_re_js_no_localstorage(self):
        """Test 2a: real_estate.js has no localStorage usage."""
        js = _js()
        self.assertNotIn("localStorage", js,
            "real_estate.js must not use localStorage — UI state is not persisted")

    def test_re_js_no_sessionstorage(self):
        """Test 2b: real_estate.js has no sessionStorage usage."""
        js = _js()
        self.assertNotIn("sessionStorage", js,
            "real_estate.js must not use sessionStorage — UI state is not persisted")

    def test_toggle_component_no_localstorage(self):
        """Test 2c: ShowAllMetricsToggle.js has no localStorage usage."""
        toggle = _toggle()
        self.assertNotIn("localStorage", toggle,
            "ShowAllMetricsToggle.js must not use localStorage")

    def test_all_re_components_no_localstorage(self):
        """Test 2d: None of the real-estate JS components use localStorage."""
        for filename, content in _all_re_js_sources():
            with self.subTest(file=filename):
                self.assertNotIn("localStorage", content,
                    f"{filename} must not use localStorage — toggle/accordion state is ephemeral")

    def test_all_re_components_no_sessionstorage(self):
        """Test 2e: None of the real-estate JS components use sessionStorage."""
        for filename, content in _all_re_js_sources():
            with self.subTest(file=filename):
                self.assertNotIn("sessionStorage", content,
                    f"{filename} must not use sessionStorage — toggle/accordion state is ephemeral")

    def test_re_js_no_indexeddb(self):
        """Test 2f: real_estate.js has no indexedDB usage."""
        js = _js()
        self.assertNotIn("indexedDB", js,
            "real_estate.js must not use indexedDB for UI state persistence")

    def test_no_cookie_state_for_toggle(self):
        """Test 2g: real_estate.js does not write cookies to persist toggle state."""
        js = _js()
        # document.cookie = ... would be a persistence mechanism
        self.assertNotIn("document.cookie", js,
            "real_estate.js must not use document.cookie to persist toggle/accordion state")


# ---------------------------------------------------------------------------
# Task 3: Metrics stack vertically on mobile (<768px)
# ---------------------------------------------------------------------------

class TestMetricsMobileLayout(unittest.TestCase):
    """Metric cards stack vertically (reduced columns) on mobile viewports."""

    def test_css_has_768px_media_query(self):
        """Test 3a: CSS has a @media (max-width: 768px) block."""
        css = _css()
        self.assertIn("max-width: 768px", css,
            "CSS must have @media (max-width: 768px) breakpoint for mobile layout")

    def test_card_grid_small_responsive_in_768px_block(self):
        """Test 3b: .card-grid.small gets fewer columns inside a 768px media query."""
        css = _css()
        # There are multiple @media (max-width: 768px) blocks — search all of them
        search_start = 0
        found_card_grid_in_media = False
        while True:
            media_idx = css.find("max-width: 768px", search_start)
            if media_idx == -1:
                break
            snippet = css[media_idx:media_idx + 3000]
            if "card-grid" in snippet and "grid-template-columns" in snippet:
                found_card_grid_in_media = True
                break
            search_start = media_idx + 1
        self.assertTrue(found_card_grid_in_media,
            ".card-grid must be overridden inside a @media (max-width: 768px) block with grid-template-columns")

    def test_css_metrics_columns_reduced_on_mobile(self):
        """Test 3c: .card-grid.small uses 2-column grid at 768px (not auto-fill with many cols)."""
        css = _css()
        media_idx = css.find("max-width: 768px")
        self.assertGreater(media_idx, -1)
        # Look for small grid override in the 768px block
        snippet = css[media_idx:media_idx + 2000]
        # Should either be repeat(2, 1fr) or repeat(1, 1fr) — fewer than desktop
        has_reduced = "repeat(2, 1fr)" in snippet or "repeat(1, 1fr)" in snippet or "1fr" in snippet
        self.assertTrue(has_reduced,
            "CSS must reduce .card-grid column count on mobile to prevent overflow")

    def test_css_has_single_column_on_very_narrow(self):
        """Test 3d: CSS applies single-column grid for card-grid.small on very narrow screens (<390px)."""
        css = _css()
        # Very narrow breakpoint
        narrow_idx = css.find("max-width: 389px")
        if narrow_idx == -1:
            narrow_idx = css.find("max-width: 390px")
        self.assertGreater(narrow_idx, -1,
            "CSS must have a very-narrow breakpoint (≤389px or ≤390px) for single-column metrics")
        snippet = css[narrow_idx:narrow_idx + 500]
        self.assertIn("card-grid", snippet,
            ".card-grid must be overridden at the narrowest mobile breakpoint")
        self.assertIn("1fr", snippet,
            "Metrics must use single-column (1fr) layout on very narrow screens")

    def test_html_primary_metrics_uses_card_grid_small(self):
        """Test 3e: Primary metrics container uses card-grid small class for responsive layout."""
        html = _html()
        # The reCards container must reference card-grid so CSS media queries apply
        idx = html.find("reCards")
        self.assertGreater(idx, -1)
        tag_start = html.rfind("<", 0, idx)
        tag_end = html.find(">", idx)
        tag = html[tag_start:tag_end + 1]
        self.assertIn("card-grid", tag,
            "reCards container must use card-grid class so mobile CSS breakpoints apply")

    def test_css_overflow_hidden_on_mobile_page(self):
        """Test 3f: CSS prevents horizontal overflow on mobile page (metrics don't cause scroll)."""
        css = _css()
        # Page must not overflow on mobile — required for metrics to stack, not overflow
        self.assertIn("overflow-x: hidden", css,
            "CSS must prevent horizontal overflow on mobile so metrics stack rather than overflow")


# ---------------------------------------------------------------------------
# Task 4: Chart container scales with viewport width
# ---------------------------------------------------------------------------

class TestChartResponsive(unittest.TestCase):
    """Property value chart scales responsively with viewport width."""

    def test_chart_responsive_option_enabled(self):
        """Test 4a: Chart is initialised with responsive:true."""
        js = _js()
        self.assertIn("responsive: true", js,
            "Chart.js must be initialised with responsive:true so canvas scales with container")

    def test_chart_maintain_aspect_ratio_disabled(self):
        """Test 4b: Chart has maintainAspectRatio:false to allow CSS-controlled height."""
        js = _js()
        self.assertIn("maintainAspectRatio: false", js,
            "Chart must have maintainAspectRatio:false so CSS controls height independently")

    def test_chart_wrap_has_css_height(self):
        """Test 4c: .chart-wrap has a defined height in CSS (Chart.js fills it)."""
        css = _css()
        idx = css.find(".chart-wrap")
        self.assertGreater(idx, -1,
            ".chart-wrap must be defined in CSS")
        snippet = css[idx:idx + 100]
        self.assertIn("height", snippet,
            ".chart-wrap must have an explicit height so Chart.js can size the canvas")

    def test_chart_wrap_height_reduced_on_mobile(self):
        """Test 4d: .chart-wrap has a smaller height inside the @media (max-width: 768px) block."""
        css = _css()
        media_idx = css.find("max-width: 768px")
        self.assertGreater(media_idx, -1)
        # Search subsequent mobile block for chart-wrap height override
        snippet = css[media_idx:media_idx + 2000]
        self.assertIn("chart-wrap", snippet,
            ".chart-wrap must be overridden inside the @media (max-width: 768px) block")
        idx_in_snippet = snippet.find("chart-wrap")
        local = snippet[idx_in_snippet:idx_in_snippet + 100]
        self.assertIn("height", local,
            ".chart-wrap must have a height override on mobile so the chart is shorter")

    def test_chart_canvas_inside_chart_wrap(self):
        """Test 4e: reChart canvas is inside a .chart-wrap div in the HTML."""
        html = _html()
        chart_wrap_idx = html.find("chart-wrap")
        self.assertGreater(chart_wrap_idx, -1,
            "HTML must have a .chart-wrap container")
        canvas_idx = html.find("reChart", chart_wrap_idx)
        self.assertGreater(canvas_idx, -1,
            "reChart canvas must be inside the .chart-wrap element so CSS controls its size")

    def test_chart_wrap_position_relative(self):
        """Test 4f: .chart-wrap uses position:relative (required by Chart.js for scaling)."""
        css = _css()
        idx = css.find(".chart-wrap")
        self.assertGreater(idx, -1)
        snippet = css[idx:idx + 200]
        self.assertIn("position: relative", snippet,
            ".chart-wrap must use position:relative — Chart.js requires this for responsive sizing")


# ---------------------------------------------------------------------------
# Task 5: Property table scrolls horizontally on narrow viewports
# ---------------------------------------------------------------------------

class TestPropertyTableHorizontalScroll(unittest.TestCase):
    """Property table is wrapped in a scrollable container on narrow viewports."""

    def test_table_scroll_class_in_html(self):
        """Test 5a: reTable is wrapped in a .table-scroll container in the HTML."""
        html = _html()
        table_idx = html.find('data-role="reTable"')
        self.assertGreater(table_idx, -1,
            "reTable must exist in real_estate.html.j2")
        # The .table-scroll wrapper must appear before the table
        scroll_idx = html.rfind("table-scroll", 0, table_idx)
        self.assertGreater(scroll_idx, -1,
            "reTable must be wrapped in a .table-scroll container for horizontal scroll on mobile")

    def test_css_table_scroll_overflow_x_auto(self):
        """Test 5b: .table-scroll has overflow-x:auto in CSS."""
        css = _css()
        idx = css.find("table-scroll")
        self.assertGreater(idx, -1,
            ".table-scroll must be defined in CSS")
        snippet = css[idx:idx + 150]
        self.assertIn("overflow-x: auto", snippet,
            ".table-scroll must have overflow-x:auto so the property table scrolls horizontally")

    def test_css_table_scroll_touch_scrolling(self):
        """Test 5c: .table-scroll has -webkit-overflow-scrolling:touch for smooth iOS scroll."""
        css = _css()
        idx = css.find("table-scroll")
        self.assertGreater(idx, -1)
        snippet = css[idx:idx + 200]
        self.assertIn("-webkit-overflow-scrolling", snippet,
            ".table-scroll must have -webkit-overflow-scrolling:touch for smooth iOS scrolling")

    def test_css_mobile_table_overflow_enforced(self):
        """Test 5d: CSS enforces overflow-x for .table-scroll inside a 768px media query."""
        css = _css()
        # There are multiple @media (max-width: 768px) blocks — search all of them.
        # The main mobile block can be large (>3000 chars) so use a 6000-char window.
        search_start = 0
        found_table_overflow_in_media = False
        while True:
            media_idx = css.find("max-width: 768px", search_start)
            if media_idx == -1:
                break
            snippet = css[media_idx:media_idx + 6000]
            if "table-scroll" in snippet:
                ts_idx = snippet.find("table-scroll")
                local = snippet[ts_idx:ts_idx + 80]
                if "overflow-x" in local:
                    found_table_overflow_in_media = True
                    break
            search_start = media_idx + 1
        self.assertTrue(found_table_overflow_in_media,
            ".table-scroll with overflow-x must appear inside a @media (max-width: 768px) block")

    def test_property_table_inside_accordion_panel(self):
        """Test 5e: reTable is inside the property-details-panel accordion (not exposed directly)."""
        html = _html()
        panel_idx = html.find('id="property-details-panel"')
        self.assertGreater(panel_idx, -1,
            "property-details-panel must exist")
        table_idx = html.find('data-role="reTable"', panel_idx)
        self.assertGreater(table_idx, -1,
            "reTable must be inside property-details-panel so the accordion controls its visibility")

    def test_data_table_has_full_width(self):
        """Test 5f: .data-table width is 100% so it naturally overflows narrow containers."""
        css = _css()
        idx = css.find(".data-table")
        self.assertGreater(idx, -1,
            ".data-table must be defined in CSS")
        snippet = css[idx:idx + 150]
        self.assertIn("width: 100%", snippet,
            ".data-table must have width:100% so it triggers scroll on narrow containers")


if __name__ == "__main__":
    unittest.main()
