"""TDD tests for SAA-583: Tax Tab — Build Advanced sub-tab with accordion sections.

Spec: TaxAdvanced container wraps 4 accordion sections in order:
  1. Tax Bracket Timeline  (tax_timeline.html.j2)
  2. Calendar              (year_end_calendar.html.j2)
  3. Smart Sell            (smart_sell.html.j2)
  4. File                  (tax_wizard.html.j2)
Single-expand behavior (only one open at a time). Timeline expanded by default.
No modifications to the wrapped components themselves.
"""
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
REPORT_HTML = PROJECT_ROOT / "src" / "templates" / "report.html.j2"
TAX_ADVANCED_HTML = PROJECT_ROOT / "src" / "templates" / "sections" / "tax_advanced.html.j2"
TAX_ADVANCED_JS = PROJECT_ROOT / "src" / "templates" / "assets" / "sections" / "tax_advanced.js"
CSS_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "styles.css"


def _report_html() -> str:
    return REPORT_HTML.read_text(encoding="utf-8")


def _tax_advanced_html() -> str:
    return TAX_ADVANCED_HTML.read_text(encoding="utf-8")


def _tax_advanced_js() -> str:
    return TAX_ADVANCED_JS.read_text(encoding="utf-8")


def _css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Test group 1: TaxAdvanced renders 4 accordion sections in order
# ---------------------------------------------------------------------------

class TestTaxAdvancedRendersAccordions(unittest.TestCase):
    """TaxAdvanced renders 4 accordion sections in the correct order."""

    def test_tax_advanced_html_exists(self):
        """1a: tax_advanced.html.j2 file exists."""
        self.assertTrue(TAX_ADVANCED_HTML.exists(), "tax_advanced.html.j2 must exist")

    def test_advanced_panel_includes_tax_advanced(self):
        """1b: report.html.j2 Advanced panel uses tax_advanced.html.j2."""
        html = _report_html()
        self.assertIn("tax_advanced.html.j2", html,
                      "Advanced panel must include tax_advanced.html.j2")

    def test_four_accordion_sections_present(self):
        """1c: Exactly 4 accordion sections defined."""
        html = _tax_advanced_html()
        self.assertEqual(html.count('data-accordion-id='), 4,
                         "Must have exactly 4 data-accordion-id attributes")

    def test_timeline_accordion_first(self):
        """1d: First accordion ID is 'timeline'."""
        html = _tax_advanced_html()
        ids = re.findall(r'data-accordion-id="([^"]+)"', html)
        self.assertGreater(len(ids), 0, "No accordion IDs found")
        self.assertEqual(ids[0], "timeline")

    def test_calendar_accordion_second(self):
        """1e: Second accordion ID is 'calendar'."""
        html = _tax_advanced_html()
        ids = re.findall(r'data-accordion-id="([^"]+)"', html)
        self.assertGreater(len(ids), 1)
        self.assertEqual(ids[1], "calendar")

    def test_smart_sell_accordion_third(self):
        """1f: Third accordion ID is 'smart-sell'."""
        html = _tax_advanced_html()
        ids = re.findall(r'data-accordion-id="([^"]+)"', html)
        self.assertGreater(len(ids), 2)
        self.assertEqual(ids[2], "smart-sell")

    def test_file_accordion_fourth(self):
        """1g: Fourth accordion ID is 'file'."""
        html = _tax_advanced_html()
        ids = re.findall(r'data-accordion-id="([^"]+)"', html)
        self.assertGreater(len(ids), 3)
        self.assertEqual(ids[3], "file")

    def test_accordion_titles_in_order(self):
        """1h: Accordion titles match spec in order."""
        html = _tax_advanced_html()
        titles = re.findall(r'<span class="tax-accordion-title">([^<]+)</span>', html)
        self.assertEqual(
            titles,
            ["Tax Bracket Timeline", "Calendar", "Smart Sell", "File"],
        )


# ---------------------------------------------------------------------------
# Test group 2: Only one accordion section can be expanded at a time
# ---------------------------------------------------------------------------

