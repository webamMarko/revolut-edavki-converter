"""TDD tests for SAA-550: Property Details accordion with ARIA and animation.

Spec: wrap existing property table in a collapsible 'Property Details' accordion
section, collapsed by default. CSS max-height transition (~200-300ms). Chevron
rotates 90° on expand. Full WAI-ARIA: role=button, aria-expanded, aria-controls,
role=region, aria-labelledby. Keyboard: Enter/Space to toggle.
"""
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RE_JS_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "sections" / "real_estate.js"
RE_HTML_PATH = PROJECT_ROOT / "src" / "templates" / "sections" / "real_estate.html.j2"
CSS_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "styles.css"


def _js() -> str:
    return RE_JS_PATH.read_text(encoding="utf-8")


def _html() -> str:
    return RE_HTML_PATH.read_text(encoding="utf-8")


def _css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 1: Property table NOT visible on initial render
# ---------------------------------------------------------------------------

class TestInitialCollapsedState(unittest.TestCase):
    """Property table must be hidden on first load — accordion starts collapsed."""

    def test_panel_starts_without_is_open(self):
        """Test 1a: property-details-panel does NOT have is-open class in HTML (collapsed by default)."""
        html = _html()
        panel_idx = html.find('property-details-panel')
        self.assertGreater(panel_idx, -1, "property-details-panel must exist in real_estate.html.j2")
        # Find the div tag that contains the panel id
        tag_start = html.rfind('<', 0, panel_idx)
        tag_end = html.find('>', panel_idx)
        tag = html[tag_start:tag_end + 1]
        self.assertNotIn('is-open', tag,
            "property-details-panel must NOT have is-open class on initial render")

    def test_header_starts_aria_expanded_false(self):
        """Test 1b: accordion header has aria-expanded='false' in HTML (table hidden on load)."""
        html = _html()
        self.assertIn('aria-expanded="false"', html,
            "property-details-header must have aria-expanded='false' as initial state")

    def test_property_table_is_inside_panel(self):
        """Test 1c: reTable data-role is inside the property-details-panel, not directly in section."""
        html = _html()
        panel_idx = html.find('id="property-details-panel"')
        self.assertGreater(panel_idx, -1, "property-details-panel must exist")
        table_idx = html.find('data-role="reTable"')
        self.assertGreater(table_idx, -1, "reTable must exist")
        self.assertGreater(table_idx, panel_idx,
            "reTable must be inside property-details-panel (appears after panel opening tag)")


# ---------------------------------------------------------------------------
# Test 2: Accordion HTML structure — ARIA attributes
# ---------------------------------------------------------------------------

class TestAccordionHTMLStructure(unittest.TestCase):
    """Accordion header and panel have correct WAI-ARIA attributes."""

    def test_header_has_role_button(self):
        """Test 2a: accordion header has role='button'."""
        html = _html()
        self.assertIn('role="button"', html,
            "Accordion header must have role='button'")

    def test_header_has_aria_controls(self):
        """Test 2b: header aria-controls points to property-details-panel."""
        html = _html()
        self.assertIn('aria-controls="property-details-panel"', html,
            "Header must have aria-controls='property-details-panel'")

    def test_header_has_correct_id(self):
        """Test 2c: accordion header has id='property-details-header'."""
        html = _html()
        self.assertIn('id="property-details-header"', html,
            "Accordion header must have id='property-details-header'")

    def test_header_has_tabindex_zero(self):
        """Test 2d: accordion header has tabindex=0 for keyboard focus."""
        html = _html()
        self.assertIn('tabindex="0"', html,
            "Accordion header must have tabindex='0'")

    def test_panel_has_role_region(self):
        """Test 2e: accordion panel has role='region'."""
        html = _html()
        self.assertIn('role="region"', html,
            "Accordion panel must have role='region'")

    def test_panel_has_aria_labelledby(self):
        """Test 2f: panel aria-labelledby references property-details-header."""
        html = _html()
        self.assertIn('aria-labelledby="property-details-header"', html,
            "Panel must have aria-labelledby='property-details-header'")

    def test_panel_has_correct_id(self):
        """Test 2g: panel has id='property-details-panel'."""
        html = _html()
        self.assertIn('id="property-details-panel"', html,
            "Accordion panel must have id='property-details-panel'")

    def test_chevron_indicator_present(self):
        """Test 2h: chevron indicator element is present in the header."""
        html = _html()
        self.assertIn('property-details-chevron', html,
            "A chevron element with class 'property-details-chevron' must be in the header")


# ---------------------------------------------------------------------------
# Test 3: Clicking expands — JS toggle logic (aria-expanded=true, is-open)
# ---------------------------------------------------------------------------

