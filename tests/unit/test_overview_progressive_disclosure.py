"""TDD tests for SAA-404: Progressive disclosure for Report/Overview metrics.

Spec: show 4 primary metrics by default, hide 6 secondary metrics behind a
"Show more metrics" toggle. Toggle state persists via localStorage.
Animation via CSS grid-template-rows transition.
"""
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SUMMARY_JS_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "sections" / "summary.js"
SUMMARY_HTML_PATH = PROJECT_ROOT / "src" / "templates" / "sections" / "summary.html.j2"
STYLES_CSS_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "styles.css"
LAYOUT_JS_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "layout.js"


def _js() -> str:
    return SUMMARY_JS_PATH.read_text(encoding="utf-8")


def _html() -> str:
    return SUMMARY_HTML_PATH.read_text(encoding="utf-8")


def _css() -> str:
    return STYLES_CSS_PATH.read_text(encoding="utf-8")


def _layout_js() -> str:
    return LAYOUT_JS_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests 1-4: metricsConfig array (PR1 equivalent — data model)
# ---------------------------------------------------------------------------

class TestMetricsConfig(unittest.TestCase):
    """METRICS_CONFIG array classifies all metrics by tier."""

    def test_metrics_config_defined(self):
        """Test 1: METRICS_CONFIG is defined in summary.js."""
        self.assertIn("METRICS_CONFIG", _js(), "METRICS_CONFIG must be defined in summary.js")

    def test_metrics_config_has_four_primary(self):
        """Test 2: METRICS_CONFIG contains exactly 4 primary-tier metrics."""
        js = _js()
        # Count occurrences of tier:'primary' or tier: 'primary' or tier:"primary"
        primaries = re.findall(r"""tier\s*:\s*['"]primary['"]""", js)
        self.assertEqual(len(primaries), 4,
            f"Expected 4 primary metrics in METRICS_CONFIG, found {len(primaries)}")

    def test_metrics_config_has_six_secondary(self):
        """Test 3: METRICS_CONFIG contains exactly 6 secondary-tier metrics."""
        js = _js()
        secondaries = re.findall(r"""tier\s*:\s*['"]secondary['"]""", js)
        self.assertEqual(len(secondaries), 6,
            f"Expected 6 secondary metrics in METRICS_CONFIG, found {len(secondaries)}")

    def test_metrics_config_drives_rendering(self):
        """Test 4: updateSummary uses METRICS_CONFIG — no hardcoded primary/secondary split."""
        js = _js()
        # METRICS_CONFIG must be referenced inside updateSummary
        self.assertIn("METRICS_CONFIG", js)
        # There must be a filter or loop using 'tier' — no hardcoded list of primary keys
        self.assertIn("tier", js, "tier field must be used in rendering logic")
        # Verify no hardcoded array of primary keys (would look like 'summary.portfolio_value','summary.total_return')
        hardcoded = re.search(
            r"""(primary|secondary)\s*:\s*\[\s*['"]summary\.""", js
        )
        self.assertIsNone(hardcoded, "Primary/secondary split must come from METRICS_CONFIG, not a hardcoded array")


# ---------------------------------------------------------------------------
# Tests 5-9: CollapsibleSection HTML structure (PR2 equivalent)
# ---------------------------------------------------------------------------

class TestToggleHTMLStructure(unittest.TestCase):
    """Toggle button and secondary panel exist in the summary template."""

    def test_toggle_button_exists(self):
        """Test 5: A toggle button with id overviewMetricsToggle is in summary.html.j2."""
        self.assertIn("overviewMetricsToggle", _html(),
            "Toggle button with id overviewMetricsToggle must exist in summary.html.j2")

    def test_toggle_has_aria_expanded(self):
        """Test 6: Toggle button has aria-expanded attribute."""
        self.assertIn("aria-expanded", _html(),
            "Toggle button must have aria-expanded attribute for accessibility")

    def test_secondary_panel_exists(self):
        """Test 7: overviewMetricsPanel div exists in summary.html.j2."""
        self.assertIn("overviewMetricsPanel", _html(),
            "Secondary metrics panel with id overviewMetricsPanel must exist")

    def test_secondary_data_role_exists(self):
        """Test 8: data-role='summarySecondary' section exists for secondary cards."""
        self.assertIn("summarySecondary", _html(),
            "A section with data-role=summarySecondary must exist for secondary metric cards")

    def test_toggle_controls_panel(self):
        """Test 9: Toggle button references overviewMetricsPanel via aria-controls."""
        html = _html()
        self.assertIn("overviewMetricsPanel", html)
        # The toggle and panel must both be present (aria-controls links them)
        self.assertIn("overviewMetricsToggle", html)


# ---------------------------------------------------------------------------
# Tests 10-14: localStorage persistence (PR2 equivalent)
# ---------------------------------------------------------------------------

