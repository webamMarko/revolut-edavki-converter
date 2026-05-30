"""TDD Tasks 24-28 (Phase 3): Accessibility — radiogroup ARIA, arrow keys, live regions."""

import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE_PATH = PROJECT_ROOT / "src" / "templates" / "pages" / "import_wizard.html.j2"
CSS_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "common.css"


def _template() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def _css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Task 24: Toggle group uses role=radiogroup with aria-checked per option
# ---------------------------------------------------------------------------

class TestRadiogroupAriaPattern(unittest.TestCase):
    """Task 24 — acToggles must expose role=radiogroup; each option must use aria-checked."""

    def test_toggle_group_has_role_radiogroup(self):
        content = _template()
        self.assertIn(
            'role="radiogroup"',
            content,
            "acToggles container must have role='radiogroup'",
        )

    def test_each_option_has_aria_checked(self):
        content = _template()
        matches = re.findall(r'aria-checked=', content)
        self.assertGreaterEqual(
            len(matches), 4,
            "All 4 asset-class buttons must have aria-checked attribute",
        )

    def test_no_aria_pressed_on_ac_buttons(self):
        """aria-pressed is for toggle buttons; radiogroup uses aria-checked."""
        content = _template()
        # Find the acToggles section
        start = content.find('id="acToggles"')
        end = content.find('</div>', start + 1)
        # Find next closing div that ends acToggles block
        section = content[start:content.find('id="overrideWarning"', start)]
        self.assertNotIn(
            'aria-pressed',
            section,
            "Asset-class option buttons must use aria-checked, not aria-pressed",
        )

    def test_each_option_has_role_radio(self):
        content = _template()
        matches = re.findall(r'role="radio"', content)
        self.assertGreaterEqual(
            len(matches), 4,
            "Each asset-class button should expose role='radio'",
        )

    def test_stock_button_default_tabindex_zero(self):
        content = _template()
        stock_idx = content.find('data-ac="stock"')
        surrounding = content[max(0, stock_idx - 20): stock_idx + 150]
        self.assertIn(
            'tabindex="0"',
            surrounding,
            "Stock button (first/default) should have tabindex=0 for roving tabindex",
        )

    def test_non_default_buttons_have_tabindex_minus_one(self):
        content = _template()
        for ac in ('cfd', 'crypto', 'savings'):
            idx = content.find(f'data-ac="{ac}"')
            surrounding = content[max(0, idx - 20): idx + 150]
            self.assertIn(
                'tabindex="-1"',
                surrounding,
                f"Non-default button '{ac}' should have tabindex=-1",
            )


# ---------------------------------------------------------------------------
# Task 25: Arrow keys cycle focus between options
# ---------------------------------------------------------------------------

class TestArrowKeyNavigation(unittest.TestCase):
    """Task 25 — Arrow key handler must be present in the script."""

    def test_arrow_right_handler_present(self):
        content = _template()
        self.assertIn(
            "'ArrowRight'",
            content,
            "Script must handle ArrowRight key for radiogroup navigation",
        )

    def test_arrow_left_handler_present(self):
        content = _template()
        self.assertIn(
            "'ArrowLeft'",
            content,
            "Script must handle ArrowLeft key for radiogroup navigation",
        )

    def test_arrow_down_handler_present(self):
        content = _template()
        self.assertIn(
            "'ArrowDown'",
            content,
            "Script must handle ArrowDown key (same as ArrowRight in radiogroup)",
        )

    def test_arrow_up_handler_present(self):
        content = _template()
        self.assertIn(
            "'ArrowUp'",
            content,
            "Script must handle ArrowUp key (same as ArrowLeft in radiogroup)",
        )

    def test_home_end_keys_handled(self):
        content = _template()
        self.assertIn("'Home'", content, "Script should handle Home key")
        self.assertIn("'End'", content, "Script should handle End key")

    def test_keydown_listener_on_ac_toggles(self):
        content = _template()
        self.assertIn(
            "'keydown'",
            content,
            "A keydown listener must be registered (for arrow-key navigation)",
        )

    def test_wrapping_modulo_logic_present(self):
        """nextIdx wrap uses modulo (% btns.length)."""
        content = _template()
        self.assertIn(
            '% btns.length',
            content,
            "Arrow key wrap-around must use modulo % btns.length",
        )


# ---------------------------------------------------------------------------
# Task 26: ARIA live region announces detection result
# ---------------------------------------------------------------------------