class TestClickExpands(unittest.TestCase):
    """JS toggle sets aria-expanded=true and adds is-open class on click."""

    def test_js_toggles_aria_expanded(self):
        """Test 3a: JS reads and sets aria-expanded on toggle."""
        js = _js()
        self.assertIn('aria-expanded', js,
            "real_estate.js must read/set aria-expanded in toggle logic")
        self.assertIn("'true'", js,
            "JS must set aria-expanded to 'true' when expanding")

    def test_js_adds_is_open_class(self):
        """Test 3b: JS adds is-open class to panel on expand."""
        js = _js()
        self.assertIn('is-open', js,
            "JS must use 'is-open' class on property-details-panel")
        self.assertIn('classList', js,
            "JS must use classList to toggle is-open class")

    def test_js_click_listener_on_header(self):
        """Test 3c: JS attaches a click event listener to the accordion header."""
        js = _js()
        self.assertIn("'click'", js,
            "JS must attach a click event listener for the accordion toggle")

    def test_js_references_property_details_header(self):
        """Test 3d: JS references property-details-header element."""
        js = _js()
        self.assertIn('property-details-header', js,
            "JS must reference 'property-details-header' to attach toggle behavior")

    def test_js_references_property_details_panel(self):
        """Test 3e: JS references property-details-panel element."""
        js = _js()
        self.assertIn('property-details-panel', js,
            "JS must reference 'property-details-panel' for expand/collapse")


# ---------------------------------------------------------------------------
# Test 4: Clicking again collapses — aria-expanded=false, is-open removed
# ---------------------------------------------------------------------------

class TestClickCollapses(unittest.TestCase):
    """JS toggle sets aria-expanded=false and removes is-open class on second click."""

    def test_js_sets_aria_expanded_false_on_collapse(self):
        """Test 4a: JS sets aria-expanded='false' when collapsing."""
        js = _js()
        self.assertIn("'false'", js,
            "JS must set aria-expanded to 'false' when collapsing")

    def test_js_removes_is_open_on_collapse(self):
        """Test 4b: JS removes is-open class or uses classList.toggle."""
        js = _js()
        has_toggle = 'classList.toggle' in js
        has_remove = 'classList.remove' in js
        self.assertTrue(has_toggle or has_remove,
            "JS must remove is-open class on collapse via classList.toggle or classList.remove")

    def test_js_reads_current_state_before_toggling(self):
        """Test 4c: JS reads current aria-expanded to determine next state."""
        js = _js()
        self.assertIn('getAttribute', js,
            "JS must read current aria-expanded value via getAttribute before toggling")


# ---------------------------------------------------------------------------
# Test 5: Keyboard Enter/Space toggles accordion
# ---------------------------------------------------------------------------

class TestKeyboardToggle(unittest.TestCase):
    """Enter and Space keys trigger the accordion toggle."""

    def test_js_keydown_listener_attached(self):
        """Test 5a: JS attaches keydown event listener to accordion header."""
        js = _js()
        self.assertIn('keydown', js,
            "JS must attach a 'keydown' event listener to the accordion header")

    def test_js_enter_key_triggers_toggle(self):
        """Test 5b: JS handles Enter key to toggle accordion."""
        js = _js()
        self.assertIn('Enter', js,
            "JS must check for 'Enter' key in keydown handler")

    def test_js_space_key_triggers_toggle(self):
        """Test 5c: JS handles Space key to toggle accordion."""
        js = _js()
        space_variants = ['" "', "' '", '"Space"', "'Space'"]
        found = any(v in js for v in space_variants)
        self.assertTrue(found,
            "JS must check for Space key (' ' or 'Space') in keydown handler")

    def test_js_prevents_default_on_space(self):
        """Test 5d: JS calls preventDefault() to stop page scroll on Space."""
        js = _js()
        self.assertIn('preventDefault', js,
            "JS must call event.preventDefault() in keydown handler to prevent page scroll on Space")


# ---------------------------------------------------------------------------
# CSS: Animation, chevron rotation, overflow hidden
# ---------------------------------------------------------------------------

class TestCSSAnimation(unittest.TestCase):
    """CSS provides max-height transition and chevron rotation."""

    def test_property_details_panel_css_exists(self):
        """CSS: .property-details-panel class is defined."""
        css = _css()
        self.assertIn('property-details-panel', css,
            ".property-details-panel must be defined in styles.css")

    def test_property_details_panel_transition(self):
        """CSS: .property-details-panel has a CSS transition."""
        css = _css()
        idx = css.find('property-details-panel')
        self.assertGreater(idx, -1)
        # Check within a reasonable range after the class definition
        snippet = css[idx:idx + 400]
        self.assertIn('transition', snippet,
            ".property-details-panel must have a CSS transition for animation")

    def test_property_details_panel_overflow_hidden(self):
        """CSS: .property-details-panel has overflow:hidden during transition."""
        css = _css()
        idx = css.find('property-details-panel')
        snippet = css[idx:idx + 400]
        self.assertIn('overflow', snippet,
            ".property-details-panel must have overflow property for animation clipping")

    def test_property_details_panel_is_open_state(self):
        """CSS: .property-details-panel.is-open expands the panel."""
        css = _css()
        self.assertIn('property-details-panel', css)
        self.assertIn('is-open', css,
            "CSS must define the .is-open expanded state for the panel")

    def test_chevron_rotation_on_expand(self):
        """CSS: chevron rotates 90 degrees when aria-expanded is true."""
        css = _css()
        self.assertIn('property-details-chevron', css,
            ".property-details-chevron must be styled in CSS")
        # Chevron rotation can be via aria-expanded selector or .is-open modifier
        has_rotate = 'rotate(90' in css
        self.assertTrue(has_rotate,
            "CSS must rotate the chevron 90 degrees when accordion is expanded")


if __name__ == "__main__":
    unittest.main()
