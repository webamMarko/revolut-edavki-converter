"""TDD tests for SAA-584: Tax Tab — Mobile optimizations.

Verifies CSS media queries implement:
- AC9: Summary metrics stack vertically on mobile (768px)
- AC10: Accordion sections full-width with WCAG 2.5.5 touch targets on mobile
- AC11: Sub-tab selector fixed at bottom of screen on mobile
"""
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CSS_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "styles.css"


def _css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


def _extract_768_mobile_blocks(css: str) -> str:
    """Return concatenated body of all @media (max-width: 768px) blocks."""
    blocks = []
    pattern = re.compile(r"@media\s*\(max-width:\s*768px\)\s*\{", re.IGNORECASE)
    for match in pattern.finditer(css):
        start = match.end()
        depth = 1
        i = start
        while i < len(css) and depth > 0:
            if css[i] == "{":
                depth += 1
            elif css[i] == "}":
                depth -= 1
            i += 1
        blocks.append(css[start : i - 1])
    return "\n".join(blocks)


def _find_selector_rule_in_mobile_css(css: str, selector: str) -> str:
    """Return the rule body for `selector` inside @media (max-width: 768px) blocks.

    Returns the content between the first matching { and } or empty string.
    """
    mobile_css = _extract_768_mobile_blocks(css)
    escaped = re.escape(selector)
    pattern = re.compile(escaped + r"\s*\{([^}]*)\}", re.DOTALL)
    match = pattern.search(mobile_css)
    return match.group(1) if match else ""


# ---------------------------------------------------------------------------
# AC9: On mobile viewport, Summary metrics stack vertically
# ---------------------------------------------------------------------------


class TestMobileMetricsStack(unittest.TestCase):
    """AC9: On mobile viewport, Summary metrics stack vertically in single column."""

    def test_metrics_card_grid_rule_exists_in_768px_block(self):
        """1a: .tax-summary-metrics .card-grid rule exists inside 768px media block."""
        rule = _find_selector_rule_in_mobile_css(_css(), ".tax-summary-metrics .card-grid")
        self.assertNotEqual(
            rule,
            "",
            ".tax-summary-metrics .card-grid must have a rule inside @media (max-width: 768px)",
        )

    def test_metrics_single_column_grid(self):
        """1b: .tax-summary-metrics .card-grid uses grid-template-columns: 1fr on mobile."""
        rule = _find_selector_rule_in_mobile_css(_css(), ".tax-summary-metrics .card-grid")
        self.assertIn(
            "grid-template-columns: 1fr",
            rule,
            "mobile metrics must use single-column grid (grid-template-columns: 1fr)",
        )


# ---------------------------------------------------------------------------
# AC10: Mobile accordion sections full-width with 44px+ touch targets
# ---------------------------------------------------------------------------


class TestMobileAccordionTouchTargets(unittest.TestCase):
    """AC10: Accordion sections full-width with WCAG 2.5.5 44px touch targets on mobile."""

    def test_accordion_full_width_rule_exists(self):
        """2a: .tax-accordion has a rule inside the 768px media block."""
        rule = _find_selector_rule_in_mobile_css(_css(), ".tax-accordion")
        self.assertNotEqual(
            rule,
            "",
            ".tax-accordion must have a rule inside @media (max-width: 768px)",
        )

    def test_accordion_full_width_100_percent(self):
        """2b: .tax-accordion is 100% width on mobile."""
        rule = _find_selector_rule_in_mobile_css(_css(), ".tax-accordion")
        self.assertIn(
            "width: 100%",
            rule,
            "mobile accordion must be 100% width",
        )

    def test_accordion_header_rule_exists(self):
        """2c: .tax-accordion-header has a rule inside the 768px media block."""
        rule = _find_selector_rule_in_mobile_css(_css(), ".tax-accordion-header")
        self.assertNotEqual(
            rule,
            "",
            ".tax-accordion-header must have a rule inside @media (max-width: 768px)",
        )

    def test_accordion_header_min_height_48px(self):
        """2d: Accordion header min-height is 48px on mobile (>= WCAG 2.5.5 44px)."""
        rule = _find_selector_rule_in_mobile_css(_css(), ".tax-accordion-header")
        self.assertIn(
            "min-height: 48px",
            rule,
            "mobile accordion header must have min-height: 48px (WCAG 2.5.5 requires 44px+)",
        )

    def test_accordion_header_padding_12px_vertical(self):
        """2e: Accordion header has at least 12px vertical padding on mobile."""
        rule = _find_selector_rule_in_mobile_css(_css(), ".tax-accordion-header")
        self.assertIn(
            "padding: 12px",
            rule,
            "mobile accordion header must have 12px vertical padding",
        )


# ---------------------------------------------------------------------------
# AC11: Mobile sub-tab selector at bottom of screen
# ---------------------------------------------------------------------------


class TestMobileSubtabBottomPlacement(unittest.TestCase):
    """AC11: Sub-tab selector is fixed at the bottom of the screen on mobile."""

    def test_subtabs_rule_exists_in_768px_block(self):
        """3a: .tax-subtabs has a rule inside the 768px media block."""
        rule = _find_selector_rule_in_mobile_css(_css(), ".tax-subtabs")
        self.assertNotEqual(
            rule,
            "",
            ".tax-subtabs must have a rule inside @media (max-width: 768px)",
        )

    def test_subtabs_position_fixed(self):
        """3b: Sub-tab selector is position: fixed on mobile."""
        rule = _find_selector_rule_in_mobile_css(_css(), ".tax-subtabs")
        self.assertIn(
            "position: fixed",
            rule,
            "mobile sub-tab selector must be position: fixed",
        )

    def test_subtabs_bottom_zero(self):
        """3c: Sub-tab selector is at bottom: 0 on mobile."""
        rule = _find_selector_rule_in_mobile_css(_css(), ".tax-subtabs")
        self.assertIn(
            "bottom: 0",
            rule,
            "mobile sub-tab selector must have bottom: 0",
        )

    def test_subtabs_z_index_set(self):
        """3d: Sub-tab selector has z-index to avoid conflicts with app navigation."""
        rule = _find_selector_rule_in_mobile_css(_css(), ".tax-subtabs")
        self.assertRegex(
            rule,
            r"z-index:\s*\d+",
            "mobile sub-tab selector must have z-index set to handle layering",
        )

    def test_subtabs_full_width(self):
        """3e: Sub-tab selector spans full viewport width on mobile."""
        rule = _find_selector_rule_in_mobile_css(_css(), ".tax-subtabs")
        self.assertTrue(
            "left: 0" in rule and "right: 0" in rule,
            "mobile sub-tab selector must span full width (left: 0; right: 0)",
        )
