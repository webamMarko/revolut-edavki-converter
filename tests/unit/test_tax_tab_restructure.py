"""TDD tests for SAA-582: Tax Tab — Restructure to 2 sub-tabs (Summary + Advanced).

Spec: restructure TaxTab from 4 sub-tabs (Summary, Calendar, Smart Sell, File)
to 2 sub-tabs: "Summary" and "Advanced". Summary shows only 4 text-based tax
metrics (realized gains/losses YTD, estimated tax liability, unrealized gains,
tax-loss harvesting opportunities). No charts or timelines on Summary.
AdvancedToolsLink at bottom of Summary switches to Advanced tab on click.
"""
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
REPORT_HTML = PROJECT_ROOT / "src" / "templates" / "report.html.j2"
TAX_METRICS_HTML = PROJECT_ROOT / "src" / "templates" / "sections" / "tax_metrics_summary.html.j2"
TAX_METRICS_JS = PROJECT_ROOT / "src" / "templates" / "assets" / "sections" / "tax_metrics_summary.js"
NAV_JS = PROJECT_ROOT / "src" / "templates" / "assets" / "nav.js"
CSS_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "styles.css"


def _report_html() -> str:
    return REPORT_HTML.read_text(encoding="utf-8")


def _tax_metrics_html() -> str:
    return TAX_METRICS_HTML.read_text(encoding="utf-8")


def _tax_metrics_js() -> str:
    return TAX_METRICS_JS.read_text(encoding="utf-8")


def _nav_js() -> str:
    return NAV_JS.read_text(encoding="utf-8")


def _css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 1: TaxTab renders exactly 2 sub-tabs labeled "Summary" and "Advanced"
# ---------------------------------------------------------------------------

class TestTaxTabTwoSubtabs(unittest.TestCase):
    """TaxTab must have exactly 2 sub-tabs: Summary and Advanced."""

    def test_summary_subtab_button_exists(self):
        """Test 1a: Summary sub-tab button labeled 'Summary' exists in report HTML."""
        html = _report_html()
        self.assertIn('data-subtab="summary"', html,
            "report.html.j2 must have a sub-tab button with data-subtab='summary'")
        self.assertIn('>Summary<', html,
            "Summary sub-tab button must be labeled 'Summary'")

    def test_advanced_subtab_button_exists(self):
        """Test 1b: Advanced sub-tab button labeled 'Advanced' exists in report HTML."""
        html = _report_html()
        self.assertIn('data-subtab="advanced"', html,
            "report.html.j2 must have a sub-tab button with data-subtab='advanced'")
        self.assertIn('>Advanced<', html,
            "Advanced sub-tab button must be labeled 'Advanced'")

    def test_no_calendar_subtab(self):
        """Test 1c: Calendar sub-tab is not a top-level sub-tab button anymore."""
        html = _report_html()
        self.assertNotIn('data-subtab="calendar"', html,
            "Calendar must not be a top-level sub-tab button (it belongs in Advanced accordion)")

    def test_no_smart_sell_subtab(self):
        """Test 1d: Smart Sell sub-tab is not a top-level sub-tab button anymore."""
        html = _report_html()
        self.assertNotIn('data-subtab="smart-sell"', html,
            "Smart Sell must not be a top-level sub-tab button")

    def test_no_file_subtab(self):
        """Test 1e: File sub-tab is not a top-level sub-tab button anymore."""
        html = _report_html()
        self.assertNotIn('data-subtab="file"', html,
            "File must not be a top-level sub-tab button")

    def test_exactly_two_subtab_panels(self):
        """Test 1f: Exactly 2 subtab panel divs exist (summary and advanced)."""
        html = _report_html()
        self.assertIn('data-subtab-panel="summary"', html,
            "Summary subtab panel must exist")
        self.assertIn('data-subtab-panel="advanced"', html,
            "Advanced subtab panel must exist")
        self.assertNotIn('data-subtab-panel="calendar"', html,
            "Calendar subtab panel must not exist as a top-level panel")
        self.assertNotIn('data-subtab-panel="smart-sell"', html,
            "Smart Sell subtab panel must not exist as a top-level panel")
        self.assertNotIn('data-subtab-panel="file"', html,
            "File subtab panel must not exist as a top-level panel")


