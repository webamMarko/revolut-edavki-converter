"""TDD tests for SAA-577-4: Dividend Tax pagination + expandable country rows.

Spec (SAA-577 Task 4):
- renderDivTax() in dividend_tax.js paginates the by_country table using
  createPaginator (SAA-577-1), wired to a #divTaxPagination container.
- Each country row gets an expand/collapse chevron toggle with aria-expanded.
- Expanding a row shows per-payment detail when
  D.dividend_tax[year].by_country[code].payments exists, otherwise a
  summary-only fallback message.
"""
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
JS_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "sections" / "dividend_tax.js"
TAX_HTML_PATH = PROJECT_ROOT / "src" / "templates" / "sections" / "tax.html.j2"
CSS_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "styles.css"


def _js() -> str:
    return JS_PATH.read_text(encoding="utf-8")


def _tax_html() -> str:
    return TAX_HTML_PATH.read_text(encoding="utf-8")


def _css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


class TestPaginationWiring(unittest.TestCase):
    """Country breakdown table is paginated using createPaginator."""

    def test_pagination_container_in_dividend_tax_section(self):
        html = _tax_html()
        section_start = html.index('data-role="dividendTaxSection"')
        section = html[section_start:html.index("</section>", section_start)]
        self.assertIn('data-role="divTaxPagination"', section)

    def test_pagination_container_after_country_table(self):
        html = _tax_html()
        table_pos = html.index('data-role="divTaxTable"')
        pag_pos = html.index('data-role="divTaxPagination"')
        self.assertGreater(pag_pos, table_pos)

    def test_creates_paginator_for_country_breakdown(self):
        js = _js()
        self.assertRegex(js, r"createPaginator\(\s*\w+")
        self.assertIn("divTaxPagination", js)

    def test_uses_get_page_for_rendered_rows(self):
        js = _js()
        self.assertRegex(js, r"countryPaginator\.getPage\(\)")

    def test_set_data_called_with_country_entries(self):
        js = _js()
        self.assertRegex(js, r"countryPaginator\.setData\(")

    def test_paginator_render_called(self):
        js = _js()
        self.assertRegex(js, r"countryPaginator\.render\(\)")


class TestExpandableCountryRows(unittest.TestCase):
    """Each country row has an expand/collapse chevron with aria-expanded."""

    def test_chevron_present_in_row_markup(self):
        js = _js()
        self.assertIn("pos-chevron", js)

    def test_toggle_has_aria_expanded_attribute(self):
        js = _js()
        self.assertIn('aria-expanded="false"', js)

    def test_toggle_handler_updates_aria_expanded(self):
        js = _js()
        self.assertRegex(js, r"setAttribute\(\s*['\"]aria-expanded['\"]\s*,\s*['\"]true['\"]\s*\)")
        self.assertRegex(js, r"setAttribute\(\s*['\"]aria-expanded['\"]\s*,\s*['\"]false['\"]\s*\)")

    def test_detail_row_toggles_display(self):
        js = _js()
        self.assertRegex(js, r"detailRow\.style\.display\s*=\s*['\"]none['\"]")
        self.assertRegex(js, r"detailRow\.style\.display\s*=\s*['\"]{2}")


class TestPaymentDetailFallback(unittest.TestCase):
    """Expanding a row shows per-payment detail or a summary-only fallback."""

    def test_checks_for_payments_array(self):
        js = _js()
        self.assertRegex(js, r"Array\.isArray\(\s*payments\s*\)")

    def test_renders_payments_table_when_present(self):
        js = _js()
        self.assertIn("dt-payments-table", js)

    def test_summary_fallback_message_when_payments_missing(self):
        js = _js()
        self.assertIn("isn't available for this country", js)


class TestStyling(unittest.TestCase):
    """Toggle button is reset to look like an inline icon, matching chevron sizing."""

    def test_dt_toggle_style_defined(self):
        css = _css()
        self.assertIn(".dt-toggle", css)


if __name__ == "__main__":
    unittest.main()
