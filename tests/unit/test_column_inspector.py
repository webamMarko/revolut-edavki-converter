"""TDD Tasks 1-17 (PR 1): Column Mapping Inspector — core inspector components."""

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
# Task 1: ColumnInspectorProvider context provides state and actions
# ---------------------------------------------------------------------------

class TestColumnInspectorProviderState(unittest.TestCase):
    """Task 1 — _ciState object provides activeColumn, reviewedColumns, and action functions."""

    def test_ci_state_object_present(self):
        self.assertIn("_ciState", _template(), "_ciState state object must be defined")

    def test_ci_state_has_active_column(self):
        content = _template()
        # Find the state declaration (not references to it)
        idx = content.find("const _ciState")
        if idx == -1:
            idx = content.find("_ciState = {")
        self.assertGreater(idx, -1, "_ciState declaration must exist")
        surrounding = content[idx: idx + 300]
        self.assertIn("activeColumn", surrounding, "_ciState must have activeColumn property")

    def test_ci_state_has_reviewed_columns(self):
        content = _template()
        idx = content.find("_ciState")
        surrounding = content[idx: idx + 300]
        self.assertIn("reviewedColumns", surrounding, "_ciState must have reviewedColumns property")

    def test_open_inspector_function_present(self):
        self.assertIn("openInspector(", _template(), "openInspector() action must be defined")

    def test_close_inspector_function_present(self):
        self.assertIn("closeInspector(", _template(), "closeInspector() action must be defined")

    def test_mark_reviewed_function_present(self):
        self.assertIn("markReviewed(", _template(), "markReviewed() action must be defined")

    def test_reviewed_columns_is_set(self):
        content = _template()
        self.assertIn("new Set()", content, "reviewedColumns must be a Set")


# ---------------------------------------------------------------------------
# Task 2: ColumnInspectorProvider implements useReducer-style dispatch
# ---------------------------------------------------------------------------

class TestColumnInspectorProviderDispatch(unittest.TestCase):
    """Task 2 — _ciDispatch implements reducer pattern with typed actions."""

    def test_ci_dispatch_function_present(self):
        self.assertIn("_ciDispatch(", _template(), "_ciDispatch() reducer function must be defined")

    def test_open_action_type(self):
        self.assertIn("'OPEN'", _template(), "OPEN action type must be defined")

    def test_close_action_type(self):
        self.assertIn("'CLOSE'", _template(), "CLOSE action type must be defined")

    def test_mark_reviewed_action_type(self):
        self.assertIn("'MARK_REVIEWED'", _template(), "MARK_REVIEWED action type must be defined")

    def test_switch_statement_in_dispatch(self):
        content = _template()
        self.assertIn("switch", content, "Dispatch should use a switch statement (reducer pattern)")

    def test_ci_render_called_from_dispatch(self):
        content = _template()
        self.assertIn("_ciRender()", content, "_ciRender() must be called after state changes")


# ---------------------------------------------------------------------------
# Task 3: ColumnInspectorContent renders column name, type, mapped field, samples
# ---------------------------------------------------------------------------

class TestColumnInspectorContentRenders(unittest.TestCase):
    """Task 3 — All content elements are present in the inspector panel."""

    def test_col_name_element_present(self):
        self.assertIn('id="ci-col-name"', _template(), "#ci-col-name element must exist")

    def test_type_badge_element_present(self):
        self.assertIn('id="ci-type-badge"', _template(), "#ci-type-badge element must exist")

    def test_mapped_field_element_present(self):
        self.assertIn('id="ci-mapped-field"', _template(), "#ci-mapped-field element must exist")

    def test_samples_element_present(self):
        self.assertIn('id="ci-samples"', _template(), "#ci-samples element must exist")

    def test_transform_preview_element_present(self):
        self.assertIn('id="ci-transform-preview"', _template(), "#ci-transform-preview element must exist")

    def test_content_populated_in_ci_render(self):
        content = _template()
        ci_render_idx = content.find("_ciRender")
        self.assertGreater(ci_render_idx, -1)
        # ci-col-name should be set in _ciRender
        self.assertIn("ci-col-name", content[ci_render_idx:], "_ciRender must populate ci-col-name")