class TestSingleExpandBehavior(unittest.TestCase):
    """Only one accordion section can be expanded at a time."""

    def test_tax_advanced_js_exists(self):
        """2a: tax_advanced.js file exists."""
        self.assertTrue(TAX_ADVANCED_JS.exists(), "tax_advanced.js must exist")

    def test_js_queries_all_accordions(self):
        """2b: JS iterates over all accordions to collapse siblings."""
        js = _tax_advanced_js()
        self.assertRegex(js, r"querySelectorAll",
                         "JS must use querySelectorAll to find all accordions")

    def test_js_sets_aria_expanded(self):
        """2c: JS controls aria-expanded attribute."""
        js = _tax_advanced_js()
        self.assertIn("aria-expanded", js)

    def test_js_toggles_expanded_class(self):
        """2d: JS adds/removes 'expanded' class on accordion content."""
        js = _tax_advanced_js()
        self.assertIn("expanded", js)

    def test_only_one_accordion_expanded_by_default_in_html(self):
        """2e: Only one aria-expanded='true' in the initial HTML."""
        html = _tax_advanced_html()
        expanded_count = html.count('aria-expanded="true"')
        self.assertEqual(expanded_count, 1,
                         "Exactly one accordion must be expanded by default")


# ---------------------------------------------------------------------------
# Test group 3: Timeline accordion is expanded by default
# ---------------------------------------------------------------------------

class TestTimelineDefaultExpanded(unittest.TestCase):
    """Timeline accordion is expanded by default."""

    def test_timeline_toggle_aria_expanded_true(self):
        """3a: Timeline accordion toggle button has aria-expanded='true'."""
        html = _tax_advanced_html()
        self.assertIn(
            'data-accordion-toggle="timeline" aria-expanded="true"',
            html,
            "Timeline toggle must have aria-expanded='true'",
        )

    def test_timeline_content_has_expanded_class(self):
        """3b: Timeline content div has 'expanded' class initially."""
        html = _tax_advanced_html()
        self.assertRegex(
            html,
            r'data-accordion-content="timeline"[^>]*class="[^"]*expanded[^"]*"'
            r'|class="[^"]*expanded[^"]*"[^>]*data-accordion-content="timeline"',
            "Timeline content must have 'expanded' class",
        )

    def test_calendar_not_expanded_by_default(self):
        """3c: Calendar accordion is collapsed by default."""
        html = _tax_advanced_html()
        self.assertNotIn(
            'data-accordion-toggle="calendar" aria-expanded="true"', html
        )

    def test_smart_sell_not_expanded_by_default(self):
        """3d: Smart Sell accordion is collapsed by default."""
        html = _tax_advanced_html()
        self.assertNotIn(
            'data-accordion-toggle="smart-sell" aria-expanded="true"', html
        )

    def test_file_not_expanded_by_default(self):
        """3e: File accordion is collapsed by default."""
        html = _tax_advanced_html()
        self.assertNotIn(
            'data-accordion-toggle="file" aria-expanded="true"', html
        )


# ---------------------------------------------------------------------------
# Test group 4: All original components render correctly inside accordions
# ---------------------------------------------------------------------------

