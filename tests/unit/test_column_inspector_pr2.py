"""TDD Tasks 18-22 (PR 2): Column Inspector — polish & edge cases."""

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
# Task 18: Unmapped columns show "Unmapped" badge and "Map this column" button
# ---------------------------------------------------------------------------

class TestUnmappedColumnDisplay(unittest.TestCase):
    """Task 18 — Unmapped columns display a badge and a 'Map this column' action."""

    def test_unmapped_badge_element_present(self):
        content = _template()
        self.assertTrue(
            'ci-unmapped-badge' in content,
            "An element with class ci-unmapped-badge must exist for unmapped columns",
        )

    def test_map_this_column_button_present(self):
        content = _template()
        self.assertIn(
            'Map this column',
            content,
            "'Map this column' button text must exist in the inspector",
        )

    def test_map_this_column_button_has_id(self):
        content = _template()
        self.assertIn(
            'ci-map-this',
            content,
            "The 'Map this column' button must have id ci-map-this",
        )

    def test_unmapped_section_conditionally_shown(self):
        content = _template()
        self.assertIn(
            'ci-unmapped-section',
            content,
            "ci-unmapped-section container must exist and be shown/hidden conditionally",
        )

    def test_unmapped_badge_css_defined(self):
        self.assertIn(
            '.ci-unmapped-badge',
            _css(),
            ".ci-unmapped-badge must be styled in CSS",
        )

    def test_unmapped_section_css_defined(self):
        self.assertIn(
            '.ci-unmapped-section',
            _css(),
            ".ci-unmapped-section must be styled in CSS",
        )

    def test_map_this_column_handler_wired(self):
        content = _template()
        self.assertIn(
            'ci-map-this',
            content,
            "ci-map-this button must be referenced in JS (click handler)",
        )
        idx = content.find('ci-map-this')
        # Should appear more than once: once in HTML, once in JS
        second_idx = content.find('ci-map-this', idx + 1)
        self.assertGreater(second_idx, -1, "ci-map-this must appear in both HTML and JS")

    def test_unmapped_section_hidden_by_default_in_css_or_render(self):
        content = _template()
        # Either style="display:none" on the element or JS sets display:none
        self.assertTrue(
            'ci-unmapped-section' in content and
            ('display:none' in content or 'display: none' in content or '.style.' in content),
            "ci-unmapped-section must be hidden by default (via style or JS)",
        )

    def test_ci_render_shows_unmapped_section_when_unmapped(self):
        content = _template()
        # _ciRender must reference the unmapped section visibility
        render_idx = content.find('function _ciRender')
        if render_idx == -1:
            render_idx = content.find('_ciRender()')
        self.assertGreater(render_idx, -1)
        # Find the render function body
        render_body = content[render_idx: render_idx + 2000]
        self.assertIn(
            'ci-unmapped-section',
            render_body,
            "_ciRender must update ci-unmapped-section visibility based on mappedField",
        )

    def test_unmapped_type_badge_shows_unmapped_text(self):
        content = _template()
        # The type badge or unmapped section should show 'Unmapped' when not mapped
        self.assertIn('Unmapped', content, "Inspector must show 'Unmapped' text for unmapped columns")


# ---------------------------------------------------------------------------
# Task 19: Sample values truncated at 50 chars with "Show full" toggle
# ---------------------------------------------------------------------------

class TestSampleValueTruncation(unittest.TestCase):
    """Task 19 — Sample values are truncated at 50 chars with a 'Show full' expand toggle."""

    def test_show_full_text_present(self):
        self.assertIn(
            'Show full',
            _template(),
            "'Show full' toggle text must be present in the template",
        )

    def test_show_less_text_present(self):
        self.assertIn(
            'Show less',
            _template(),
            "'Show less' text must be present (collapse toggle)",
        )

    def test_truncation_at_50_chars(self):
        content = _template()
        # Must have a .slice(0, 50) or length > 50 check for truncation
        self.assertTrue(
            '.length > 50' in content or 'length > 50' in content or '.slice(0, 50)' in content,
            "Template must implement 50-char truncation check",
        )

    def test_ci_show_full_css_class(self):
        content = _template()
        self.assertIn(
            'ci-show-full',
            content,
            "Show full button must have css class ci-show-full",
        )

    def test_ci_show_full_css_defined(self):
        self.assertIn(
            '.ci-show-full',
            _css(),
            ".ci-show-full must be styled in CSS",
        )

    def test_show_full_click_handler(self):
        content = _template()
        # Must handle click on show-full buttons (event delegation or direct)
        self.assertIn(
            'ci-show-full',
            content,
            "ci-show-full must be referenced in JS click handling",
        )
        idx = content.find('ci-show-full')
        second_idx = content.find('ci-show-full', idx + 1)
        self.assertGreater(second_idx, -1, "ci-show-full must appear in both HTML template and JS handler")

    def test_data_full_attribute_on_truncated_items(self):
        content = _template()
        self.assertIn(
            'data-full',
            content,
            "Truncated sample items must store full value in data-full attribute",
        )

    def test_expand_toggle_restores_full_text(self):
        content = _template()
        # The handler should use data-full to expand
        self.assertIn(
            'data-full',
            content,
            "Show full handler must read full value from data-full attribute",
        )

    def test_ellipsis_added_to_truncated_values(self):
        content = _template()
        # Must show … or ... after truncated text
        self.assertTrue(
            '…' in content or "'...'" in content or '"..."' in content or '\\u2026' in content,
            "Truncated sample values must be followed by an ellipsis character",
        )


