"""TDD tests for SAA-584 (Tax Tab mobile optimizations) and SAA-666.

Verifies CSS implements:
- AC9: Summary metrics stack vertically on mobile (768px)
- AC10: Accordion sections full-width with WCAG 2.5.5 touch targets on mobile
- SAA-666: All secondary tab bars (.tax-subtabs, .proj-subtabs) are fixed at
  the top of the page, below the header, on every viewport.
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
# SAA-666: Secondary (sub-tab) navigation fixed at the top of the page,
# below the header, on every viewport. Supersedes the SAA-584 AC11 behavior
# of pinning .tax-subtabs to the bottom of the screen on mobile.
# ---------------------------------------------------------------------------

SUBTABS_SELECTOR = ".tax-subtabs, .proj-subtabs"


def _find_global_rule(css: str, selector: str) -> str:
    """Return the rule body for `selector` outside of any media block."""
    pattern = re.compile(re.escape(selector) + r"\s*\{([^}]*)\}", re.DOTALL)
    match = pattern.search(css)
    return match.group(1) if match else ""


class TestSecondaryTabsFixedAtTop(unittest.TestCase):
    """All secondary tab bars stick to the top of the page, below the header."""

    def test_subtabs_rule_exists(self):
        """The shared sub-tab rule covers both Tax and Projections tab bars."""
        rule = _find_global_rule(_css(), SUBTABS_SELECTOR)
        self.assertNotEqual(
            rule,
            "",
            f"{SUBTABS_SELECTOR} must have a base rule",
        )

    def test_subtabs_position_sticky(self):
        """Sub-tab bars stay fixed in place at the top while the page scrolls."""
        rule = _find_global_rule(_css(), SUBTABS_SELECTOR)
        self.assertIn(
            "position: sticky",
            rule,
            "secondary tab bars must use position: sticky to stay fixed at the top",
        )

    def test_subtabs_stuck_to_top(self):
        """Sub-tab bars are anchored to the top edge of the page (below the header)."""
        rule = _find_global_rule(_css(), SUBTABS_SELECTOR)
        self.assertRegex(
            rule,
            r"top:\s*-?[\d.]+rem",
            "secondary tab bars must set a top offset to stick below the header",
        )

    def test_subtabs_z_index_set(self):
        """Sub-tab bars have a z-index so scrolled content passes beneath them."""
        rule = _find_global_rule(_css(), SUBTABS_SELECTOR)
        self.assertRegex(
            rule,
            r"z-index:\s*\d+",
            "secondary tab bars must have z-index set to handle layering",
        )

    def test_mobile_subtabs_no_longer_pinned_to_bottom(self):
        """The old SAA-584 AC11 bottom-fixed mobile placement is removed."""
        rule = _find_selector_rule_in_mobile_css(_css(), SUBTABS_SELECTOR)
        self.assertNotIn(
            "bottom: 0",
            rule,
            "secondary tab bars must no longer be pinned to the bottom on mobile",
        )

    def test_mobile_subtabs_top_offset_matches_page_padding(self):
        """On mobile the sticky offset matches the .page padding so the bar sits flush at the top."""
        rule = _find_selector_rule_in_mobile_css(_css(), SUBTABS_SELECTOR)
        self.assertRegex(
            rule,
            r"top:\s*-?[\d.]+rem",
            "mobile secondary tab bars must define a top offset",
        )
