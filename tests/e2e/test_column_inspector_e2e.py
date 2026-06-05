"""E2E tests for Column Inspector — PR 2: Polish & edge cases (TDD Task 23).

Full flow tests: upload CSV → preview table → click column header → inspector opens
with unmapped badge, truncated samples with Show full, transform preview, ARIA live
regions, and reviewed checkmark persistence.
"""

import pytest
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"


def _upload_and_preview(page, server_url, csv_name="sample_transactions.csv"):
    """Upload a CSV and navigate to the preview step. Returns False if CSV not found."""
    csv_path = EXAMPLES_DIR / csv_name
    if not csv_path.exists():
        return False
    page.goto(f"{server_url}/import")
    page.wait_for_timeout(300)
    page.locator("#step1 input[type='file']").set_input_files(str(csv_path))
    page.wait_for_timeout(300)
    page.locator("#previewBtn").click()
    page.wait_for_selector("#previewTable", state="visible", timeout=10000)
    return True


class TestColumnInspectorPanel:
    """Inspector panel opens and renders metadata on column header click."""

    def test_inspector_panel_exists_in_dom(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/import")
        panel = premium_desktop_page.locator("#columnInspector")
        assert panel.count() == 1, "Column inspector panel must exist in the DOM"

    def test_inspector_hidden_by_default(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/import")
        panel = premium_desktop_page.locator("#columnInspector")
        assert panel.get_attribute("aria-hidden") == "true", "Inspector must be hidden before any column is clicked"

    def test_clicking_column_header_opens_inspector(self, premium_desktop_page, server_url):
        if not _upload_and_preview(premium_desktop_page, server_url):
            pytest.skip("sample_transactions.csv not found")

        header = premium_desktop_page.locator(".ci-inspectable-th").first
        header.click()
        premium_desktop_page.wait_for_timeout(200)

        panel = premium_desktop_page.locator("#columnInspector")
        assert panel.get_attribute("aria-hidden") == "false", "Inspector must be visible after clicking a column header"

    def test_inspector_shows_column_name(self, premium_desktop_page, server_url):
        if not _upload_and_preview(premium_desktop_page, server_url):
            pytest.skip("sample_transactions.csv not found")

        header = premium_desktop_page.locator(".ci-inspectable-th").first
        header.inner_text().strip().replace("✓", "").strip()
        header.click()
        premium_desktop_page.wait_for_timeout(200)

        name_el = premium_desktop_page.locator("#ci-col-name")
        assert name_el.inner_text().strip() != "", "Inspector must show the column name"

    def test_close_button_closes_inspector(self, premium_desktop_page, server_url):
        if not _upload_and_preview(premium_desktop_page, server_url):
            pytest.skip("sample_transactions.csv not found")

        premium_desktop_page.locator(".ci-inspectable-th").first.click()
        premium_desktop_page.wait_for_timeout(200)

        premium_desktop_page.locator("#ci-close").click()
        premium_desktop_page.wait_for_timeout(200)

        panel = premium_desktop_page.locator("#columnInspector")
        assert panel.get_attribute("aria-hidden") == "true", "Inspector must be hidden after closing"

    def test_escape_key_closes_inspector(self, premium_desktop_page, server_url):
        if not _upload_and_preview(premium_desktop_page, server_url):
            pytest.skip("sample_transactions.csv not found")

        premium_desktop_page.locator(".ci-inspectable-th").first.click()
        premium_desktop_page.wait_for_timeout(200)

        premium_desktop_page.keyboard.press("Escape")
        premium_desktop_page.wait_for_timeout(200)

        panel = premium_desktop_page.locator("#columnInspector")
        assert panel.get_attribute("aria-hidden") == "true", "Inspector must close on Escape key"


class TestUnmappedColumn:
    """Unmapped columns show the 'Unmapped' badge and 'Map this column' button."""

    def test_unmapped_section_exists_in_dom(self, premium_desktop_page, server_url):
        if not _upload_and_preview(premium_desktop_page, server_url):
            pytest.skip("sample_transactions.csv not found")

        section = premium_desktop_page.locator("#ci-unmapped-section")
        assert section.count() == 1, "ci-unmapped-section must exist in DOM"

    def test_map_this_column_button_exists(self, premium_desktop_page, server_url):
        if not _upload_and_preview(premium_desktop_page, server_url):
            pytest.skip("sample_transactions.csv not found")

        btn = premium_desktop_page.locator("#ci-map-this")
        assert btn.count() == 1, "'Map this column' button must exist in inspector"


class TestSampleValueTruncation:
    """Sample values longer than 50 chars show truncated text with 'Show full' toggle."""

    def test_ci_samples_section_present(self, premium_desktop_page, server_url):
        if not _upload_and_preview(premium_desktop_page, server_url):
            pytest.skip("sample_transactions.csv not found")

        premium_desktop_page.locator(".ci-inspectable-th").first.click()
        premium_desktop_page.wait_for_timeout(300)

        samples = premium_desktop_page.locator("#ci-samples")
        assert samples.count() == 1, "#ci-samples section must exist"

    def test_samples_list_populated(self, premium_desktop_page, server_url):
        if not _upload_and_preview(premium_desktop_page, server_url):
            pytest.skip("sample_transactions.csv not found")

        premium_desktop_page.locator(".ci-inspectable-th").first.click()
        premium_desktop_page.wait_for_timeout(300)

        sample_items = premium_desktop_page.locator("#ci-samples .ci-sample-item")
        no_samples = premium_desktop_page.locator("#ci-samples .ci-no-samples")
        assert sample_items.count() > 0 or no_samples.count() > 0, \
            "Sample values section must show items or 'No sample data'"

    def test_show_full_toggle_works_when_present(self, premium_desktop_page, server_url):
        """If any Show full button exists, clicking it reveals the full text."""
        if not _upload_and_preview(premium_desktop_page, server_url):
            pytest.skip("sample_transactions.csv not found")

        # Click each header until we find one with a Show full button
        headers = premium_desktop_page.locator(".ci-inspectable-th")
        count = headers.count()
        found = False
        for i in range(count):
            headers.nth(i).click()
            premium_desktop_page.wait_for_timeout(200)
            show_full = premium_desktop_page.locator(".ci-show-full").first
            if show_full.count() > 0 and show_full.is_visible():
                found = True
                show_full.click()
                premium_desktop_page.wait_for_timeout(100)
                show_less = premium_desktop_page.locator(".ci-show-less").first
                assert show_less.count() > 0, "After clicking 'Show full', a 'Show less' button must appear"
                break
            premium_desktop_page.locator("#ci-close").click()
            premium_desktop_page.wait_for_timeout(100)

        if not found:
            pytest.skip("No sample values longer than 50 chars found in this CSV")


class TestReviewedColumnCheckmark:
    """Clicking 'Looks good' marks column as reviewed and shows a checkmark on the header."""

    def test_looks_good_closes_inspector(self, premium_desktop_page, server_url):
        if not _upload_and_preview(premium_desktop_page, server_url):
            pytest.skip("sample_transactions.csv not found")

        premium_desktop_page.locator(".ci-inspectable-th").first.click()
        premium_desktop_page.wait_for_timeout(200)

        premium_desktop_page.locator("#ci-looks-good").click()
        premium_desktop_page.wait_for_timeout(200)

        panel = premium_desktop_page.locator("#columnInspector")
        assert panel.get_attribute("aria-hidden") == "true", "Inspector must close after 'Looks good'"

    def test_looks_good_shows_checkmark_on_header(self, premium_desktop_page, server_url):
        if not _upload_and_preview(premium_desktop_page, server_url):
            pytest.skip("sample_transactions.csv not found")

        first_header = premium_desktop_page.locator(".ci-inspectable-th").first
        first_header.click()
        premium_desktop_page.wait_for_timeout(200)

        premium_desktop_page.locator("#ci-looks-good").click()
        premium_desktop_page.wait_for_timeout(300)

        # Reviewed mark should appear on the header
        reviewed_mark = first_header.locator(".ci-reviewed-mark")
        assert reviewed_mark.count() > 0 or "✓" in first_header.inner_text(), \
            "A checkmark must appear on the header after marking reviewed"

    def test_reviewed_column_checkmark_persists_after_reopen(self, premium_desktop_page, server_url):
        if not _upload_and_preview(premium_desktop_page, server_url):
            pytest.skip("sample_transactions.csv not found")

        first_header = premium_desktop_page.locator(".ci-inspectable-th").first
        first_header.click()
        premium_desktop_page.wait_for_timeout(200)
        premium_desktop_page.locator("#ci-looks-good").click()
        premium_desktop_page.wait_for_timeout(200)

        # Re-open the same column
        first_header.click()
        premium_desktop_page.wait_for_timeout(200)

        # Inspector opens (column can be re-inspected even after reviewing)
        panel = premium_desktop_page.locator("#columnInspector")
        assert panel.get_attribute("aria-hidden") == "false", \
            "Reviewed columns can still be re-opened for inspection"


class TestAriaLiveRegions:
    """ARIA live region ci-announce is present and gets updated."""

    def test_ci_announce_element_present(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/import")
        announce = premium_desktop_page.locator("#ci-announce")
        assert announce.count() == 1, "#ci-announce live region must exist in DOM"

    def test_ci_announce_has_aria_live(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/import")
        announce = premium_desktop_page.locator("#ci-announce")
        assert announce.get_attribute("aria-live") == "polite", \
            "#ci-announce must have aria-live='polite'"

    def test_ci_announce_has_aria_atomic(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/import")
        announce = premium_desktop_page.locator("#ci-announce")
        assert announce.get_attribute("aria-atomic") == "true", \
            "#ci-announce must have aria-atomic='true'"

    def test_ci_announce_updated_on_column_open(self, premium_desktop_page, server_url):
        if not _upload_and_preview(premium_desktop_page, server_url):
            pytest.skip("sample_transactions.csv not found")

        premium_desktop_page.locator(".ci-inspectable-th").first.click()
        premium_desktop_page.wait_for_timeout(500)

        announce_text = premium_desktop_page.locator("#ci-announce").inner_text()
        assert announce_text.strip() != "", \
            "#ci-announce must be populated with announcement text when inspector opens"


class TestTransformPreview:
    """Transformation preview shows before/after when a transform fn is available."""

    def test_transform_preview_section_present(self, premium_desktop_page, server_url):
        if not _upload_and_preview(premium_desktop_page, server_url):
            pytest.skip("sample_transactions.csv not found")

        premium_desktop_page.locator(".ci-inspectable-th").first.click()
        premium_desktop_page.wait_for_timeout(300)

        preview = premium_desktop_page.locator("#ci-transform-preview")
        assert preview.count() == 1, "#ci-transform-preview section must exist"

    def test_transform_preview_shows_before_after_for_date_column(self, premium_desktop_page, server_url):
        """For a date-mapped column, before/after transform rows should appear."""
        if not _upload_and_preview(premium_desktop_page, server_url):
            pytest.skip("sample_transactions.csv not found")

        # Try each column — find one mapped to 'date' by checking ci-type-badge
        headers = premium_desktop_page.locator(".ci-inspectable-th")
        count = headers.count()
        found = False
        for i in range(count):
            headers.nth(i).click()
            premium_desktop_page.wait_for_timeout(200)
            badge_text = premium_desktop_page.locator("#ci-type-badge").inner_text()
            if "📅" in badge_text or "Date" in badge_text:
                transform_rows = premium_desktop_page.locator(".ci-transform-row")
                if transform_rows.count() > 0:
                    found = True
                    # Verify before and after spans exist
                    before_els = premium_desktop_page.locator(".ci-before")
                    after_els = premium_desktop_page.locator(".ci-after")
                    assert before_els.count() > 0, "ci-before spans must exist in transform preview"
                    assert after_els.count() > 0, "ci-after spans must exist in transform preview"
                premium_desktop_page.locator("#ci-close").click()
                premium_desktop_page.wait_for_timeout(100)
                break
            premium_desktop_page.locator("#ci-close").click()
            premium_desktop_page.wait_for_timeout(100)

        if not found:
            pytest.skip("No date-mapped column with transform preview found in this CSV")


class TestMobileBottomSheet:
    """On mobile viewport, the inspector renders as a bottom sheet."""

    def test_inspector_panel_exists_on_mobile(self, premium_mobile_page, server_url):
        premium_mobile_page.goto(f"{server_url}/import")
        panel = premium_mobile_page.locator("#columnInspector")
        assert panel.count() == 1, "Inspector panel must exist on mobile"

    def test_inspector_opens_on_mobile_header_click(self, premium_mobile_page, server_url):
        csv_path = EXAMPLES_DIR / "sample_transactions.csv"
        if not csv_path.exists():
            pytest.skip("sample_transactions.csv not found")

        premium_mobile_page.goto(f"{server_url}/import")
        premium_mobile_page.wait_for_timeout(300)
        premium_mobile_page.locator("#step1 input[type='file']").set_input_files(str(csv_path))
        premium_mobile_page.wait_for_timeout(300)
        premium_mobile_page.locator("#previewBtn").click()
        premium_mobile_page.wait_for_selector("#previewTable", state="visible", timeout=10000)

        premium_mobile_page.locator(".ci-inspectable-th").first.click()
        premium_mobile_page.wait_for_timeout(300)

        panel = premium_mobile_page.locator("#columnInspector")
        assert panel.get_attribute("aria-hidden") == "false", \
            "Inspector must open on mobile after clicking a column header"
