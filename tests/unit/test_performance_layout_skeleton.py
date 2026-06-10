"""TDD tests for SAA-640 (SAA-573a): Reorder Performance layout + benchmark skeleton.

Spec: benchmarkSection becomes the first child of .page-stack (always visible),
followed by the heatmap toggle/panel, then Annual Summary, then the rest.
A pulsing skeleton placeholder shows while the benchmark chart loads, and the
section is hidden entirely when there is no benchmark data.
"""
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CHARTS_HTML_PATH = PROJECT_ROOT / "src" / "templates" / "sections" / "charts.html.j2"
CHARTS_JS_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "charts.js"
STYLES_CSS_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "styles.css"


def _html() -> str:
    return CHARTS_HTML_PATH.read_text(encoding="utf-8")


def _js() -> str:
    return CHARTS_JS_PATH.read_text(encoding="utf-8")


def _css() -> str:
    return STYLES_CSS_PATH.read_text(encoding="utf-8")


class TestLayoutOrder(unittest.TestCase):
    """AC5: Layout order is Benchmark -> Heatmaps toggle -> Annual Summary -> rest."""

    def test_benchmark_section_is_first_child_of_page_stack(self):
        html = _html()
        page_stack_start = html.index('<div class="page-stack">')
        benchmark_pos = html.index('data-role="benchmarkSection"')
        toggle_pos = html.index('perf-detail-toggle-wrap')
        yearly_pos = html.index('data-role="yearlyTableSection"')

        self.assertLess(page_stack_start, benchmark_pos)
        self.assertLess(benchmark_pos, toggle_pos,
            "benchmarkSection must come before the heatmap toggle")
        self.assertLess(toggle_pos, yearly_pos,
            "heatmap toggle/panel must come before Annual Summary")

    def test_no_other_section_precedes_benchmark_section(self):
        html = _html()
        page_stack_start = html.index('<div class="page-stack">')
        benchmark_section_start = html.rindex(
            '<section', 0, html.index('data-role="benchmarkSection"')
        )
        between = html[page_stack_start:benchmark_section_start]
        self.assertNotIn('<section', between,
            "benchmarkSection must be the first section in .page-stack")


class TestBenchmarkSectionVisibility(unittest.TestCase):
    """AC1/AC3: section starts visible (skeleton shows), JS hides it when empty."""

    def test_benchmark_section_has_no_inline_display_none(self):
        html = _html()
        section_match = re.search(
            r'<section[^>]*data-role="benchmarkSection"[^>]*>', html
        )
        self.assertIsNotNone(section_match)
        self.assertNotIn("display:none", section_match.group(0))
        self.assertNotIn("display: none", section_match.group(0))


class TestSkeletonPlaceholder(unittest.TestCase):
    """AC1/AC2: skeleton placeholder exists before the canvas, with pulsing CSS."""

    def test_skeleton_div_present_with_role_and_class(self):
        html = _html()
        self.assertIn('data-role="benchmarkSkeleton"', html)
        skeleton_match = re.search(
            r'<div[^>]*data-role="benchmarkSkeleton"[^>]*>', html
        )
        self.assertIsNotNone(skeleton_match)
        self.assertIn("skeleton-chart", skeleton_match.group(0))

    def test_skeleton_appears_before_benchmark_canvas(self):
        html = _html()
        skeleton_pos = html.index('data-role="benchmarkSkeleton"')
        canvas_pos = html.index('data-role="benchmarkChart"')
        self.assertLess(skeleton_pos, canvas_pos,
            "skeleton placeholder must precede the benchmark canvas")

    def test_skeleton_chart_css_has_pulsing_animation_and_height(self):
        css = _css()
        rule_match = re.search(r"\.skeleton-chart\s*\{([^}]*)\}", css)
        self.assertIsNotNone(rule_match, ".skeleton-chart rule must be defined")
        rule = rule_match.group(1)
        self.assertIn("height: 300px", rule)
        self.assertRegex(rule, r"animation\s*:")
        # animation should reference a keyframes block defined in the stylesheet
        anim_name = re.search(r"animation\s*:\s*([\w-]+)", rule).group(1)
        self.assertIn(f"@keyframes {anim_name}", css)


class TestBuildBenchmarkChartJs(unittest.TestCase):
    """JS behavior: hide skeleton/show canvas at start, hide section when empty."""

    def _function_body(self) -> str:
        js = _js()
        match = re.search(r"function buildBenchmarkChart\(\)\s*\{(.*?)\n\}", js, re.S)
        self.assertIsNotNone(match, "buildBenchmarkChart must be defined")
        return match.group(1)

    def test_hides_skeleton_at_start(self):
        body = self._function_body()
        self.assertRegex(
            body,
            r"scopedFind\(null,\s*'benchmarkSkeleton'\)\.style\.display\s*=\s*'none'",
        )

    def test_shows_canvas_at_start(self):
        body = self._function_body()
        self.assertRegex(
            body,
            r"scopedFind\(null,\s*'benchmarkChart'\)\.style\.display\s*=\s*'';?",
        )

    def test_hides_section_when_no_benchmark_keys(self):
        body = self._function_body()
        self.assertIn("bKeys.length === 0", body)
        # The branch handling the empty case must hide the benchmark section.
        empty_branch = re.search(
            r"bKeys\.length === 0\)\s*\{(.*?)\}", body, re.S
        ).group(1)
        self.assertRegex(
            empty_branch,
            r"scopedFind\(null,\s*'benchmarkSection'\)\.style\.display\s*=\s*'none'",
        )

    def test_skeleton_hidden_before_section_visibility_decision(self):
        body = self._function_body()
        skeleton_idx = body.index("benchmarkSkeleton")
        bkeys_idx = body.index("bKeys.length === 0")
        self.assertLess(skeleton_idx, bkeys_idx)


if __name__ == "__main__":
    unittest.main()
