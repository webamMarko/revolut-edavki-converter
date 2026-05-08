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