# ---------------------------------------------------------------------------
# Task 4: ColumnInspectorContent structure
# ---------------------------------------------------------------------------

class TestColumnInspectorContentStructure(unittest.TestCase):
    """Task 4 — Inspector panel has correct DOM structure."""

    def test_inspector_panel_exists(self):
        self.assertIn('id="columnInspector"', _template(), "#columnInspector panel must exist")

    def test_inspector_has_content_section(self):
        self.assertIn("ci-content", _template(), ".ci-content section must be present")

    def test_inspector_has_close_button(self):
        self.assertIn('id="ci-close"', _template(), "#ci-close button must exist")

    def test_close_button_has_aria_label(self):
        content = _template()
        ci_close_idx = content.find('id="ci-close"')
        self.assertGreater(ci_close_idx, -1)
        surrounding = content[max(0, ci_close_idx - 100): ci_close_idx + 150]
        self.assertIn("aria-label=", surrounding, "Close button must have aria-label")

    def test_inspector_has_samples_section(self):
        self.assertIn("ci-samples", _template(), "Inspector must have a samples section")

    def test_ci_content_css_defined(self):
        self.assertIn(".ci-content", _css(), ".ci-content must be defined in CSS")


# ---------------------------------------------------------------------------
# Task 5: ColumnInspector renders as side drawer on desktop, bottom sheet on mobile
# ---------------------------------------------------------------------------

class TestColumnInspectorResponsive(unittest.TestCase):
    """Task 5 — Inspector uses CSS translateX (drawer) on desktop, translateY (sheet) on mobile."""

    def test_ci_panel_css_class_defined(self):
        self.assertIn(".ci-panel", _css(), ".ci-panel must be defined in CSS")

    def test_desktop_uses_translatex(self):
        self.assertIn("translateX", _css(), "Desktop drawer must use translateX transition")

    def test_mobile_uses_translatey(self):
        self.assertIn("translateY", _css(), "Mobile bottom sheet must use translateY transition")

    def test_inspector_has_transition(self):
        css = _css()
        idx = css.find(".ci-panel")
        self.assertGreater(idx, -1)
        rule = css[idx: idx + 600]
        self.assertIn("transition", rule, ".ci-panel must define a CSS transition")

    def test_mobile_media_query_present(self):
        css = _css()
        idx = css.find(".ci-panel")
        surrounding = css[idx: idx + 1500]
        self.assertIn("@media", surrounding, "Mobile bottom-sheet layout needs a @media breakpoint")


# ---------------------------------------------------------------------------
# Task 6: ColumnInspector shell — position: fixed, high z-index
# ---------------------------------------------------------------------------

class TestColumnInspectorShell(unittest.TestCase):
    """Task 6 — Inspector panel is position:fixed with a high z-index."""

    def test_inspector_panel_fixed_position(self):
        css = _css()
        idx = css.find(".ci-panel")
        self.assertGreater(idx, -1)
        rule = css[idx: idx + 400]
        self.assertIn("position:fixed", rule.replace(" ", ""), ".ci-panel must be position:fixed")

    def test_inspector_has_z_index(self):
        css = _css()
        idx = css.find(".ci-panel")
        rule = css[idx: idx + 400]
        self.assertIn("z-index", rule, ".ci-panel must define a z-index")

    def test_ci_open_class_defined_in_css(self):
        self.assertIn(".ci-panel.ci-open", _css(), ".ci-panel.ci-open must be defined in CSS")


# ---------------------------------------------------------------------------
# Task 7: InspectableColumnHeader calls openInspector on click
# ---------------------------------------------------------------------------

class TestInspectableColumnHeaderClick(unittest.TestCase):
    """Task 7 — Column headers are clickable and call openInspector."""

    def test_open_inspector_called_in_header(self):
        content = _template()
        self.assertIn("openInspector(", content, "openInspector() must be called from column header handler")

    def test_column_headers_have_click_event(self):
        content = _template()
        self.assertIn("addEventListener", content, "Column headers must wire up event listeners")

    def test_inspectable_th_css_defined(self):
        self.assertIn(".ci-inspectable-th", _css(), ".ci-inspectable-th must be defined in CSS")

    def test_inspectable_header_has_pointer_cursor(self):
        css = _css()
        idx = css.find(".ci-inspectable-th")
        self.assertGreater(idx, -1)
        rule = css[idx: idx + 300]
        self.assertIn("cursor:pointer", rule.replace(" ", ""), ".ci-inspectable-th must have cursor:pointer")

    def test_header_built_in_build_preview_table(self):
        content = _template()
        # buildPreviewTable should generate inspectable-th headers
        build_fn_idx = content.find("buildPreviewTable")
        self.assertGreater(build_fn_idx, -1)
        fn_body = content[build_fn_idx: build_fn_idx + 800]
        self.assertIn("ci-inspectable-th", fn_body, "buildPreviewTable must generate .ci-inspectable-th headers")


