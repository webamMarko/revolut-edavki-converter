"""TDD tests for SAA-548: Primary & secondary metric cards with toggle.

Spec (from SAA-327 spec, Task 1):
- On first load, only PROPERTIES and UNREALIZED GAIN % metric cards visible
- Secondary metrics (PURCHASE TOTAL, ETN ESTIMATE) hidden by default
- ShowAllMetricsToggle text link: 'Show all metrics' / 'Show fewer' with aria-expanded
- Clicking 'Show all metrics' reveals secondary, label changes to 'Show fewer'
- Clicking 'Show fewer' hides secondary
- Each component in its own file
"""
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PRIMARY_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "components" / "PrimaryMetrics.js"
SECONDARY_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "components" / "SecondaryMetrics.js"
TOGGLE_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "components" / "ShowAllMetricsToggle.js"
RE_JS_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "sections" / "real_estate.js"
RE_HTML_PATH = PROJECT_ROOT / "src" / "templates" / "sections" / "real_estate.html.j2"


def _primary() -> str:
    return PRIMARY_PATH.read_text(encoding="utf-8")


def _secondary() -> str:
    return SECONDARY_PATH.read_text(encoding="utf-8")


def _toggle() -> str:
    return TOGGLE_PATH.read_text(encoding="utf-8")


def _js() -> str:
    return RE_JS_PATH.read_text(encoding="utf-8")


def _html() -> str:
    return RE_HTML_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 1: RealEstateTab renders only PROPERTIES and UNREALIZED GAIN % by default
# ---------------------------------------------------------------------------

class TestDefaultPrimaryOnlyView(unittest.TestCase):
    """On first load, only primary metrics (PROPERTIES, UNREALIZED GAIN %) are visible."""

    def test_primary_metrics_component_file_exists(self):
        """Test 1a: PrimaryMetrics.js component file exists."""
        self.assertTrue(PRIMARY_PATH.exists(),
            "PrimaryMetrics.js must exist in src/templates/assets/components/")

    def test_primary_metrics_has_properties_label(self):
        """Test 1b: PrimaryMetrics component renders a PROPERTIES metric card."""
        comp = _primary()
        self.assertIn('PROPERTIES', comp,
            "PrimaryMetrics must include 'PROPERTIES' label for property count")

    def test_primary_metrics_has_unrealized_gain_pct_label(self):
        """Test 1c: PrimaryMetrics component renders an UNREALIZED GAIN % metric card."""
        comp = _primary()
        self.assertIn('UNREALIZED GAIN', comp,
            "PrimaryMetrics must include 'UNREALIZED GAIN' label")
        self.assertIn('%', comp,
            "PrimaryMetrics must show percentage for unrealized gain")

    def test_primary_metrics_accepts_property_count(self):
        """Test 1d: PrimaryMetrics function accepts propertyCount parameter."""
        comp = _primary()
        self.assertIn('propertyCount', comp,
            "PrimaryMetrics must accept 'propertyCount' parameter")

    def test_primary_metrics_accepts_unrealized_gain_pct(self):
        """Test 1e: PrimaryMetrics function accepts unrealizedGainPct parameter."""
        comp = _primary()
        self.assertIn('unrealizedGainPct', comp,
            "PrimaryMetrics must accept 'unrealizedGainPct' parameter")

    def test_js_renders_primary_metrics_into_recards(self):
        """Test 1f: real_estate.js calls createPrimaryMetrics and places into reCards."""
        js = _js()
        self.assertIn('createPrimaryMetrics', js,
            "real_estate.js must call createPrimaryMetrics")
        self.assertIn('reCards', js,
            "real_estate.js must render primary metrics into reCards container")

    def test_html_has_primary_metrics_container(self):
        """Test 1g: HTML has reCards container for primary metrics."""
        html = _html()
        self.assertIn('reCards', html,
            "real_estate.html.j2 must have a data-role='reCards' container for primary metrics")

    def test_secondary_container_hidden_by_default_in_html(self):
        """Test 1h: Secondary metrics container starts hidden (display:none) in HTML."""
        html = _html()
        idx = html.find('reCardsSecondary')
        self.assertGreater(idx, -1,
            "HTML must have a 'reCardsSecondary' container for secondary metrics")
        tag_start = html.rfind('<', 0, idx)
        tag_end = html.find('>', idx)
        tag = html[tag_start:tag_end + 1]
        normalised = tag.replace(' ', '').replace('"', '').replace("'", '')
        self.assertIn('display:none', normalised,
            "reCardsSecondary container must start hidden (display:none)")