class TestDetectionLiveRegion(unittest.TestCase):
    """Task 26 — A dedicated live region must be present for detection announcements."""

    def test_ac_detect_announce_element_exists(self):
        content = _template()
        self.assertIn(
            'id="acDetectAnnounce"',
            content,
            "Dedicated detection live region #acDetectAnnounce must exist",
        )

    def test_ac_detect_announce_has_aria_live_polite(self):
        content = _template()
        idx = content.find('id="acDetectAnnounce"')
        self.assertGreater(idx, -1)
        surrounding = content[max(0, idx - 5): idx + 100]
        self.assertIn(
            'aria-live="polite"',
            surrounding,
            "#acDetectAnnounce must have aria-live='polite'",
        )

    def test_ac_detect_announce_has_aria_atomic(self):
        content = _template()
        idx = content.find('id="acDetectAnnounce"')
        surrounding = content[max(0, idx - 5): idx + 100]
        self.assertIn(
            'aria-atomic="true"',
            surrounding,
            "#acDetectAnnounce must have aria-atomic='true'",
        )

    def test_ac_detect_announce_is_sr_only(self):
        content = _template()
        idx = content.find('id="acDetectAnnounce"')
        surrounding = content[max(0, idx - 5): idx + 100]
        self.assertIn(
            'class="sr-only"',
            surrounding,
            "#acDetectAnnounce must be visually hidden via sr-only",
        )

    def test_announce_detect_function_exists(self):
        content = _template()
        self.assertIn(
            '_announceDetect(',
            content,
            "_announceDetect() helper must be called from the script",
        )

    def test_announce_detect_wired_to_detected_class(self):
        content = _template()
        # Find the if(detectedClass) guard and verify _announceDetect is called inside it
        guard_idx = content.find('if (detectedClass)')
        self.assertGreater(guard_idx, -1, "Script must guard _announceDetect with 'if (detectedClass)'")
        after_guard = content[guard_idx: guard_idx + 400]
        self.assertIn(
            '_announceDetect(',
            after_guard,
            "_announceDetect() must be called inside the 'if (detectedClass)' block",
        )


# ---------------------------------------------------------------------------
# Task 27: ARIA live region announces override warning
# ---------------------------------------------------------------------------

class TestOverrideLiveRegion(unittest.TestCase):
    """Task 27 — A dedicated live region must be present for override announcements."""

    def test_ac_override_announce_element_exists(self):
        content = _template()
        self.assertIn(
            'id="acOverrideAnnounce"',
            content,
            "Dedicated override live region #acOverrideAnnounce must exist",
        )

    def test_ac_override_announce_has_aria_live_polite(self):
        content = _template()
        idx = content.find('id="acOverrideAnnounce"')
        self.assertGreater(idx, -1)
        surrounding = content[max(0, idx - 5): idx + 100]
        self.assertIn(
            'aria-live="polite"',
            surrounding,
            "#acOverrideAnnounce must have aria-live='polite'",
        )

    def test_ac_override_announce_is_sr_only(self):
        content = _template()
        idx = content.find('id="acOverrideAnnounce"')
        surrounding = content[max(0, idx - 5): idx + 100]
        self.assertIn(
            'class="sr-only"',
            surrounding,
            "#acOverrideAnnounce must be visually hidden via sr-only",
        )

    def test_announce_override_function_exists(self):
        content = _template()
        self.assertIn(
            '_announceOverride(',
            content,
            "_announceOverride() helper must be called from the script",
        )

    def test_announce_override_wired_to_isoverridden(self):
        content = _template()
        # Find the _isOverridden guard and verify _announceOverride is called inside it
        guard_idx = content.find('if (_isOverridden')
        self.assertGreater(guard_idx, -1, "Script must guard _announceOverride with 'if (_isOverridden'")
        after_guard = content[guard_idx: guard_idx + 400]
        self.assertIn(
            '_announceOverride(',
            after_guard,
            "_announceOverride() must be called inside the '_isOverridden' check",
        )


# ---------------------------------------------------------------------------
# Task 28: Each option has descriptive aria-label
# ---------------------------------------------------------------------------

class TestDescriptiveAriaLabels(unittest.TestCase):
    """Task 28 — Every asset-class button must have a descriptive aria-label."""

    def test_stock_has_descriptive_aria_label(self):
        content = _template()
        self.assertIn(
            'aria-label="Stock: Company shares"',
            content,
            "Stock button must have descriptive aria-label",
        )

    def test_cfd_has_descriptive_aria_label(self):
        content = _template()
        self.assertIn(
            'aria-label="CFD:',
            content,
            "CFD button must have a descriptive aria-label starting with 'CFD:'",
        )

    def test_crypto_has_descriptive_aria_label(self):
        content = _template()
        self.assertIn(
            'aria-label="Crypto:',
            content,
            "Crypto button must have a descriptive aria-label starting with 'Crypto:'",
        )

    def test_savings_has_descriptive_aria_label(self):
        content = _template()
        self.assertIn(
            'aria-label="Savings:',
            content,
            "Savings button must have a descriptive aria-label starting with 'Savings:'",
        )

    def test_all_four_ac_buttons_have_aria_label(self):
        content = _template()
        for ac in ('stock', 'cfd', 'crypto', 'savings'):
            btn_idx = content.find(f'data-ac="{ac}"')
            self.assertGreater(btn_idx, -1, f"Button for '{ac}' must exist")
            surrounding = content[max(0, btn_idx - 150): btn_idx + 200]
            self.assertIn(
                'aria-label=',
                surrounding,
                f"Button for '{ac}' must have aria-label",
            )


# ---------------------------------------------------------------------------
# CSS: focus-visible ring on .ac-btn
# ---------------------------------------------------------------------------

class TestFocusVisibleCSS(unittest.TestCase):
    """Phase 3 visual: focused radio button must have a visible focus ring."""

    def test_ac_btn_focus_visible_defined(self):
        content = _css()
        self.assertIn(
            '.ac-btn:focus-visible',
            content,
            "CSS must define .ac-btn:focus-visible for visible keyboard focus indicator",
        )

    def test_ac_btn_focus_visible_has_outline(self):
        content = _css()
        idx = content.find('.ac-btn:focus-visible')
        self.assertGreater(idx, -1)
        rule = content[idx: idx + 100]
        self.assertIn('outline', rule, ".ac-btn:focus-visible must set outline")


if __name__ == "__main__":
    unittest.main()
