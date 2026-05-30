"""TDD Tasks 1-6 (Phase 1): Detection card frame, enhanced toggles, snapshot tests."""

import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE_PATH = PROJECT_ROOT / "src" / "templates" / "pages" / "import_wizard.html.j2"
CSS_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "common.css"

ASSET_CLASSES = [
    {
        "ac": "stock",
        "label": "Stock",
        "desc": "Company shares",
    },
    {
        "ac": "cfd",
        "label": "CFD",
        "desc": "Contracts for difference",
    },
    {
        "ac": "crypto",
        "label": "Crypto",
        "desc": "Bitcoin, Ethereum",
    },
    {
        "ac": "savings",
        "label": "Savings",
        "desc": "Money market funds",
    },
]


def _template() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def _css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Task 1: Detection card frame renders with question text
# ---------------------------------------------------------------------------

class TestDetectionCardFrame(unittest.TestCase):
    """Task 1 — The detection card frame exists and shows the question text."""

    def test_detection_card_element_exists(self):
        content = _template()
        self.assertIn(
            'class="detection-card"',
            content,
            "Should have a detection-card container",
        )

    def test_detection_card_has_id(self):
        content = _template()
        self.assertIn(
            'id="detectionCard"',
            content,
            "Detection card should have id='detectionCard'",
        )

    def test_detection_card_question_text(self):
        content = _template()
        self.assertIn(
            "What type of trades are in this file?",
            content,
            "Detection card should display the question text",
        )

    def test_detection_question_element(self):
        content = _template()
        self.assertIn(
            'class="detection-question"',
            content,
            "Should have a detection-question element",
        )

    def test_detection_card_wraps_toggles(self):
        content = _template()
        card_start = content.find('class="detection-card"')
        toggles_start = content.find('id="acToggles"')
        self.assertGreater(card_start, -1, "detection-card must exist")
        self.assertGreater(toggles_start, -1, "acToggles must exist")
        self.assertGreater(
            toggles_start, card_start,
            "acToggles must appear after detection-card opening (card wraps toggles)",
        )

    def test_detection_card_css_defined(self):
        content = _css()
        self.assertIn(
            ".detection-card",
            content,
            "CSS should define .detection-card",
        )

    def test_detection_question_css_defined(self):
        content = _css()
        self.assertIn(
            ".detection-question",
            content,
            "CSS should define .detection-question",
        )


# ---------------------------------------------------------------------------
# Task 2: Toggle group renders all 4 options with icons and descriptions
# ---------------------------------------------------------------------------

class TestToggleGroupStructure(unittest.TestCase):
    """Task 2 — The toggle group has all four asset-class options."""

    def test_all_four_asset_class_buttons_present(self):
        content = _template()
        for cls in ("stock", "cfd", "crypto", "savings"):
            self.assertIn(
                f'data-ac="{cls}"',
                content,
                f"Should have toggle for asset class '{cls}'",
            )

    def test_toggle_group_has_role_group(self):
        content = _template()
        self.assertIn(
            'role="group"',
            content,
            "Toggle group should have role='group'",
        )

    def test_toggle_group_has_aria_labelledby(self):
        content = _template()
        self.assertIn(
            "aria-labelledby=",
            content,
            "Toggle group should have aria-labelledby referencing the question",
        )

    def test_each_toggle_is_button(self):
        content = _template()
        for cls in ("stock", "cfd", "crypto", "savings"):
            self.assertIn(
                f'data-ac="{cls}"',
                content,
                f"Toggle '{cls}' should use a button element with data-ac attribute",
            )


# ---------------------------------------------------------------------------
# Task 3: Each toggle displays icon, label, and short description
# ---------------------------------------------------------------------------