# ---------------------------------------------------------------------------
# Test 2: TaxTab defaults to Summary sub-tab on load
# ---------------------------------------------------------------------------

class TestTaxTabDefaultsToSummary(unittest.TestCase):
    """Summary sub-tab must be active by default when the page loads."""

    def test_summary_subtab_button_is_active(self):
        """Test 2a: Summary sub-tab button has 'active' class in HTML (default active tab)."""
        html = _report_html()
        tax_page_start = html.find('id="page-tax"')
        self.assertGreater(tax_page_start, -1, "page-tax div must exist")
        tax_page_section = html[tax_page_start:tax_page_start + 2000]
        summary_btn_idx = tax_page_section.find('data-subtab="summary"')
        self.assertGreater(summary_btn_idx, -1)
        btn_tag_start = tax_page_section.rfind('<', 0, summary_btn_idx)
        btn_tag_end = tax_page_section.find('>', summary_btn_idx)
        btn_tag = tax_page_section[btn_tag_start:btn_tag_end + 1]
        self.assertIn('active', btn_tag,
            "Summary sub-tab button must have 'active' class (default tab)")

    def test_advanced_subtab_panel_hidden_by_default(self):
        """Test 2b: Advanced sub-tab panel is hidden by default (display:none)."""
        html = _report_html()
        advanced_panel_idx = html.find('data-subtab-panel="advanced"')
        self.assertGreater(advanced_panel_idx, -1)
        tag_start = html.rfind('<', 0, advanced_panel_idx)
        tag_end = html.find('>', advanced_panel_idx)
        tag = html[tag_start:tag_end + 1]
        self.assertIn('display:none', tag.replace(' ', '').replace('"', '').replace("'", ''),
            "Advanced subtab panel must be hidden by default (style display:none)")

    def test_nav_js_handles_summary_default(self):
        """Test 2c: nav.js switch logic handles 'summary' tab correctly."""
        js = _nav_js()
        self.assertIn('switchTaxSubtab', js,
            "nav.js must define switchTaxSubtab function")
        self.assertIn("'summary'", js,
            "nav.js must reference 'summary' tab")


# ---------------------------------------------------------------------------
# Test 3: TaxSummary renders 4 text metrics
# ---------------------------------------------------------------------------