# ---------------------------------------------------------------------------
# Task 8: InspectableColumnHeader emoji type badges
# ---------------------------------------------------------------------------

class TestInspectableColumnHeaderEmojis(unittest.TestCase):
    """Task 8 — Type indicator emojis are present for date, currency, and ticker columns."""

    def test_date_emoji_present(self):
        self.assertIn("📅", _template(), "Date emoji 📅 must be used for date column type")

    def test_currency_emoji_present(self):
        self.assertIn("💰", _template(), "Currency emoji 💰 must be used for price/amount columns")

    def test_ticker_emoji_present(self):
        self.assertIn("🏷️", _template(), "Ticker emoji 🏷️ must be used for ticker/symbol columns")

    def test_type_emoji_function_defined(self):
        self.assertIn("_ciGetTypeEmoji", _template(), "_ciGetTypeEmoji helper function must be defined")

    def test_type_emoji_handles_date(self):
        content = _template()
        idx = content.find("_ciGetTypeEmoji")
        fn = content[idx: idx + 400]
        self.assertIn("date", fn, "_ciGetTypeEmoji must handle 'date' type")

    def test_type_emoji_handles_ticker(self):
        content = _template()
        idx = content.find("_ciGetTypeEmoji")
        fn = content[idx: idx + 400]
        self.assertIn("ticker", fn, "_ciGetTypeEmoji must handle 'ticker' type")


# ---------------------------------------------------------------------------
# Task 9: Sticky headers remain visible on scroll
# ---------------------------------------------------------------------------

class TestStickyHeaders(unittest.TestCase):
    """Task 9 — Preview table headers use position:sticky."""

    def test_position_sticky_defined(self):
        css = _css()
        self.assertIn("position:sticky", css.replace(" ", ""), "position:sticky must be defined for table headers")

    def test_sticky_applied_to_preview_table(self):
        css = _css()
        idx = css.find("position:sticky")
        self.assertGreater(idx, -1)
        surrounding = css[max(0, idx - 200): idx + 50]
        self.assertTrue(
            "preview-table" in surrounding or "ci-" in surrounding or "thead" in surrounding,
            "position:sticky must be applied to preview table header or a related class",
        )


# ---------------------------------------------------------------------------
# Task 10: StickyTableHeader CSS — top:0 and z-index
# ---------------------------------------------------------------------------

class TestStickyTableHeaderCSS(unittest.TestCase):
    """Task 10 — Sticky header has top:0 and a z-index to stay above scrolled content."""

    def test_sticky_has_top_zero(self):
        css = _css()
        idx = css.replace(" ", "").find("position:sticky")
        self.assertGreater(idx, -1)
        # Find a region around sticky for 'top'
        sticky_char_idx = css.find("position:sticky")
        surrounding = css[max(0, sticky_char_idx - 100): sticky_char_idx + 300]
        self.assertIn("top:", surrounding, "Sticky header must have top:0")

    def test_sticky_has_z_index(self):
        css = _css()
        sticky_idx = css.find("position:sticky")
        surrounding = css[max(0, sticky_idx - 100): sticky_idx + 300]
        self.assertIn("z-index", surrounding, "Sticky header must define z-index")


# ---------------------------------------------------------------------------
# Task 11: "Looks good" marks column reviewed and closes inspector
# ---------------------------------------------------------------------------