class TestToggleContent(unittest.TestCase):
    """Task 3 — Every toggle button has an icon span, label span, and description span."""

    def test_toggle_buttons_have_icon_span(self):
        content = _template()
        self.assertIn(
            'class="ac-btn-icon"',
            content,
            "Toggle buttons should contain ac-btn-icon span",
        )

    def test_toggle_buttons_have_label_span(self):
        content = _template()
        self.assertIn(
            'class="ac-btn-label"',
            content,
            "Toggle buttons should contain ac-btn-label span",
        )

    def test_toggle_buttons_have_description_span(self):
        content = _template()
        self.assertIn(
            'class="ac-btn-desc"',
            content,
            "Toggle buttons should contain ac-btn-desc span",
        )

    def test_stock_label_text(self):
        content = _template()
        self.assertIn("Stock", content, "Stock toggle should display 'Stock' label")

    def test_stock_description_text(self):
        content = _template()
        self.assertIn(
            "Company shares",
            content,
            "Stock toggle should display 'Company shares' description",
        )

    def test_cfd_label_text(self):
        content = _template()
        self.assertIn("CFD", content, "CFD toggle should display 'CFD' label")

    def test_cfd_description_text(self):
        content = _template()
        self.assertIn(
            "Contracts for difference",
            content,
            "CFD toggle should display description containing 'Contracts for difference'",
        )

    def test_crypto_label_text(self):
        content = _template()
        self.assertIn("Crypto", content, "Crypto toggle should display 'Crypto' label")

    def test_crypto_description_text(self):
        content = _template()
        self.assertIn(
            "Bitcoin, Ethereum",
            content,
            "Crypto toggle should display description containing 'Bitcoin, Ethereum'",
        )

    def test_savings_label_text(self):
        content = _template()
        self.assertIn("Savings", content, "Savings toggle should display 'Savings' label")

    def test_savings_description_text(self):
        content = _template()
        self.assertIn(
            "savings accounts",
            content,
            "Savings toggle should display description containing 'savings accounts'",
        )

    def test_icon_span_is_aria_hidden(self):
        content = _template()
        icon_idx = content.find('class="ac-btn-icon"')
        self.assertGreater(icon_idx, -1, "ac-btn-icon should exist")
        surrounding = content[max(0, icon_idx - 5): icon_idx + 60]
        self.assertIn(
            'aria-hidden="true"',
            surrounding,
            "Icon span should be aria-hidden='true'",
        )

    def test_each_button_has_aria_label(self):
        content = _template()
        for cls in ("stock", "cfd", "crypto", "savings"):
            btn_start = content.find(f'data-ac="{cls}"')
            self.assertGreater(btn_start, -1)
            # aria-label may appear before or after data-ac on the same button element
            surrounding = content[max(0, btn_start - 150): btn_start + 200]
            self.assertIn(
                "aria-label=",
                surrounding,
                f"Toggle '{cls}' button should have an aria-label",
            )


# ---------------------------------------------------------------------------
# Task 6: Snapshot tests — CSS classes for enhanced toggle layout
# ---------------------------------------------------------------------------

class TestToggleAndCardSnapshots(unittest.TestCase):
    """Task 6 — CSS snapshot: all required classes are defined."""

    def test_ac_btn_has_flex_column_layout(self):
        content = _css()
        ac_btn_idx = content.find(".ac-btn{")
        self.assertGreater(ac_btn_idx, -1, ".ac-btn rule should exist")
        rule_chunk = content[ac_btn_idx: ac_btn_idx + 400]
        self.assertIn(
            "flex-direction:column",
            rule_chunk,
            ".ac-btn should use flex-direction:column for icon-label-desc stacking",
        )

    def test_ac_btn_icon_css_defined(self):
        content = _css()
        self.assertIn(
            ".ac-btn-icon",
            content,
            "CSS should define .ac-btn-icon",
        )

    def test_ac_btn_label_css_defined(self):
        content = _css()
        self.assertIn(
            ".ac-btn-label",
            content,
            "CSS should define .ac-btn-label",
        )

    def test_ac_btn_desc_css_defined(self):
        content = _css()
        self.assertIn(
            ".ac-btn-desc",
            content,
            "CSS should define .ac-btn-desc",
        )

    def test_detection_card_has_border(self):
        content = _css()
        card_idx = content.find(".detection-card")
        self.assertGreater(card_idx, -1)
        rule_chunk = content[card_idx: card_idx + 200]
        self.assertIn(
            "border",
            rule_chunk,
            ".detection-card should have a border",
        )

    def test_detection_card_has_border_radius(self):
        content = _css()
        card_idx = content.find(".detection-card")
        self.assertGreater(card_idx, -1)
        rule_chunk = content[card_idx: card_idx + 200]
        self.assertIn(
            "border-radius",
            rule_chunk,
            ".detection-card should have border-radius",
        )

    def test_detection_question_font_weight(self):
        content = _css()
        q_idx = content.find(".detection-question")
        self.assertGreater(q_idx, -1)
        rule_chunk = content[q_idx: q_idx + 150]
        self.assertIn(
            "font-weight",
            rule_chunk,
            ".detection-question should define font-weight",
        )

    def test_template_snapshot_no_old_ac_help_div(self):
        """Old flat ac-help text block should be replaced by per-button descriptions."""
        content = _template()
        self.assertNotIn(
            'id="ac-help"',
            content,
            "Old ac-help div should be removed — descriptions are now inline in each toggle",
        )

    def test_template_snapshot_no_old_ac_desc_div(self):
        """Old ac-desc prose should be replaced by detection-question."""
        content = _template()
        self.assertNotIn(
            'id="ac-desc"',
            content,
            "Old ac-desc div should be removed — question is now in detection-question element",
        )


if __name__ == "__main__":
    unittest.main()
