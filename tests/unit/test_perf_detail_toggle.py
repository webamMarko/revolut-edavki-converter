"""Tests for SAA-573b (SAA-641): heatmap toggle uses event delegation.

sections/charts.html.j2 is rendered for both Performance and dashboard widgets.
Dashboard copies live inside inert template elements, preventing duplicate IDs
in live DOM and avoiding startup style/layout work.

The fix uses a document-level delegated click listener: the button is
resolved via e.target.closest() (correct regardless of duplicate ids, since
it walks up from the actual clicked element), and the panel is resolved as a
descendant of the clicked button's own .page-stack.
"""
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
NAV_JS_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "nav.js"
CHARTS_HTML_PATH = PROJECT_ROOT / "src" / "templates" / "sections" / "charts.html.j2"
DASHBOARD_HTML_PATH = PROJECT_ROOT / "src" / "templates" / "sections" / "dashboard.html.j2"
REPORT_HTML_PATH = PROJECT_ROOT / "src" / "templates" / "report.html.j2"


def _nav_js() -> str:
    return NAV_JS_PATH.read_text(encoding="utf-8")


def _toggle_block() -> str:
    js = _nav_js()
    match = re.search(r"// --- Performance detail panel toggle ---\n(.*)", js, re.S)
    assert match, "Performance detail panel toggle block not found in nav.js"
    return match.group(1)


class TestDashboardTemplateIsolation(unittest.TestCase):
    """Dashboard widget markup stays outside live DOM until first use."""

    def test_charts_section_defines_perf_detail_ids(self):
        html = CHARTS_HTML_PATH.read_text(encoding="utf-8")
        self.assertIn('id="perfDetailToggle"', html)
        self.assertIn('id="perfDetailPanel"', html)

    def test_charts_section_is_included_in_inert_widget_template(self):
        dashboard_html = DASHBOARD_HTML_PATH.read_text(encoding="utf-8")
        pool_start = dashboard_html.index('id="widgetTemplates"')
        template_pos = dashboard_html.index('<template id="widget-charts">')
        include_pos = dashboard_html.index('{% include "sections/charts.html.j2" %}')
        self.assertGreater(template_pos, pool_start)
        self.assertGreater(
            include_pos, template_pos,
            "charts.html.j2 must be included inside inert widget template",
        )

    def test_charts_section_is_also_included_for_visible_performance_page(self):
        report_html = REPORT_HTML_PATH.read_text(encoding="utf-8")
        page_charts_pos = report_html.index('id="page-charts"')
        include_pos = report_html.index(
            '{% include "sections/charts.html.j2" %}', page_charts_pos
        )
        self.assertGreater(include_pos, page_charts_pos)


class TestPerfDetailToggleUsesEventDelegation(unittest.TestCase):
    """AC6/AC7: toggle works on every click regardless of duplicate ids."""

    def test_uses_document_level_click_delegation(self):
        block = _toggle_block()
        self.assertRegex(block, r"document\.addEventListener\(\s*['\"]click['\"]")

    def test_resolves_button_via_closest_from_event_target(self):
        block = _toggle_block()
        self.assertRegex(
            block, r"e\.target\.closest\(\s*['\"]#perfDetailToggle['\"]\s*\)"
        )

    def test_does_not_use_global_getelementbyid_for_toggle_or_panel(self):
        block = _toggle_block()
        for ident in ("perfDetailToggle", "perfDetailPanel"):
            for quote in ("'", '"'):
                self.assertNotIn(
                    f"getElementById({quote}{ident}{quote})", block,
                    f"getElementById({quote}{ident}{quote}) resolves to the "
                    "hidden #widgetTemplates copy, not the visible one",
                )

    def test_panel_resolved_relative_to_clicked_button(self):
        block = _toggle_block()
        self.assertRegex(block, r"btn\.closest\(\s*['\"]\.page-stack['\"]\s*\)")
        self.assertRegex(block, r"\.querySelector\(\s*['\"]#perfDetailPanel['\"]\s*\)")

    def test_toggles_aria_expanded_and_panel_display(self):
        block = _toggle_block()
        self.assertRegex(block, r"getAttribute\(\s*['\"]aria-expanded['\"]\s*\)")
        self.assertRegex(block, r"setAttribute\(\s*['\"]aria-expanded['\"]")
        self.assertRegex(block, r"panel\.style\.display\s*=")

    def test_no_iife_bound_at_parse_time(self):
        full_js = _nav_js()
        toggle_section_start = full_js.index(
            "// --- Performance detail panel toggle ---"
        )
        trailing = full_js[toggle_section_start:]
        self.assertNotIn("(function() {", trailing)


if __name__ == "__main__":
    unittest.main()
