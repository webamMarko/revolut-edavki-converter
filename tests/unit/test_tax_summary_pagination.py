"""TDD tests for SAA-577-2 / SAA-634: Tax Summary pagination + expandable ticker rows.

Spec (SAA-577 Task 2):
- renderTax() in tax.js groups realized_sales by ticker into summary rows
  (total gain, total tax, sale count) and paginates them using
  createPaginator (SAA-577-1), wired to a #taxPagination container.
- Each ticker row gets an expand/collapse chevron toggle with aria-expanded
  that reveals individual FIFO sale detail rows below it.
- On year change, taxPaginator.reset() resets to page 1 (page size kept).
- Sortable still works on summary rows, keeping detail rows paired beneath.
"""
import json
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
JS_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "sections" / "tax.js"
TAX_HTML_PATH = PROJECT_ROOT / "src" / "templates" / "sections" / "tax.html.j2"
CSS_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "styles.css"
LOCALES_DIR = PROJECT_ROOT / "src" / "locales"


def _js() -> str:
    return JS_PATH.read_text(encoding="utf-8")


def _tax_html() -> str:
    return TAX_HTML_PATH.read_text(encoding="utf-8")


def _css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


class TestPaginationWiring(unittest.TestCase):
    """Ticker summary table is paginated using createPaginator."""

    def test_pagination_container_in_tax_section(self):
        html = _tax_html()
        section_start = html.index('data-role="taxSection"')
        section = html[section_start:html.index("</section>", section_start)]
        self.assertIn('data-role="taxPagination"', section)

    def test_pagination_container_after_tax_table(self):
        html = _tax_html()
        table_pos = html.index('data-role="taxTable"')
        pag_pos = html.index('data-role="taxPagination"')
        self.assertGreater(pag_pos, table_pos)

    def test_creates_paginator_for_tax_table(self):
        js = _js()
        self.assertRegex(js, r"createPaginator\(\s*\w+")
        self.assertIn("taxPagination", js)

    def test_uses_get_page_for_rendered_rows(self):
        js = _js()
        self.assertRegex(js, r"taxPaginator\.getPage\(\)")

    def test_set_data_called_with_grouped_entries(self):
        js = _js()
        self.assertRegex(js, r"taxPaginator\.setData\(\s*currentTaxGroups\s*\)")

    def test_paginator_render_called(self):
        js = _js()
        self.assertRegex(js, r"taxPaginator\.render\(\)")

    def test_paginator_reset_called(self):
        js = _js()
        self.assertRegex(js, r"taxPaginator\.reset\(\)")


class TestTickerGrouping(unittest.TestCase):
    """realized_sales are grouped by ticker into summary rows."""

    def test_groups_sales_by_ticker(self):
        js = _js()
        self.assertIn("function _groupSalesByTicker(sales)", js)

    def test_group_tracks_sale_count(self):
        js = _js()
        self.assertRegex(js, r"g\.count\+\+")

    def test_group_aggregates_gain_and_tax(self):
        js = _js()
        self.assertIn("g.gain_eur += s.gain_eur", js)
        self.assertIn("g.tax_eur += s.tax_eur", js)

    def test_render_tax_uses_grouped_data(self):
        js = _js()
        self.assertRegex(js, r"currentTaxGroups\s*=\s*_groupSalesByTicker\(sales\)")


class TestExpandableTickerRows(unittest.TestCase):
    """Each ticker row has an expand/collapse chevron with aria-expanded."""

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

    def test_detail_row_collapsed_by_default(self):
        js = _js()
        self.assertRegex(js, r'tax-detail-row["\']\s+id="\$\{detailId\}"\s+style="display:none"')

    def test_renders_individual_sale_detail_table(self):
        js = _js()
        self.assertIn("function _renderTaxSaleDetail(sales)", js)
        self.assertIn("tax-sales-table", js)


class TestSortableSummaryRows(unittest.TestCase):
    """Sorting works on summary rows while keeping detail rows paired beneath."""

    def test_custom_sortable_defined(self):
        js = _js()
        self.assertIn("function _makeTaxSortable(table)", js)

    def test_sortable_pairs_summary_and_detail_rows(self):
        js = _js()
        self.assertIn("tax-summary-row", js)
        self.assertIn("tax-detail-row", js)

    def test_render_tax_table_invokes_sortable(self):
        js = _js()
        self.assertIn("_makeTaxSortable(tt)", js)


class TestI18nKeys(unittest.TestCase):
    """New 'Sales' column header has translations across all locales."""

    def test_sales_column_key_in_all_locales(self):
        for locale_file in LOCALES_DIR.glob("*.json"):
            if locale_file.name == "country_map.json":
                continue
            data = json.loads(locale_file.read_text(encoding="utf-8"))
            self.assertIn("tax.col.sales", data, f"missing tax.col.sales in {locale_file.name}")

    def test_sales_column_used_in_summary_header(self):
        js = _js()
        self.assertIn("t('tax.col.sales')", js)


class TestStyling(unittest.TestCase):
    """Toggle button reuses existing .dt-toggle styling from SAA-577-4."""

    def test_dt_toggle_style_defined(self):
        css = _css()
        self.assertIn(".dt-toggle", css)


if __name__ == "__main__":
    unittest.main()