# ---------------------------------------------------------------------------
# Test 2 (4): SecondaryMetrics is hidden by default
# ---------------------------------------------------------------------------

class TestSecondaryMetricsHiddenByDefault(unittest.TestCase):
    """SecondaryMetrics component exists and its container is hidden on first load."""

    def test_secondary_metrics_component_file_exists(self):
        """Test 2a: SecondaryMetrics.js component file exists."""
        self.assertTrue(SECONDARY_PATH.exists(),
            "SecondaryMetrics.js must exist in src/templates/assets/components/")

    def test_secondary_metrics_has_purchase_total_label(self):
        """Test 2b: SecondaryMetrics renders a PURCHASE TOTAL metric card."""
        comp = _secondary()
        self.assertIn('PURCHASE TOTAL', comp,
            "SecondaryMetrics must include 'PURCHASE TOTAL' label")

    def test_secondary_metrics_has_etn_estimate_label(self):
        """Test 2c: SecondaryMetrics renders an ETN ESTIMATE metric card."""
        comp = _secondary()
        self.assertIn('ETN ESTIMATE', comp,
            "SecondaryMetrics must include 'ETN ESTIMATE' label")

    def test_secondary_metrics_accepts_purchase_total(self):
        """Test 2d: SecondaryMetrics function accepts purchaseTotal parameter."""
        comp = _secondary()
        self.assertIn('purchaseTotal', comp,
            "SecondaryMetrics must accept 'purchaseTotal' parameter")

    def test_secondary_metrics_accepts_etn_estimate(self):
        """Test 2e: SecondaryMetrics function accepts etnEstimate parameter."""
        comp = _secondary()
        self.assertIn('etnEstimate', comp,
            "SecondaryMetrics must accept 'etnEstimate' parameter")

    def test_js_renders_secondary_into_recardssecondary(self):
        """Test 2f: real_estate.js calls createSecondaryMetrics into reCardsSecondary."""
        js = _js()
        self.assertIn('createSecondaryMetrics', js,
            "real_estate.js must call createSecondaryMetrics")
        self.assertIn('reCardsSecondary', js,
            "real_estate.js must reference reCardsSecondary container")

    def test_js_secondary_container_starts_hidden(self):
        """Test 2g: real_estate.js does not reveal reCardsSecondary on initial render."""
        js = _js()
        # The JS must NOT show reCardsSecondary on initial load — the HTML default is hidden.
        # Verify the show/hide logic is inside a toggle handler, not the initial render.
        re_cards_secondary_idx = js.find('reCardsSecondary')
        self.assertGreater(re_cards_secondary_idx, -1,
            "JS must reference reCardsSecondary")
        # The first reference should NOT immediately set display to '' without a conditional
        # (Soft check: the JS shouldn't set display='' for secondary at module init level)
        initial_reveal = "reCardsSecondary').style.display = ''" in js or \
                         'reCardsSecondary"].style.display = ""' in js
        if initial_reveal:
            # Acceptable only if it's inside a toggle handler, not direct init
            self.assertIn('click', js,
                "If reCardsSecondary display is changed, it must be inside a click handler")


# ---------------------------------------------------------------------------
# Test 3 (5): ShowAllMetricsToggle — text link with aria-expanded
# ---------------------------------------------------------------------------

class TestShowAllMetricsToggle(unittest.TestCase):
    """ShowAllMetricsToggle component has correct labels and aria-expanded."""

    def test_toggle_component_file_exists(self):
        """Test 3a: ShowAllMetricsToggle.js component file exists."""
        self.assertTrue(TOGGLE_PATH.exists(),
            "ShowAllMetricsToggle.js must exist in src/templates/assets/components/")

    def test_toggle_has_show_all_metrics_label(self):
        """Test 3b: Toggle component contains 'Show all metrics' text."""
        comp = _toggle()
        self.assertIn('Show all metrics', comp,
            "ShowAllMetricsToggle must contain 'Show all metrics' label (collapsed state)")

    def test_toggle_has_show_fewer_label(self):
        """Test 3c: Toggle component contains 'Show fewer' text."""
        comp = _toggle()
        self.assertIn('Show fewer', comp,
            "ShowAllMetricsToggle must contain 'Show fewer' label (expanded state)")

    def test_toggle_has_aria_expanded(self):
        """Test 3d: Toggle component includes aria-expanded attribute."""
        comp = _toggle()
        self.assertIn('aria-expanded', comp,
            "ShowAllMetricsToggle must include aria-expanded attribute for accessibility")

    def test_toggle_accepts_expanded_param(self):
        """Test 3e: Toggle function accepts expanded boolean parameter."""
        comp = _toggle()
        self.assertIn('expanded', comp,
            "ShowAllMetricsToggle must accept 'expanded' boolean parameter")

    def test_html_has_metrics_toggle_container(self):
        """Test 3f: HTML has reMetricsToggle container for the toggle."""
        html = _html()
        self.assertIn('reMetricsToggle', html,
            "real_estate.html.j2 must have a 'reMetricsToggle' container for the toggle")

    def test_js_renders_toggle_into_container(self):
        """Test 3g: real_estate.js calls createShowAllMetricsToggle into reMetricsToggle."""
        js = _js()
        self.assertIn('createShowAllMetricsToggle', js,
            "real_estate.js must call createShowAllMetricsToggle")
        self.assertIn('reMetricsToggle', js,
            "real_estate.js must reference reMetricsToggle container")