class TestTaxMetricsSummaryComponent(unittest.TestCase):
    """TaxMetricsSummary component must render 4 text-based tax metrics."""

    def test_tax_metrics_summary_html_exists(self):
        """Test 3a: tax_metrics_summary.html.j2 template file exists."""
        self.assertTrue(TAX_METRICS_HTML.exists(),
            "src/templates/sections/tax_metrics_summary.html.j2 must exist")

    def test_tax_metrics_summary_js_exists(self):
        """Test 3b: tax_metrics_summary.js file exists."""
        self.assertTrue(TAX_METRICS_JS.exists(),
            "src/templates/assets/sections/tax_metrics_summary.js must exist")

    def test_tax_metrics_summary_included_in_report(self):
        """Test 3c: tax_metrics_summary is included in report.html.j2."""
        html = _report_html()
        self.assertIn('tax_metrics_summary', html,
            "report.html.j2 must include tax_metrics_summary template or script")

    def test_realized_gains_metric_present(self):
        """Test 3d: Realized gains/losses metric is present in TaxMetricsSummary."""
        html = _tax_metrics_html()
        html_lower = html.lower()
        self.assertTrue(
            'realized' in html_lower or 'data-role="taxSummaryRealizedGains"' in html,
            "TaxMetricsSummary must contain a realized gains/losses metric element"
        )

    def test_tax_liability_metric_present(self):
        """Test 3e: Estimated tax liability metric is present in TaxMetricsSummary."""
        html = _tax_metrics_html()
        self.assertTrue(
            'taxliability' in html.lower().replace('-', '').replace('_', '') or
            'tax-liability' in html.lower() or
            'tax_liability' in html.lower() or
            'taxLiability' in html,
            "TaxMetricsSummary must contain an estimated tax liability metric element"
        )

    def test_unrealized_gains_metric_present(self):
        """Test 3f: Unrealized gains metric is present in TaxMetricsSummary."""
        html = _tax_metrics_html()
        self.assertIn('unrealized', html.lower(),
            "TaxMetricsSummary must contain an unrealized gains metric element")

    def test_tax_loss_harvesting_metric_present(self):
        """Test 3g: Tax-loss harvesting opportunities metric is present in TaxMetricsSummary."""
        html = _tax_metrics_html()
        self.assertIn('harvest', html.lower(),
            "TaxMetricsSummary must contain a tax-loss harvesting opportunities metric element")

    def test_four_metric_roles_in_js(self):
        """Test 3h: JS populates all 4 metric values."""
        js = _tax_metrics_js()
        has_realized = 'realized' in js.lower()
        has_tax = 'tax' in js.lower() and 'liability' in js.lower() or 'totalTax' in js or 'total_tax' in js
        has_unrealized = 'unrealized' in js.lower()
        has_harvest = 'harvest' in js.lower()
        self.assertTrue(has_realized,
            "tax_metrics_summary.js must reference realized gains/losses data")
        self.assertTrue(has_tax,
            "tax_metrics_summary.js must reference tax liability data")
        self.assertTrue(has_unrealized,
            "tax_metrics_summary.js must reference unrealized gains data")
        self.assertTrue(has_harvest,
            "tax_metrics_summary.js must reference harvest opportunities data")


# ---------------------------------------------------------------------------
# Test 4: TaxSummary does NOT render TaxBracketTimeline or charts
# ---------------------------------------------------------------------------

class TestTaxSummaryNoTimeline(unittest.TestCase):
    """Summary sub-tab panel must not include TaxBracketTimeline or chart sections."""

    def test_tax_timeline_not_in_summary_panel(self):
        """Test 4a: tax_timeline template is NOT included in the Summary sub-tab panel."""
        html = _report_html()
        summary_panel_start = html.find('data-subtab-panel="summary"')
        self.assertGreater(summary_panel_start, -1)
        advanced_panel_start = html.find('data-subtab-panel="advanced"')
        self.assertGreater(advanced_panel_start, -1)
        summary_panel = html[summary_panel_start:advanced_panel_start]
        self.assertNotIn('tax_timeline', summary_panel,
            "tax_timeline.html.j2 must NOT be included in Summary sub-tab panel")

    def test_tax_timeline_in_advanced_panel(self):
        """Test 4b: tax_timeline template IS included in the Advanced sub-tab panel."""
        html = _report_html()
        advanced_panel_start = html.find('data-subtab-panel="advanced"')
        self.assertGreater(advanced_panel_start, -1)
        # Look for it anywhere after the advanced panel start
        rest = html[advanced_panel_start:]
        self.assertIn('tax_timeline', rest,
            "tax_timeline.html.j2 must be in the Advanced sub-tab panel")

    def test_no_canvas_or_chart_in_summary_panel(self):
        """Test 4c: No <canvas> or chart elements in Summary sub-tab panel content."""
        html = _report_html()
        summary_panel_start = html.find('data-subtab-panel="summary"')
        self.assertGreater(summary_panel_start, -1)
        advanced_panel_start = html.find('data-subtab-panel="advanced"')
        self.assertGreater(advanced_panel_start, -1)
        summary_panel = html[summary_panel_start:advanced_panel_start]
        self.assertNotIn('<canvas', summary_panel,
            "Summary panel must not contain <canvas> elements (no charts)")

    def test_tax_preview_not_in_summary_panel(self):
        """Test 4d: tax_preview (What-If simulator with charts) is NOT in Summary panel."""
        html = _report_html()
        summary_panel_start = html.find('data-subtab-panel="summary"')
        self.assertGreater(summary_panel_start, -1)
        advanced_panel_start = html.find('data-subtab-panel="advanced"')
        self.assertGreater(advanced_panel_start, -1)
        summary_panel = html[summary_panel_start:advanced_panel_start]
        self.assertNotIn('tax_preview', summary_panel,
            "tax_preview.html.j2 must NOT be in Summary sub-tab panel")