class TestOriginalComponentsInsideAccordions(unittest.TestCase):
    """All original components are present inside their accordion wrappers."""

    def test_timeline_section_included(self):
        """4a: tax_timeline.html.j2 is included in tax_advanced."""
        html = _tax_advanced_html()
        self.assertIn("tax_timeline.html.j2", html)

    def test_calendar_section_included(self):
        """4b: year_end_calendar.html.j2 is included in tax_advanced."""
        html = _tax_advanced_html()
        self.assertIn("year_end_calendar.html.j2", html)

    def test_smart_sell_section_included(self):
        """4c: smart_sell.html.j2 is included in tax_advanced."""
        html = _tax_advanced_html()
        self.assertIn("smart_sell.html.j2", html)

    def test_file_section_included(self):
        """4d: tax_wizard.html.j2 is included in tax_advanced."""
        html = _tax_advanced_html()
        self.assertIn("tax_wizard.html.j2", html)

    def test_timeline_inside_timeline_accordion(self):
        """4e: tax_timeline is nested inside the timeline accordion div."""
        html = _tax_advanced_html()
        segment = re.search(
            r'data-accordion-id="timeline"(.*?)data-accordion-id="calendar"',
            html, re.DOTALL
        )
        self.assertIsNotNone(segment, "Could not find timeline→calendar segment")
        self.assertIn("tax_timeline.html.j2", segment.group(1))

    def test_calendar_inside_calendar_accordion(self):
        """4f: year_end_calendar is nested inside the calendar accordion div."""
        html = _tax_advanced_html()
        segment = re.search(
            r'data-accordion-id="calendar"(.*?)data-accordion-id="smart-sell"',
            html, re.DOTALL
        )
        self.assertIsNotNone(segment, "Could not find calendar→smart-sell segment")
        self.assertIn("year_end_calendar.html.j2", segment.group(1))

    def test_smart_sell_inside_smart_sell_accordion(self):
        """4g: smart_sell is nested inside the smart-sell accordion div."""
        html = _tax_advanced_html()
        segment = re.search(
            r'data-accordion-id="smart-sell"(.*?)data-accordion-id="file"',
            html, re.DOTALL
        )
        self.assertIsNotNone(segment, "Could not find smart-sell→file segment")
        self.assertIn("smart_sell.html.j2", segment.group(1))

    def test_file_inside_file_accordion(self):
        """4h: tax_wizard is nested inside the file accordion div."""
        html = _tax_advanced_html()
        segment = re.search(
            r'data-accordion-id="file"(.*)',
            html, re.DOTALL
        )
        self.assertIsNotNone(segment, "Could not find file accordion segment")
        self.assertIn("tax_wizard.html.j2", segment.group(1))

    def test_advanced_panel_no_longer_flat_includes(self):
        """4i: Advanced panel in report.html uses tax_advanced.html.j2, not flat includes."""
        html = _report_html()
        # The flat includes should be gone from the Advanced panel
        # (they are now inside tax_advanced.html.j2)
        advanced_panel = re.search(
            r'id="taxSubtabAdvanced"(.*?)(?=</div>\s*</div>)',
            html, re.DOTALL
        )
        if advanced_panel:
            panel_html = advanced_panel.group(1)
            # Should not have flat includes of these sections in the panel
            self.assertNotIn('"sections/tax_timeline.html.j2"', panel_html,
                             "tax_timeline should be inside tax_advanced, not flat")
            self.assertNotIn('"sections/smart_sell.html.j2"', panel_html,
                             "smart_sell should be inside tax_advanced, not flat")


# ---------------------------------------------------------------------------
# Test group 5: CSS animation — max-height transition with overflow:hidden
# ---------------------------------------------------------------------------

class TestAccordionCSS(unittest.TestCase):
    """Accordion CSS uses max-height transition with overflow:hidden."""

    def test_accordion_css_class_exists(self):
        """5a: .tax-accordion CSS class exists."""
        css = _css()
        self.assertIn(".tax-accordion", css)

    def test_accordion_content_max_height_zero(self):
        """5b: Collapsed .tax-accordion-content has max-height: 0."""
        css = _css()
        self.assertRegex(
            css,
            r"\.tax-accordion-content\s*\{[^}]*max-height\s*:\s*0",
            ".tax-accordion-content must have max-height: 0 for collapsed state",
        )

    def test_accordion_content_overflow_hidden(self):
        """5c: .tax-accordion-content has overflow: hidden."""
        css = _css()
        self.assertRegex(
            css,
            r"\.tax-accordion-content\s*\{[^}]*overflow\s*:\s*hidden",
            ".tax-accordion-content must have overflow: hidden",
        )

    def test_accordion_content_transition(self):
        """5d: .tax-accordion-content has a CSS transition (200-300ms)."""
        css = _css()
        self.assertRegex(
            css,
            r"\.tax-accordion-content[^}]*transition[^}]*0\.[23]\d*s",
            ".tax-accordion-content must have transition ~200-300ms",
        )

    def test_expanded_state_css(self):
        """5e: .tax-accordion-content.expanded has large max-height for open state."""
        css = _css()
        self.assertIn(".tax-accordion-content.expanded", css)

    def test_accordion_js_included_in_report(self):
        """5f: tax_advanced.js is included in report.html.j2."""
        html = _report_html()
        self.assertIn("tax_advanced.js", html)


if __name__ == "__main__":
    unittest.main()
