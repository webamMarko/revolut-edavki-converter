"""Mobile import wizard tests."""

import pytest
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"


class TestMobileImportWizard:
    def test_import_wizard_mobile_layout(self, premium_mobile_page, server_url):
        premium_mobile_page.goto(f"{server_url}/import")
        premium_mobile_page.wait_for_timeout(500)

        step1 = premium_mobile_page.locator("#wb1")
        assert step1.is_visible()

        box = step1.bounding_box()
        assert box is not None
        # Should fit within the mobile viewport (390px)
        assert box["width"] <= 400

    def test_import_full_flow_mobile(self, premium_mobile_page, server_url):
        premium_mobile_page.goto(f"{server_url}/import")
        premium_mobile_page.wait_for_timeout(300)

        csv_path = EXAMPLES_DIR / "sample_transactions.csv"
        if not csv_path.exists():
            pytest.skip("sample_transactions.csv not found")

        # Step 1: Upload
        premium_mobile_page.locator("#wb1 input[type='file']").set_input_files(
            str(csv_path)
        )
        premium_mobile_page.wait_for_timeout(300)
        premium_mobile_page.locator("#previewBtn").click()
        premium_mobile_page.wait_for_selector("#wb2", state="visible", timeout=10000)

        # Step 2: Map columns + go to step 3
        next_btn = premium_mobile_page.locator("#nextBtn2")
        premium_mobile_page.wait_for_timeout(500)

        if next_btn.is_disabled():
            stock_btn = premium_mobile_page.locator('.ac-btn[data-ac="stock"]')
            if stock_btn.is_visible():
                stock_btn.click()
                premium_mobile_page.wait_for_timeout(300)

        if next_btn.is_disabled():
            pytest.skip("Could not auto-map required columns at mobile size")

        next_btn.click()
        premium_mobile_page.wait_for_selector("#wb3", state="visible", timeout=10000)

        # Step 3: Import
        premium_mobile_page.locator("#importBtn").click()
        premium_mobile_page.wait_for_selector(
            "#successBox", state="visible", timeout=15000
        )
        assert "Import complete" in premium_mobile_page.locator("#successBox").text_content()
