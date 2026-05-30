"""TDD Task 31 (Phase 3): E2E keyboard-only navigation through asset class detection flow."""

import pytest
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"


class TestKeyboardNavigation:
    """Keyboard-only navigation through the import wizard's asset class radiogroup."""

    def _reach_step2(self, page, server_url, csv_name="sample_transactions.csv"):
        csv_path = EXAMPLES_DIR / csv_name
        if not csv_path.exists():
            pytest.skip(f"{csv_name} not found in examples/")
        page.goto(f"{server_url}/import")
        page.wait_for_timeout(300)
        page.locator("#fileInput").set_input_files(str(csv_path))
        page.wait_for_timeout(200)
        page.locator("#previewBtn").click()
        page.wait_for_selector("#wb2:not([hidden])", timeout=10000)
        page.wait_for_timeout(300)

    # ── ARIA structure ─────────────────────────────────────────────────

    def test_ac_toggle_group_has_role_radiogroup(self, premium_desktop_page, server_url):
        """#acToggles must expose role=radiogroup."""
        self._reach_step2(premium_desktop_page, server_url)
        role = premium_desktop_page.locator("#acToggles").get_attribute("role")
        assert role == "radiogroup", f"Expected role='radiogroup', got '{role}'"

    def test_exactly_one_button_has_aria_checked_true(self, premium_desktop_page, server_url):
        """Exactly one radio button must be aria-checked=true on load."""
        self._reach_step2(premium_desktop_page, server_url)
        checked = premium_desktop_page.locator('.ac-btn[aria-checked="true"]')
        assert checked.count() == 1, f"Expected 1 checked radio, got {checked.count()}"

    def test_unchecked_buttons_have_aria_checked_false(self, premium_desktop_page, server_url):
        """The three non-selected buttons must have aria-checked=false."""
        self._reach_step2(premium_desktop_page, server_url)
        unchecked = premium_desktop_page.locator('.ac-btn[aria-checked="false"]')
        assert unchecked.count() == 3, f"Expected 3 unchecked radios, got {unchecked.count()}"

    def test_only_checked_button_has_tabindex_zero(self, premium_desktop_page, server_url):
        """Roving tabindex: only checked button has tabindex=0; others have -1."""
        self._reach_step2(premium_desktop_page, server_url)
        btns = premium_desktop_page.locator(".ac-btn")
        tab0 = sum(
            1 for i in range(btns.count())
            if btns.nth(i).get_attribute("tabindex") == "0"
        )
        tabn1 = sum(
            1 for i in range(btns.count())
            if btns.nth(i).get_attribute("tabindex") == "-1"
        )
        assert tab0 == 1, f"Expected 1 button with tabindex=0, got {tab0}"
        assert tabn1 == 3, f"Expected 3 buttons with tabindex=-1, got {tabn1}"

    # ── Arrow key navigation ───────────────────────────────────────────

    def test_arrow_right_moves_to_next_option(self, premium_desktop_page, server_url):
        """ArrowRight on a radio should select the next option."""
        self._reach_step2(premium_desktop_page, server_url)

        # Click and focus the first option (stock)
        stock_btn = premium_desktop_page.locator('.ac-btn[data-ac="stock"]')
        stock_btn.click()
        premium_desktop_page.wait_for_timeout(100)
        stock_btn.focus()

        premium_desktop_page.keyboard.press("ArrowRight")
        premium_desktop_page.wait_for_timeout(150)

        checked = premium_desktop_page.locator('.ac-btn[aria-checked="true"]')
        assert checked.count() == 1
        new_ac = checked.get_attribute("data-ac")
        assert new_ac != "stock", "ArrowRight from stock should move to the next option"
        assert new_ac == "cfd", f"Expected 'cfd' after ArrowRight from 'stock', got '{new_ac}'"

    def test_arrow_down_moves_to_next_option(self, premium_desktop_page, server_url):
        """ArrowDown must behave identically to ArrowRight."""
        self._reach_step2(premium_desktop_page, server_url)

        stock_btn = premium_desktop_page.locator('.ac-btn[data-ac="stock"]')
        stock_btn.click()
        premium_desktop_page.wait_for_timeout(100)
        stock_btn.focus()

        premium_desktop_page.keyboard.press("ArrowDown")
        premium_desktop_page.wait_for_timeout(150)

        checked = premium_desktop_page.locator('.ac-btn[aria-checked="true"]')
        assert checked.get_attribute("data-ac") == "cfd"

    def test_arrow_left_moves_to_previous_option(self, premium_desktop_page, server_url):
        """ArrowLeft on a radio should select the previous option."""
        self._reach_step2(premium_desktop_page, server_url)

        cfd_btn = premium_desktop_page.locator('.ac-btn[data-ac="cfd"]')
        cfd_btn.click()
        premium_desktop_page.wait_for_timeout(100)
        cfd_btn.focus()

        premium_desktop_page.keyboard.press("ArrowLeft")
        premium_desktop_page.wait_for_timeout(150)

        checked = premium_desktop_page.locator('.ac-btn[aria-checked="true"]')
        assert checked.get_attribute("data-ac") == "stock"

    def test_arrow_left_wraps_from_first_to_last(self, premium_desktop_page, server_url):
        """ArrowLeft on the first option wraps around to the last."""
        self._reach_step2(premium_desktop_page, server_url)

        stock_btn = premium_desktop_page.locator('.ac-btn[data-ac="stock"]')
        stock_btn.click()
        premium_desktop_page.wait_for_timeout(100)
        stock_btn.focus()

        premium_desktop_page.keyboard.press("ArrowLeft")
        premium_desktop_page.wait_for_timeout(150)

        checked = premium_desktop_page.locator('.ac-btn[aria-checked="true"]')
        assert checked.get_attribute("data-ac") == "savings", \
            "ArrowLeft from 'stock' (first) should wrap to 'savings' (last)"

    def test_arrow_right_wraps_from_last_to_first(self, premium_desktop_page, server_url):
        """ArrowRight on the last option wraps around to the first."""
        self._reach_step2(premium_desktop_page, server_url)

        savings_btn = premium_desktop_page.locator('.ac-btn[data-ac="savings"]')
        savings_btn.click()
        premium_desktop_page.wait_for_timeout(100)
        savings_btn.focus()

        premium_desktop_page.keyboard.press("ArrowRight")
        premium_desktop_page.wait_for_timeout(150)

        checked = premium_desktop_page.locator('.ac-btn[aria-checked="true"]')
        assert checked.get_attribute("data-ac") == "stock", \
            "ArrowRight from 'savings' (last) should wrap to 'stock' (first)"

    # ── Click selection ────────────────────────────────────────────────

    def test_click_updates_aria_checked(self, premium_desktop_page, server_url):
        """Clicking a radio button must update aria-checked on all buttons."""
        self._reach_step2(premium_desktop_page, server_url)

        crypto_btn = premium_desktop_page.locator('.ac-btn[data-ac="crypto"]')
        crypto_btn.click()
        premium_desktop_page.wait_for_timeout(150)

        assert crypto_btn.get_attribute("aria-checked") == "true"
        assert crypto_btn.get_attribute("tabindex") == "0"
        for ac in ("stock", "cfd", "savings"):
            btn = premium_desktop_page.locator(f'.ac-btn[data-ac="{ac}"]')
            assert btn.get_attribute("aria-checked") == "false"
            assert btn.get_attribute("tabindex") == "-1"

    # ── Live regions ───────────────────────────────────────────────────

    def test_detect_live_region_exists(self, premium_desktop_page, server_url):
        """#acDetectAnnounce must be present in the DOM."""
        premium_desktop_page.goto(f"{server_url}/import")
        premium_desktop_page.wait_for_timeout(300)
        el = premium_desktop_page.locator("#acDetectAnnounce")
        assert el.count() == 1, "#acDetectAnnounce live region must exist"
        assert el.get_attribute("aria-live") == "polite"

    def test_override_live_region_exists(self, premium_desktop_page, server_url):
        """#acOverrideAnnounce must be present in the DOM."""
        premium_desktop_page.goto(f"{server_url}/import")
        premium_desktop_page.wait_for_timeout(300)
        el = premium_desktop_page.locator("#acOverrideAnnounce")
        assert el.count() == 1, "#acOverrideAnnounce live region must exist"
        assert el.get_attribute("aria-live") == "polite"
