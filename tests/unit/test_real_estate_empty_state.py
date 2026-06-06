"""TDD tests for SAA-551: Real Estate Tab empty state with Add Property CTA.

Spec: when no properties, show 'No properties yet' message and 'Add Property'
CTA button linking to the property management page. When properties exist,
empty state is NOT shown — normal metrics/chart view renders.
"""
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
COMPONENT_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "components" / "RealEstateEmptyState.js"
RE_JS_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "sections" / "real_estate.js"
RE_HTML_PATH = PROJECT_ROOT / "src" / "templates" / "sections" / "real_estate.html.j2"


def _component() -> str:
    return COMPONENT_PATH.read_text(encoding="utf-8")


def _js() -> str:
    return RE_JS_PATH.read_text(encoding="utf-8")


def _html() -> str:
    return RE_HTML_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 1: Empty state shown when no properties
# ---------------------------------------------------------------------------

class TestEmptyStateNoProperties(unittest.TestCase):
    """When no properties exist, show friendly message and Add Property button."""

    def test_component_file_exists(self):
        """Test 1a: RealEstateEmptyState component file exists."""
        self.assertTrue(COMPONENT_PATH.exists(),
            "RealEstateEmptyState.js must exist in src/templates/assets/components/")

    def test_component_has_no_properties_message(self):
        """Test 1b: component contains 'No properties yet' message."""
        comp = _component()
        self.assertIn('No properties yet', comp,
            "RealEstateEmptyState must contain 'No properties yet' message")

    def test_component_has_add_property_button(self):
        """Test 1c: component renders an 'Add Property' CTA."""
        comp = _component()
        self.assertIn('Add Property', comp,
            "RealEstateEmptyState must contain 'Add Property' CTA text")

    def test_html_has_empty_state_container(self):
        """Test 1d: real_estate.html.j2 has a reEmptyState container element."""
        html = _html()
        self.assertIn('reEmptyState', html,
            "real_estate.html.j2 must have a data-role='reEmptyState' container")

    def test_js_references_empty_state_container(self):
        """Test 1e: real_estate.js references reEmptyState to show empty state."""
        js = _js()
        self.assertIn('reEmptyState', js,
            "real_estate.js must reference reEmptyState to render empty state")

    def test_js_calls_empty_state_component(self):
        """Test 1f: real_estate.js calls createRealEstateEmptyState when no properties."""
        js = _js()
        self.assertIn('createRealEstateEmptyState', js,
            "real_estate.js must call createRealEstateEmptyState when no properties")


# ---------------------------------------------------------------------------
# Test 2: 'Add Property' CTA links to property management page
# ---------------------------------------------------------------------------

class TestAddPropertyCTA(unittest.TestCase):
    """'Add Property' CTA must link to the existing property management page."""

    def test_component_has_property_management_url(self):
        """Test 2a: component includes /properties/new URL."""
        comp = _component()
        self.assertIn('/properties/new', comp,
            "RealEstateEmptyState must link to /properties/new (property management page)")

    def test_component_accepts_addPropertyUrl_param(self):
        """Test 2b: component function accepts addPropertyUrl parameter."""
        comp = _component()
        self.assertIn('addPropertyUrl', comp,
            "RealEstateEmptyState must accept addPropertyUrl parameter")

    def test_component_cta_is_anchor_with_href(self):
        """Test 2c: CTA is rendered as an anchor tag with href attribute."""
        comp = _component()
        self.assertIn('href', comp,
            "RealEstateEmptyState CTA must be an anchor tag with href")

    def test_js_passes_property_url_to_component(self):
        """Test 2d: real_estate.js supplies add property URL to createRealEstateEmptyState."""
        js = _js()
        has_hardcoded = '/properties/new' in js
        has_data_url = 'add_property_url' in js
        self.assertTrue(has_hardcoded or has_data_url,
            "real_estate.js must supply /properties/new (or RE.add_property_url) to the component")


# ---------------------------------------------------------------------------
# Test 3: When properties exist, empty state is NOT shown, metrics/chart render
# ---------------------------------------------------------------------------

class TestEmptyStateNotShownWhenPropertiesExist(unittest.TestCase):
    """When properties exist, empty state must be hidden; metrics/chart must render."""

    def test_js_has_conditional_else_for_empty_state(self):
        """Test 3a: JS has else branch — empty state only shown when no properties."""
        js = _js()
        self.assertIn('else', js,
            "real_estate.js must have conditional else branch for empty state vs content")

    def test_js_empty_state_follows_properties_check(self):
        """Test 3b: reEmptyState reference appears in else branch of properties length check."""
        js = _js()
        props_idx = js.find('properties.length')
        if props_idx == -1:
            props_idx = js.find('RE.properties')
        empty_idx = js.find('reEmptyState')
        self.assertGreater(props_idx, -1, "JS must check properties existence")
        self.assertGreater(empty_idx, -1, "JS must reference reEmptyState")
        else_idx = js.find('else', props_idx)
        self.assertGreater(else_idx, -1,
            "JS must have an else branch after properties check for empty state")

    def test_js_metrics_rendered_only_when_properties_exist(self):
        """Test 3c: reCards (metrics) and reChart are inside the properties-exist branch."""
        js = _js()
        props_idx = js.find('properties.length')
        if props_idx == -1:
            props_idx = js.find('RE.properties')
        re_cards_idx = js.find('reCards')
        re_chart_idx = js.find('reChart')
        self.assertGreater(props_idx, -1, "JS must check properties")
        self.assertGreater(re_cards_idx, props_idx,
            "reCards (metrics) must appear inside the properties-exist branch")
        self.assertGreater(re_chart_idx, props_idx,
            "reChart must appear inside the properties-exist branch")

    def test_html_empty_state_hidden_by_default(self):
        """Test 3d: reEmptyState container starts hidden in HTML (display:none)."""
        html = _html()
        idx = html.find('reEmptyState')
        self.assertGreater(idx, -1, "reEmptyState must exist in HTML")
        tag_start = html.rfind('<', 0, idx)
        tag_end = html.find('>', idx)
        tag = html[tag_start:tag_end + 1]
        normalised = tag.replace(' ', '').replace('"', '').replace("'", '')
        self.assertIn('display:none', normalised,
            "reEmptyState container must start hidden (display:none)")


if __name__ == "__main__":
    unittest.main()
