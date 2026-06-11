"""TDD tests for SAA-577-3 / SAA-635: Tax-Loss Harvesting pagination + expandable rows.

Spec (SAA-577 Task 3):
- renderHarvest() in tax.js paginates `harvest_candidates` using
  createPaginator (SAA-577-1), wired to a #harvestPagination container.
- Each candidate row gets an expand/collapse chevron toggle with
  aria-expanded, matching the Tax Summary (#taxPagination) row pattern.
- Expanding a row shows lot-level detail when
  D.tax_by_year[year].harvest_candidates[i].lots exists, otherwise a
  summary-only fallback message.
"""
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
JS_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "sections" / "tax.js"
TAX_HTML_PATH = PROJECT_ROOT / "src" / "templates" / "sections" / "tax.html.j2"
CSS_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "styles.css"


def _js() -> str:
    return JS_PATH.read_text(encoding="utf-8")


def _tax_html() -> str:
    return TAX_HTML_PATH.read_text(encoding="utf-8")


def _css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


class TestPaginationWiring(unittest.TestCase):
    """Harvesting table is paginated using createPaginator."""

    def test_pagination_container_in_harvest_section(self):
        html = _tax_html()
        section_start = html.index('data-role="harvestSection"')
        section = html[section_start:html.index("</section>", section_start)]
        self.assertIn('data-role="harvestPagination"', section)

    def test_pagination_container_after_harvest_table(self):
        html = _tax_html()
        table_pos = html.index('data-role="harvestTable"')
        pag_pos = html.index('data-role="harvestPagination"')
        self.assertGreater(pag_pos, table_pos)

    def test_creates_paginator_for_harvest_table(self):
        js = _js()
        self.assertRegex(js, r"createPaginator\(\s*\w+")
        self.assertIn("harvestPagination", js)

    def test_uses_get_page_for_rendered_rows(self):
        js = _js()
        self.assertRegex(js, r"harvestPaginator\.getPage\(\)")

    def test_set_data_called_with_filtered_candidates(self):
        js = _js()
        self.assertRegex(js, r"harvestPaginator\.setData\(")

    def test_paginator_render_called(self):
        js = _js()
        self.assertRegex(js, r"harvestPaginator\.render\(\)")

    def test_paginator_reset_called(self):
        js = _js()
        self.assertRegex(js, r"harvestPaginator\.reset\(\)")


class TestExpandableHarvestRows(unittest.TestCase):
    """Each candidate row has an expand/collapse chevron with aria-expanded."""

    def test_render_harvest_table_function_exists(self):
        js = _js()
        self.assertIn("function renderHarvestTable()", js)

    def test_render_harvest_invokes_render_harvest_table(self):
        js = _js()
        self.assertIn("renderHarvestTable()", js)

    def test_summary_and_detail_row_classes_present(self):
        js = _js()
        self.assertIn("harvest-summary-row", js)
        self.assertIn("harvest-detail-row", js)

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

    def test_harvest_detail_row_collapsed_by_default(self):
        js = _js()
        self.assertRegex(js, r'harvest-detail-row["\']\s+id="\$\{detailId\}"\s+style="display:none"')


class TestLotDetailFallback(unittest.TestCase):
    """Expanding a row shows lot-level detail or a summary-only fallback."""

    def test_renders_lot_detail_function_exists(self):
        js = _js()
        self.assertIn("function _renderHarvestLotDetail(", js)

    def test_checks_for_lots_array(self):
        js = _js()
        self.assertRegex(js, r"Array\.isArray\(\s*(\w+\.)?lots\s*\)")

    def test_renders_lots_table_when_present(self):
        js = _js()
        self.assertIn("harvest-lots-table", js)

    def test_fallback_message_when_lots_missing(self):
        js = _js()
        self.assertIn("isn't available", js)

    def test_lot_table_uses_harvest_lot_fields(self):
        js = _js()
        for field in ["buy_date", "cost_per_share_eur", "current_price_eur", "potential_saving_eur"]:
            self.assertIn(field, js)


class TestPairedSorting(unittest.TestCase):
    """Sorting keeps each candidate's detail row paired beneath it."""

    def test_paired_sortable_helper_defined(self):
        js = _js()
        self.assertIn("function _makePairedSortable(table, summaryClass, detailClass)", js)

    def test_render_harvest_table_invokes_paired_sortable(self):
        js = _js()
        self.assertIn("_makePairedSortable(ht, 'harvest-summary-row', 'harvest-detail-row')", js)

    def test_tax_summary_sortable_still_wired(self):
        js = _js()
        self.assertIn("function _makeTaxSortable(table)", js)
        self.assertIn("_makeTaxSortable(tt)", js)


class TestStyling(unittest.TestCase):
    """Toggle button reuses existing .dt-toggle styling."""

    def test_dt_toggle_style_defined(self):
        css = _css()
        self.assertIn(".dt-toggle", css)


if __name__ == "__main__":
    unittest.main()