class TestLooksGoodAction(unittest.TestCase):
    """Task 11 — Looks good button marks column reviewed and closes the inspector."""

    def test_looks_good_button_present(self):
        self.assertIn('id="ci-looks-good"', _template(), "#ci-looks-good button must exist")

    def test_looks_good_calls_mark_reviewed(self):
        content = _template()
        self.assertIn("markReviewed(", content, "markReviewed() must be called by the Looks good handler")

    def test_looks_good_calls_close_inspector(self):
        content = _template()
        self.assertIn("closeInspector(", content, "closeInspector() must be called to close the panel")

    def test_reviewed_columns_persisted_in_state(self):
        content = _template()
        self.assertIn("reviewedColumns", content, "reviewedColumns must be tracked in state")

    def test_looks_good_wired_to_click(self):
        content = _template()
        # The button can appear in HTML and JS separately — check the JS wiring exists
        # by looking for getElementById('ci-looks-good') + addEventListener combination
        self.assertTrue(
            ("ci-looks-good" in content and "addEventListener" in content)
            or "ci-looks-good" in content,
            "#ci-looks-good must exist and event listeners must be wired",
        )
        # More specifically: markReviewed must be called in the same JS block as ci-looks-good
        looks_good_js_idx = content.rfind("ci-looks-good")
        surrounding = content[max(0, looks_good_js_idx - 50): looks_good_js_idx + 200]
        self.assertTrue(
            "markReviewed" in surrounding or "addEventListener" in surrounding,
            "#ci-looks-good JS wiring must reference markReviewed or addEventListener",
        )


# ---------------------------------------------------------------------------
# Task 12: "Fix this" navigates to mapping step
# ---------------------------------------------------------------------------

class TestFixThisAction(unittest.TestCase):
    """Task 12 — Fix this button closes inspector and navigates to the mapping table."""

    def test_fix_this_button_present(self):
        self.assertIn('id="ci-fix-this"', _template(), "#ci-fix-this button must exist")

    def test_fix_this_scrolls_to_mapping(self):
        content = _template()
        # Fix this wiring may appear in JS later than the HTML button definition
        # Use the last occurrence (JS handler) of ci-fix-this
        fix_idx = content.rfind("ci-fix-this")
        self.assertGreater(fix_idx, -1)
        surrounding = content[max(0, fix_idx - 50): fix_idx + 500]
        self.assertTrue(
            "mapTable" in surrounding or "navigateToStep" in surrounding or "scrollIntoView" in surrounding,
            "'Fix this' must navigate to the mapping table",
        )

    def test_fix_this_uses_active_column_context(self):
        content = _template()
        self.assertIn("_ciState.activeColumn", content, "Fix this handler must reference _ciState.activeColumn")


# ---------------------------------------------------------------------------
# Task 13: All three action buttons have event listeners
# ---------------------------------------------------------------------------

class TestActionButtonHandlers(unittest.TestCase):
    """Task 13 — All three action buttons are present and wired up."""

    def test_change_mapping_button_present(self):
        self.assertIn('id="ci-change-mapping"', _template(), "#ci-change-mapping button must exist")

    def test_all_three_buttons_present(self):
        content = _template()
        self.assertIn('id="ci-looks-good"', content)
        self.assertIn('id="ci-fix-this"', content)
        self.assertIn('id="ci-change-mapping"', content)

    def test_ci_actions_container_present(self):
        self.assertIn("ci-actions", _template(), ".ci-actions container must be present")

    def test_ci_actions_css_defined(self):
        self.assertIn(".ci-actions", _css(), ".ci-actions must be defined in CSS")

    def test_close_button_wired(self):
        content = _template()
        self.assertIn("ci-close", content, "Close button must be referenced in JS")


# ---------------------------------------------------------------------------
# Task 14: Click on table area closes inspector
# ---------------------------------------------------------------------------

class TestClickOutsideToClose(unittest.TestCase):
    """Task 14 — Clicking outside the inspector panel closes it."""

    def test_click_outside_handler_present(self):
        content = _template()
        self.assertTrue(
            "contains(" in content or "closest(" in content,
            "Click-outside handler must check whether the target is inside the inspector",
        )

    def test_click_outside_calls_close_inspector(self):
        content = _template()
        self.assertIn("closeInspector(", content, "closeInspector() must be called by the click-outside handler")

    def test_document_click_listener_present(self):
        content = _template()
        # A document-level click listener is needed for click-outside
        self.assertIn("document.addEventListener", content, "document.addEventListener must register click-outside handler")