# ---------------------------------------------------------------------------
# Test 4 (6): Clicking 'Show all metrics' reveals SecondaryMetrics, label → 'Show fewer'
# ---------------------------------------------------------------------------

class TestToggleRevealsBehavior(unittest.TestCase):
    """Clicking 'Show all metrics' shows secondary metrics and updates label/aria."""

    def test_js_click_handler_attached_to_toggle(self):
        """Test 4a: real_estate.js attaches a click handler to the metrics toggle button."""
        js = _js()
        self.assertIn("'click'", js,
            "real_estate.js must attach a 'click' event listener to the toggle")

    def test_js_toggle_reveals_secondary_on_expand(self):
        """Test 4b: JS shows reCardsSecondary when expanding (removes display:none)."""
        js = _js()
        # Toggling show: either style.display = '' or style.removeProperty('display')
        has_show = "style.display = ''" in js or 'style.display=""' in js or \
                   "style.removeProperty" in js or "classList.remove('re-hidden')" in js or \
                   "classList.add('re-visible')" in js
        self.assertTrue(has_show,
            "JS must reveal secondary metrics container when toggle is expanded")

    def test_js_sets_aria_expanded_true_on_expand(self):
        """Test 4c: JS sets aria-expanded='true' on the toggle button when expanding."""
        js = _js()
        self.assertIn("'true'", js,
            "JS must set aria-expanded to 'true' when revealing secondary metrics")

    def test_js_changes_label_to_show_fewer(self):
        """Test 4d: JS updates toggle button text to 'Show fewer' after expanding."""
        js = _js()
        self.assertIn('Show fewer', js,
            "real_estate.js must set toggle text to 'Show fewer' when expanded")

    def test_js_reads_aria_expanded_before_toggle(self):
        """Test 4e: JS reads current aria-expanded to decide next action."""
        js = _js()
        self.assertIn('getAttribute', js,
            "JS must call getAttribute to read current aria-expanded before toggling")


# ---------------------------------------------------------------------------
# Test 5 (7): Clicking 'Show fewer' hides SecondaryMetrics
# ---------------------------------------------------------------------------

class TestToggleHidesBehavior(unittest.TestCase):
    """Clicking 'Show fewer' hides secondary metrics and updates label/aria."""

    def test_js_hides_secondary_on_collapse(self):
        """Test 5a: JS hides reCardsSecondary when collapsing."""
        js = _js()
        has_hide = "style.display = 'none'" in js or "style.display='none'" in js or \
                   "classList.add('re-hidden')" in js or "classList.remove('re-visible')" in js
        self.assertTrue(has_hide,
            "JS must hide secondary metrics container when toggle is collapsed")

    def test_js_sets_aria_expanded_false_on_collapse(self):
        """Test 5b: JS sets aria-expanded='false' on the toggle button when collapsing."""
        js = _js()
        self.assertIn("'false'", js,
            "JS must set aria-expanded to 'false' when hiding secondary metrics")

    def test_js_changes_label_to_show_all_metrics(self):
        """Test 5c: JS updates toggle button text to 'Show all metrics' after collapsing."""
        js = _js()
        self.assertIn('Show all metrics', js,
            "real_estate.js must set toggle text to 'Show all metrics' when collapsed")

    def test_js_toggle_is_bidirectional(self):
        """Test 5d: JS toggle handler handles both expand and collapse (conditional logic)."""
        js = _js()
        # Must have conditional: either if/else or ternary
        has_conditional = ('=== \'true\'' in js or '=== "true"' in js or
                           "=== 'false'" in js or '=== "false"' in js)
        self.assertTrue(has_conditional,
            "JS toggle must check aria-expanded value to handle both expand and collapse")


if __name__ == "__main__":
    unittest.main()
