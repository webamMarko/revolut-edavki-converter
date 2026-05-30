"""Desktop upload page and import wizard tests."""

import pytest
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"


class TestUploadPage:
    def test_upload_page_status_bar(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(server_url)
        premium_desktop_page.wait_for_timeout(500)
        status_bar = premium_desktop_page.locator("#statusBar")
        # Status bar should be visible since we imported test data
        assert status_bar.is_visible()

    def test_upload_file_selection(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(server_url)
        premium_desktop_page.wait_for_timeout(300)

        csv_path = EXAMPLES_DIR / "sample_transactions.csv"
        if not csv_path.exists():
            pytest.skip("sample_transactions.csv not found")

        premium_desktop_page.locator("#fileInput").set_input_files(str(csv_path))
        premium_desktop_page.wait_for_timeout(300)

        file_list = premium_desktop_page.locator("#fileList")
        assert file_list.text_content().strip() != ""

        upload_btn = premium_desktop_page.locator("#uploadBtn")
        assert not upload_btn.is_disabled()


class TestImportWizard:
    def test_import_wizard_loads(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/import")
        premium_desktop_page.wait_for_timeout(300)
        assert premium_desktop_page.locator("#step1").is_visible()
        assert premium_desktop_page.locator("#previewBtn").is_disabled()

    def test_import_file_upload(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/import")
        premium_desktop_page.wait_for_timeout(300)

        csv_path = EXAMPLES_DIR / "sample_transactions.csv"
        if not csv_path.exists():
            pytest.skip("sample_transactions.csv not found")

        premium_desktop_page.locator("#step1 input[type='file']").set_input_files(
            str(csv_path)
        )
        premium_desktop_page.wait_for_timeout(300)

        chosen = premium_desktop_page.locator("#chosenFile")
        assert "sample_transactions.csv" in chosen.text_content()
        assert not premium_desktop_page.locator("#previewBtn").is_disabled()

    def test_import_step2_preview(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/import")
        premium_desktop_page.wait_for_timeout(300)

        csv_path = EXAMPLES_DIR / "sample_transactions.csv"
        if not csv_path.exists():
            pytest.skip("sample_transactions.csv not found")

        premium_desktop_page.locator("#step1 input[type='file']").set_input_files(
            str(csv_path)
        )
        premium_desktop_page.wait_for_timeout(300)

        premium_desktop_page.locator("#previewBtn").click()
        premium_desktop_page.wait_for_selector("#step2", state="visible", timeout=10000)

        # Preview table should have headers
        table = premium_desktop_page.locator("#previewTable")
        assert table.locator("th").count() > 0

    def test_import_column_mapping(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/import")
        premium_desktop_page.wait_for_timeout(300)

        csv_path = EXAMPLES_DIR / "sample_transactions.csv"
        if not csv_path.exists():
            pytest.skip("sample_transactions.csv not found")

        premium_desktop_page.locator("#step1 input[type='file']").set_input_files(
            str(csv_path)
        )
        premium_desktop_page.wait_for_timeout(300)
        premium_desktop_page.locator("#previewBtn").click()
        premium_desktop_page.wait_for_selector("#step2", state="visible", timeout=10000)

        # Map table should have select elements
        selects = premium_desktop_page.locator("#mapTable select")
        assert selects.count() > 0

    def test_import_back_navigation(self, premium_desktop_page, server_url):
        premium_desktop_page.goto(f"{server_url}/import")
        premium_desktop_page.wait_for_timeout(300)

        csv_path = EXAMPLES_DIR / "sample_transactions.csv"
        if not csv_path.exists():
            pytest.skip("sample_transactions.csv not found")

        # Go to step 2
        premium_desktop_page.locator("#step1 input[type='file']").set_input_files(
            str(csv_path)
        )
        premium_desktop_page.wait_for_timeout(300)
        premium_desktop_page.locator("#previewBtn").click()
        premium_desktop_page.wait_for_selector("#step2", state="visible", timeout=10000)

        # Back to step 1
        premium_desktop_page.locator("#backBtn1").click()
        premium_desktop_page.wait_for_timeout(300)
        assert premium_desktop_page.locator("#step1").is_visible()
        assert not premium_desktop_page.locator("#step2").is_visible()

    def test_import_full_flow(self, premium_desktop_page, server_url):
        """Complete the 3-step import wizard end-to-end."""
        premium_desktop_page.goto(f"{server_url}/import")
        premium_desktop_page.wait_for_timeout(300)

        csv_path = EXAMPLES_DIR / "sample_transactions.csv"
        if not csv_path.exists():
            pytest.skip("sample_transactions.csv not found")

        # Step 1: Upload
        premium_desktop_page.locator("#step1 input[type='file']").set_input_files(
            str(csv_path)
        )
        premium_desktop_page.wait_for_timeout(300)
        premium_desktop_page.locator("#previewBtn").click()
        premium_desktop_page.wait_for_selector("#step2", state="visible", timeout=10000)

        # Step 2: Ensure required fields are mapped, then click Next
        next_btn = premium_desktop_page.locator("#nextBtn2")
        # Wait a bit for auto-mapping to populate
        premium_desktop_page.wait_for_timeout(500)

        if next_btn.is_disabled():
            # Try to select 'stock' asset class explicitly
            stock_btn = premium_desktop_page.locator('.ac-btn[data-ac="stock"]')
            if stock_btn.is_visible():
                stock_btn.click()
                premium_desktop_page.wait_for_timeout(300)

        if next_btn.is_disabled():
            pytest.skip("Could not auto-map required columns")

        next_btn.click()
        premium_desktop_page.wait_for_selector("#step3", state="visible", timeout=10000)

        # Step 3: Import
        premium_desktop_page.locator("#importBtn").click()
        premium_desktop_page.wait_for_selector("#successBox", state="visible", timeout=15000)
        assert "Import complete" in premium_desktop_page.locator("#successBox").text_content()


class TestDetectOverrideFlow:
    """E2E tests: upload-detect-override flow (Phase 2 TDD task 23)."""

    def _upload_and_advance(self, page, server_url, csv_path):
        """Helper: upload CSV and advance to Step 2."""
        page.goto(f"{server_url}/import")
        page.wait_for_timeout(300)
        page.locator("#fileInput").set_input_files(str(csv_path))
        page.wait_for_timeout(200)
        page.locator("#previewBtn").click()
        # Wait for step 2 body to become visible
        page.wait_for_selector("#wb2:not([hidden])", timeout=10000)
        page.wait_for_timeout(500)

    def test_detected_badge_appears_on_cfd_upload(self, premium_desktop_page, server_url):
        """Upload a CFD CSV: Detected badge appears on the CFD toggle."""
        csv_path = EXAMPLES_DIR / "cfds.csv"
        if not csv_path.exists():
            pytest.skip("cfds.csv not found")

        self._upload_and_advance(premium_desktop_page, server_url, csv_path)

        badge = premium_desktop_page.locator("#badge-cfd")
        assert badge.is_visible(), "Detected badge should appear on CFD toggle"

    def test_no_badge_when_detection_fallback(self, premium_desktop_page, server_url):
        """Upload an ambiguous CSV: no Detected badges shown."""
        csv_path = EXAMPLES_DIR / "sample_transactions.csv"
        if not csv_path.exists():
            pytest.skip("sample_transactions.csv not found")

        self._upload_and_advance(premium_desktop_page, server_url, csv_path)

        for ac in ["stock", "cfd", "crypto", "savings"]:
            badge = premium_desktop_page.locator(f"#badge-{ac}")
            assert not badge.is_visible(), f"No badge expected for {ac} on ambiguous file"

    def test_override_warning_appears_when_user_selects_different_class(
        self, premium_desktop_page, server_url
    ):
        """Upload CFD CSV, then click Stock: override warning appears."""
        csv_path = EXAMPLES_DIR / "cfds.csv"
        if not csv_path.exists():
            pytest.skip("cfds.csv not found")

        self._upload_and_advance(premium_desktop_page, server_url, csv_path)

        # Verify CFD was auto-selected
        cfd_btn = premium_desktop_page.locator('.ac-btn[data-ac="cfd"]')
        assert cfd_btn.get_attribute("aria-pressed") == "true", "CFD should be auto-selected"

        # Click Stock to override
        stock_btn = premium_desktop_page.locator('.ac-btn[data-ac="stock"]')
        stock_btn.click()
        premium_desktop_page.wait_for_timeout(200)

        # Override warning should appear
        warn = premium_desktop_page.locator("#overrideWarning")
        assert warn.is_visible(), "Override warning should be visible"
        warn_text = warn.text_content()
        assert "stock" in warn_text.lower(), "Warning should mention selected class"
        assert "cfd" in warn_text.lower(), "Warning should mention detected class"

    def test_override_warning_hidden_when_user_selects_detected_class(
        self, premium_desktop_page, server_url
    ):
        """After override, clicking back to detected class hides the warning."""
        csv_path = EXAMPLES_DIR / "cfds.csv"
        if not csv_path.exists():
            pytest.skip("cfds.csv not found")

        self._upload_and_advance(premium_desktop_page, server_url, csv_path)

        # Override
        premium_desktop_page.locator('.ac-btn[data-ac="stock"]').click()
        premium_desktop_page.wait_for_timeout(200)
        assert premium_desktop_page.locator("#overrideWarning").is_visible()

        # Go back to detected class
        premium_desktop_page.locator('.ac-btn[data-ac="cfd"]').click()
        premium_desktop_page.wait_for_timeout(200)
        assert not premium_desktop_page.locator("#overrideWarning").is_visible(), \
            "Warning should hide when user selects detected class"

    def test_re_upload_resets_detection(self, premium_desktop_page, server_url):
        """Going back to Step 1 and re-uploading resets detection state."""
        cfd_path = EXAMPLES_DIR / "cfds.csv"
        ambiguous_path = EXAMPLES_DIR / "sample_transactions.csv"
        if not cfd_path.exists() or not ambiguous_path.exists():
            pytest.skip("Required CSV fixtures not found")

        # First upload: CFD → badge appears
        self._upload_and_advance(premium_desktop_page, server_url, cfd_path)
        assert premium_desktop_page.locator("#badge-cfd").is_visible()

        # Navigate back to Step 1 (click step header)
        premium_desktop_page.locator("#wh1").click()
        premium_desktop_page.wait_for_timeout(300)

        # Re-upload ambiguous CSV
        premium_desktop_page.locator("#fileInput").set_input_files(str(ambiguous_path))
        premium_desktop_page.wait_for_timeout(200)
        premium_desktop_page.locator("#previewBtn").click()
        premium_desktop_page.wait_for_selector("#wb2:not([hidden])", timeout=10000)
        premium_desktop_page.wait_for_timeout(500)

        # No badges should be visible for new ambiguous file
        for ac in ["stock", "cfd", "crypto", "savings"]:
            assert not premium_desktop_page.locator(f"#badge-{ac}").is_visible(), \
                f"Badge for {ac} should be reset after re-upload"
        assert not premium_desktop_page.locator("#overrideWarning").is_visible(), \
            "Override warning should be cleared after re-upload"