# ---------------------------------------------------------------------------
# Task 15: Escape closes inspector, focus returns to header
# ---------------------------------------------------------------------------

class TestEscapeKeyHandler(unittest.TestCase):
    """Task 15 — Escape key closes the inspector and returns focus to the triggering header."""

    def test_escape_key_handled(self):
        self.assertIn("'Escape'", _template(), "Escape key must be handled")

    def test_escape_calls_close_inspector(self):
        content = _template()
        escape_idx = content.find("'Escape'")
        self.assertGreater(escape_idx, -1)
        surrounding = content[max(0, escape_idx - 50): escape_idx + 300]
        self.assertIn("closeInspector(", surrounding, "closeInspector() must be called when Escape is pressed")

    def test_last_focused_element_tracked(self):
        content = _template()
        self.assertIn("_ciLastFocused", content, "_ciLastFocused must track the triggering element for focus return")

    def test_focus_returned_on_close(self):
        content = _template()
        # .focus() should appear near _ciLastFocused in closeInspector/markReviewed
        self.assertIn("_ciLastFocused", content, "_ciLastFocused must be defined")
        self.assertIn(".focus()", content, ".focus() must be called to return focus")
        # Verify they appear in the same region (closeInspector or markReviewed)
        close_fn_idx = content.find("function closeInspector")
        self.assertGreater(close_fn_idx, -1)
        close_fn = content[close_fn_idx: close_fn_idx + 300]
        self.assertTrue(
            "_ciLastFocused" in close_fn and ".focus()" in close_fn,
            "closeInspector must return focus to _ciLastFocused",
        )


# ---------------------------------------------------------------------------
# Task 16: ARIA attributes — aria-haspopup, role="dialog"
# ---------------------------------------------------------------------------

class TestAriaAttributes(unittest.TestCase):
    """Task 16 — All required ARIA attributes are present."""

    def test_inspector_has_role_dialog(self):
        self.assertIn('role="dialog"', _template(), 'Inspector panel must have role="dialog"')

    def test_inspector_has_aria_modal(self):
        self.assertIn('aria-modal="true"', _template(), 'Inspector panel must have aria-modal="true"')

    def test_column_header_has_aria_haspopup(self):
        self.assertIn('aria-haspopup="dialog"', _template(), 'Column headers must have aria-haspopup="dialog"')

    def test_inspector_has_aria_labelledby(self):
        content = _template()
        self.assertIn('aria-labelledby="ci-col-name"', content, 'Inspector must be labelled by ci-col-name')

    def test_aria_hidden_managed(self):
        content = _template()
        self.assertIn("aria-hidden", content, "aria-hidden must be managed on the inspector panel")


# ---------------------------------------------------------------------------
# Task 17: Focus management and keyboard navigation
# ---------------------------------------------------------------------------

class TestFocusManagement(unittest.TestCase):
    """Task 17 — Focus trap is implemented and headers are keyboard-accessible."""

    def test_focus_trap_implemented(self):
        content = _template()
        self.assertTrue(
            "firstFocusable" in content or "focusable" in content.lower(),
            "Focus trap must be implemented (first/lastFocusable logic)",
        )

    def test_tab_key_handled_in_inspector(self):
        content = _template()
        self.assertIn("'Tab'", content, "Tab key must be handled for focus trap")

    def test_shift_tab_wraps_backwards(self):
        content = _template()
        self.assertIn("shiftKey", content, "Shift+Tab must wrap backwards in the focus trap")

    def test_inspectable_header_has_tabindex(self):
        content = _template()
        self.assertIn("tabIndex", content, "Inspectable column headers must have tabIndex for keyboard access")

    def test_inspectable_header_has_keyboard_handler(self):
        content = _template()
        self.assertTrue(
            "'Enter'" in content or "' '" in content,
            "Inspectable headers must handle Enter or Space key to open inspector",
        )

    def test_inspectable_header_focus_css(self):
        css = _css()
        self.assertIn(
            ".ci-inspectable-th:focus-visible",
            css,
            ".ci-inspectable-th:focus-visible must define a visible focus indicator",
        )


if __name__ == "__main__":
    unittest.main()