# ---------------------------------------------------------------------------
# Test 5: AdvancedToolsLink renders and calls tab-switch on click
# ---------------------------------------------------------------------------

class TestAdvancedToolsLink(unittest.TestCase):
    """AdvancedToolsLink must render in Summary panel and switch to Advanced on click."""

    def test_advanced_tools_link_in_summary_html(self):
        """Test 5a: AdvancedToolsLink element exists in the Summary sub-tab panel."""
        html = _report_html()
        summary_panel_start = html.find('data-subtab-panel="summary"')
        self.assertGreater(summary_panel_start, -1)
        advanced_panel_start = html.find('data-subtab-panel="advanced"')
        summary_panel = html[summary_panel_start:advanced_panel_start]
        has_link = (
            'taxAdvancedLink' in summary_panel or
            'advanced-link' in summary_panel or
            'advanced-tools-link' in summary_panel or
            'tax_metrics_summary' in summary_panel
        )
        self.assertTrue(has_link,
            "Summary panel must contain AdvancedToolsLink (via tax_metrics_summary include or direct element)")

    def test_advanced_tools_link_html_in_metrics(self):
        """Test 5b: AdvancedToolsLink element exists in tax_metrics_summary.html.j2."""
        html = _tax_metrics_html()
        has_link_element = (
            'taxAdvancedLink' in html or
            'advanced-link' in html or
            'advanced-tools-link' in html
        )
        self.assertTrue(has_link_element,
            "tax_metrics_summary.html.j2 must contain AdvancedToolsLink element")

    def test_advanced_tools_link_calls_switch_in_js(self):
        """Test 5c: JS wires AdvancedToolsLink click to switchTaxSubtab('advanced')."""
        js = _tax_metrics_js()
        self.assertTrue(
            "switchTaxSubtab" in js and "advanced" in js,
            "tax_metrics_summary.js must call switchTaxSubtab('advanced') when link is clicked"
        )

    def test_advanced_tools_link_onclick_switches_to_advanced(self):
        """Test 5d: The link element has a click handler that switches to 'advanced' tab."""
        js = _tax_metrics_js()
        has_click = 'addEventListener' in js or 'onclick' in js
        has_advanced = "'advanced'" in js or '"advanced"' in js
        self.assertTrue(has_click and has_advanced,
            "JS must attach click handler to AdvancedToolsLink that navigates to 'advanced' tab")


# ---------------------------------------------------------------------------
# Test 6: CSS for new components
# ---------------------------------------------------------------------------

class TestTaxTabCss(unittest.TestCase):
    """CSS must include styles for TaxMetricsSummary and AdvancedToolsLink."""

    def test_tax_summary_metrics_css_exists(self):
        """Test 6a: CSS contains styles for tax summary metrics section."""
        css = _css()
        has_metrics_style = (
            'tax-summary-metrics' in css or
            'taxSummaryMetrics' in css or
            'tax-metrics' in css
        )
        self.assertTrue(has_metrics_style,
            "styles.css must contain CSS for the tax metrics summary section")

    def test_advanced_tools_link_css_exists(self):
        """Test 6b: CSS contains styles for the AdvancedToolsLink banner."""
        css = _css()
        has_link_style = (
            'tax-advanced-link' in css or
            'taxAdvancedLink' in css or
            'advanced-tools-link' in css
        )
        self.assertTrue(has_link_style,
            "styles.css must contain CSS for the AdvancedToolsLink banner")