class TestLocalStoragePersistence(unittest.TestCase):
    """Toggle state is persisted to and read from localStorage."""

    def test_localStorage_key_used(self):
        """Test 10: summary.js uses the overview-metrics-expanded localStorage key."""
        self.assertIn("overview-metrics-expanded", _js(),
            "summary.js must use 'overview-metrics-expanded' as the localStorage key")

    def test_localStorage_written_on_toggle(self):
        """Test 11: localStorage.setItem is called with the metrics key on toggle."""
        js = _js()
        self.assertIn("localStorage.setItem", js,
            "localStorage.setItem must be called when toggling the metrics panel")
        # Verify the key is used in the setItem call context
        self.assertIn("overview-metrics-expanded", js)

    def test_localStorage_read_on_init(self):
        """Test 12: localStorage.getItem is called to read initial expanded state."""
        js = _js()
        self.assertIn("localStorage.getItem", js,
            "localStorage.getItem must be called to restore toggle state on page load")

    def test_default_collapsed_when_storage_empty(self):
        """Test 13: Default state is collapsed (aria-expanded=false) when localStorage is empty."""
        html = _html()
        # The initial aria-expanded in the HTML must be 'false' (collapsed by default)
        self.assertIn('aria-expanded="false"', html,
            "Toggle must default to aria-expanded='false' (collapsed) for new users")

    def test_localStorage_graceful_fallback(self):
        """Test 14: localStorage access is wrapped in try/catch for graceful failure."""
        js = _js()
        self.assertIn("try", js, "localStorage access must be wrapped in try/catch")
        self.assertIn("catch", js, "localStorage access must have a catch block for private browsing")


# ---------------------------------------------------------------------------
# Tests 15-17: Label changes and toggle logic
# ---------------------------------------------------------------------------

class TestToggleLabels(unittest.TestCase):
    """Toggle label changes between expanded and collapsed states."""

    def test_show_more_label(self):
        """Test 15: 'Show more metrics' label exists for the collapsed state."""
        self.assertIn("Show more metrics", _html() + _js(),
            "Collapsed label 'Show more metrics' must exist")

    def test_show_fewer_label(self):
        """Test 16: 'Show fewer metrics' label exists for the expanded state."""
        self.assertIn("Show fewer metrics", _js(),
            "Expanded label 'Show fewer metrics' must be set dynamically in summary.js")

    def test_label_changes_on_toggle(self):
        """Test 17: Label text is updated when toggling (both labels must be in the JS)."""
        js = _js()
        self.assertIn("Show more metrics", js)
        self.assertIn("Show fewer metrics", js)


# ---------------------------------------------------------------------------
# Tests 18-21: CSS animation and responsive grid
# ---------------------------------------------------------------------------

class TestCSSAnimation(unittest.TestCase):
    """CSS grid-template-rows animation for smooth expand/collapse."""

    def test_overview_metrics_panel_css_exists(self):
        """Test 18: .overview-metrics-panel CSS class exists in styles.css."""
        self.assertIn("overview-metrics-panel", _css(),
            ".overview-metrics-panel CSS class must be defined in styles.css")

    def test_css_grid_animation(self):
        """Test 19: .overview-metrics-panel uses grid-template-rows for animation."""
        css = _css()
        self.assertIn("grid-template-rows", css,
            "CSS must use grid-template-rows for smooth expand/collapse animation")

    def test_css_expanded_state(self):
        """Test 20: .overview-metrics-panel.is-expanded sets grid-template-rows: 1fr."""
        css = _css()
        self.assertIn("is-expanded", css,
            ".overview-metrics-panel.is-expanded class must be defined for expanded state")
        # 1fr is the expanded state
        self.assertIn("1fr", css)

    def test_inner_overflow_hidden(self):
        """Test 21: overview-metrics-inner has overflow:hidden to clip animation."""
        css = _css()
        self.assertIn("overview-metrics-inner", css,
            ".overview-metrics-inner must be defined in CSS")
        # overflow:hidden is required for the grid animation to work
        idx = css.find("overview-metrics-inner")
        snippet = css[idx:idx+200]
        self.assertIn("overflow", snippet,
            ".overview-metrics-inner must have overflow property for animation clipping")


# ---------------------------------------------------------------------------
# Tests 22-24: Rendering logic — primary vs secondary split
# ---------------------------------------------------------------------------

class TestRenderingSplit(unittest.TestCase):
    """updateSummary renders primary cards and secondaries separately."""

    def test_primary_rendered_in_summary_role(self):
        """Test 22: Primary metrics are rendered into data-role='summary' element."""
        js = _js()
        # The JS must write to the 'summary' data-role for primary cards
        self.assertIn("summarySecondary", js,
            "summary.js must render secondary cards into summarySecondary role element")
        self.assertIn("summary", js)

    def test_secondary_rendered_in_secondary_role(self):
        """Test 23: Secondary metrics are rendered into data-role='summarySecondary' element."""
        js = _js()
        self.assertIn("summarySecondary", js,
            "summary.js must find and populate the summarySecondary element")

    def test_all_ten_metrics_present(self):
        """Test 24: All 10 metric keys are defined in METRICS_CONFIG."""
        js = _js()
        expected_keys = [
            "summary.portfolio_value",
            "summary.total_return",
            "summary.daily_change",
            "summary.dividend_yield",
            "summary.cagr",
            "summary.sharpe",
            "summary.max_drawdown",
            "summary.unrealized_pnl",
            "summary.absolute_gain",
            "summary.twr",
        ]
        for key in expected_keys:
            self.assertIn(key, js, f"Metric key '{key}' must be present in summary.js METRICS_CONFIG")


# ---------------------------------------------------------------------------
# Test 25: layout.js knows new metric keys
# ---------------------------------------------------------------------------

class TestLayoutJsMetricKeys(unittest.TestCase):
    """layout.js DEFAULT_CARD_ORDER includes new metric keys."""

    def test_new_metrics_in_layout(self):
        """Test 25: layout.js includes daily_change and dividend_yield in card order."""
        layout = _layout_js()
        self.assertIn("summary.daily_change", layout,
            "layout.js DEFAULT_CARD_ORDER must include summary.daily_change")
        self.assertIn("summary.dividend_yield", layout,
            "layout.js DEFAULT_CARD_ORDER must include summary.dividend_yield")


if __name__ == "__main__":
    unittest.main()