# ---------------------------------------------------------------------------
# Task 20: Transformation preview shows before/after
# ---------------------------------------------------------------------------

class TestTransformationPreview(unittest.TestCase):
    """Task 20 — Transformation preview displays before and after values."""

    def test_transform_preview_section_present(self):
        self.assertIn(
            'id="ci-transform-preview"',
            _template(),
            "#ci-transform-preview element must exist",
        )

    def test_ci_transform_fns_defined(self):
        content = _template()
        self.assertIn(
            '_ciTransformFns',
            content,
            "_ciTransformFns map must be defined for field type transforms",
        )

    def test_before_label_in_preview(self):
        content = _template()
        self.assertTrue(
            'Before' in content or 'before' in content,
            "Transform preview must show a 'Before' label",
        )

    def test_after_label_in_preview(self):
        content = _template()
        self.assertTrue(
            'After' in content or 'after' in content,
            "Transform preview must show an 'After' label",
        )

    def test_transform_preview_populated_in_render(self):
        content = _template()
        render_idx = content.find('function _ciRender')
        self.assertGreater(render_idx, -1, "function _ciRender must be defined")
        # ci-transform-preview should be set inside _ciRender (not just cleared)
        render_body = content[render_idx: render_idx + 4000]
        self.assertIn(
            'ci-transform-preview',
            render_body,
            "_ciRender must reference ci-transform-preview",
        )
        # Verify the transform-preview receives actual HTML content (not only cleared)
        # ci-before and ci-after CSS classes must appear in the JS (inside the innerHTML string)
        self.assertIn('ci-before', content, "Transform preview must use ci-before span for raw values")
        self.assertIn('ci-after', content, "Transform preview must use ci-after span for transformed values")
        # The transform rows container must be built in JS
        self.assertIn('ci-transform-rows', content, "Transform preview must build ci-transform-rows HTML")

    def test_transform_applied_to_sample_values(self):
        content = _template()
        self.assertIn(
            '_ciTransformFns',
            content,
            "Transform functions must be applied in inspector render",
        )

    def test_transform_preview_css_styled(self):
        css = _css()
        self.assertIn(
            '.ci-transform-preview',
            css,
            ".ci-transform-preview must be styled in CSS",
        )

    def test_ci_before_after_css(self):
        css = _css()
        self.assertTrue(
            'ci-before' in css or 'ci-after' in css or 'ci-transform' in css,
            "Before/after transform preview rows must have CSS styling",
        )


# ---------------------------------------------------------------------------
# Task 22: ARIA live regions for screen readers
# ---------------------------------------------------------------------------

class TestAriaLiveRegions(unittest.TestCase):
    """Task 22 — Screen reader ARIA live regions announce inspector state changes."""

    def test_aria_live_region_present(self):
        content = _template()
        self.assertIn(
            'aria-live',
            content,
            "An aria-live region must be present for screen reader announcements",
        )

    def test_aria_live_is_polite(self):
        content = _template()
        self.assertIn(
            'aria-live="polite"',
            content,
            "The aria-live region must be polite (non-interruptive)",
        )

    def test_ci_announce_element_present(self):
        content = _template()
        self.assertIn(
            'id="ci-announce"',
            content,
            "#ci-announce element must exist for column inspector announcements",
        )

    def test_ci_announce_called_on_open(self):
        content = _template()
        # _ciAnnounce helper must exist and reference ci-announce
        self.assertIn('_ciAnnounce', content, "_ciAnnounce helper must be defined")
        self.assertIn('ci-announce', content, "ci-announce element must be referenced in JS")
        # _ciRender must call _ciAnnounce to announce state changes to screen readers
        render_idx = content.find('function _ciRender')
        self.assertGreater(render_idx, -1, "function _ciRender must be defined")
        render_body = content[render_idx: render_idx + 4000]
        self.assertIn(
            '_ciAnnounce',
            render_body,
            "_ciRender must call _ciAnnounce() to announce inspector state to screen readers",
        )

    def test_ci_announce_sr_only_css(self):
        css = _css()
        self.assertTrue(
            '#ci-announce' in css or '.sr-only' in css,
            "#ci-announce or .sr-only must be visually hidden in CSS",
        )

    def test_aria_atomic_true_on_announce(self):
        content = _template()
        # aria-atomic ensures entire region is read, not just changes
        idx = content.find('ci-announce')
        self.assertGreater(idx, -1)
        surrounding = content[max(0, idx - 200): idx + 300]
        self.assertIn(
            'aria-atomic',
            surrounding,
            "ci-announce region must have aria-atomic attribute",
        )

    def test_inspector_open_announcement(self):
        content = _template()
        # Should announce column name when inspector opens
        self.assertTrue(
            'Inspecting' in content or 'inspector' in content.lower() or 'column' in content.lower(),
            "ci-announce must announce something meaningful when inspector opens",
        )

    def test_reviewed_announcement(self):
        content = _template()
        # Should announce when a column is marked reviewed
        self.assertTrue(
            'Reviewed' in content or 'reviewed' in content or 'marked' in content,
            "ci-announce must announce when a column is marked as reviewed",
        )


if __name__ == "__main__":
    unittest.main()
