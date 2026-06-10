"""TDD tests for SAA-577-1: Reusable createPaginator utility.

Spec (from SAA-577 spec, Task 1):
- createPaginator(containerEl, opts) factory encapsulating pagination state,
  page slicing, and rendering. Mirrors buildTxPagination() (transactions.js)
  and reuses .pagination CSS (styles.css).
- Interface: { setData(arr), getPage() -> arr, render(), reset(), currentPage, pageSize }
- Configurable page sizes (10/25/50) via inline dropdown
- "Page X of Y (Z total)" indicator
- Prev/next + numbered page buttons
- reset() preserves page size but goes to page 1
- aria-live region for page change announcements
- Keyboard navigable (Tab/Enter/Space) via native <button>/<select> elements
"""
import glob
import json
import shutil
import subprocess
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PAGINATOR_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "components" / "Paginator.js"
REPORT_PATH = PROJECT_ROOT / "src" / "templates" / "report.html.j2"
STYLES_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "styles.css"


def _src() -> str:
    return PAGINATOR_PATH.read_text(encoding="utf-8")


def _report() -> str:
    return REPORT_PATH.read_text(encoding="utf-8")


def _styles() -> str:
    return STYLES_PATH.read_text(encoding="utf-8")


def _find_node():
    node = shutil.which("node")
    if node:
        return node
    candidates = sorted(glob.glob(str(Path.home() / ".nvm" / "versions" / "node" / "*" / "bin" / "node")))
    return candidates[-1] if candidates else None


NODE_BIN = _find_node()


def _run_paginator_script(script: str):
    """Run a JS snippet with createPaginator() in scope; return parsed JSON stdout."""
    full = _src() + "\n" + script
    result = subprocess.run([NODE_BIN, "-e", full], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# Test 1: Factory exists with expected interface, wired into the report
# ---------------------------------------------------------------------------

class TestFactoryInterface(unittest.TestCase):
    """createPaginator(containerEl, opts) returns the documented interface."""

    def test_paginator_file_exists(self):
        """Test 1a: Paginator.js component file exists."""
        self.assertTrue(PAGINATOR_PATH.exists(),
            "Paginator.js must exist in src/templates/assets/components/")

    def test_defines_create_paginator_factory(self):
        """Test 1b: createPaginator(containerEl, opts) factory is defined."""
        src = _src()
        self.assertIn('function createPaginator(containerEl, opts)', src,
            "Paginator.js must define createPaginator(containerEl, opts)")

    def test_returns_expected_interface_members(self):
        """Test 1c: returned object exposes setData, getPage, render, reset, currentPage, pageSize."""
        src = _src()
        for member in ['setData', 'getPage', 'render', 'reset', 'currentPage', 'pageSize']:
            self.assertIn(member, src,
                f"Paginator interface must expose '{member}'")

    def test_included_in_report_template(self):
        """Test 1d: report.html.j2 includes the Paginator component."""
        report = _report()
        self.assertIn('components/Paginator.js', report,
            "report.html.j2 must include assets/components/Paginator.js")

    def test_reuses_pagination_css_class(self):
        """Test 1e: render() applies the existing .pagination class to its container."""
        src = _src()
        self.assertIn("classList.add('pagination')", src,
            "Paginator must reuse the existing .pagination CSS class on its container")


# ---------------------------------------------------------------------------
# Test 2: Page size dropdown (10/25/50)
# ---------------------------------------------------------------------------

class TestPageSizeDropdown(unittest.TestCase):
    """Configurable page sizes (10/25/50) via inline dropdown."""

    def test_default_page_sizes_10_25_50(self):
        """Test 2a: default page sizes are [10, 25, 50]."""
        src = _src()
        self.assertIn('[10, 25, 50]', src,
            "Paginator must default pageSizes to [10, 25, 50]")

    def test_renders_inline_size_select(self):
        """Test 2b: pagination controls include an inline page-size <select>."""
        src = _src()
        self.assertIn('<select', src,
            "Paginator must render a <select> for page size")
        self.assertIn('pagination-size', src,
            "Page-size control must use the pagination-size class")

    def test_size_change_handler_resets_to_page_1(self):
        """Test 2c: changing page size calls reset() before re-rendering."""
        src = _src()
        idx = src.index("sizeSelect.addEventListener('change'")
        snippet = src[idx:idx + 400]
        self.assertIn('reset()', snippet,
            "Page-size change handler must call reset() to return to page 1")
        self.assertIn('render()', snippet,
            "Page-size change handler must re-render after resetting")


# ---------------------------------------------------------------------------
# Test 3: "Page X of Y (Z total)" indicator with aria-live
# ---------------------------------------------------------------------------

class TestPageIndicator(unittest.TestCase):
    """'Page X of Y (Z total)' indicator announced via aria-live."""

    def test_aria_live_region_present(self):
        """Test 3a: page indicator is an aria-live region."""
        src = _src()
        self.assertIn('aria-live="polite"', src,
            "Paginator must include an aria-live region for page change announcements")

    def test_page_indicator_format(self):
        """Test 3b: indicator text follows 'Page X of Y (Z total)'."""
        src = _src()
        self.assertIn(">Page '", src)
        self.assertIn("' of '", src)
        self.assertIn("' total)</span>'", src)


# ---------------------------------------------------------------------------
# Test 4: Prev/next + numbered page buttons, keyboard navigable
# ---------------------------------------------------------------------------

class TestNavigationControls(unittest.TestCase):
    """Prev/next and numbered page buttons, all keyboard navigable."""

    def test_prev_next_buttons(self):
        """Test 4a: prev/next buttons are rendered."""
        src = _src()
        self.assertIn('pagination-prev', src)
        self.assertIn('pagination-next', src)

    def test_numbered_page_buttons(self):
        """Test 4b: numbered page buttons reuse the windowed-pagination pattern."""
        src = _src()
        self.assertIn('pagination-page', src)
        self.assertIn('data-page', src)
        self.assertIn('pagination-ellipsis', src,
            "Paginator must reuse the pagination-ellipsis pattern for skipped pages")

    def test_uses_native_interactive_elements(self):
        """Test 4c: controls use native <button>/<select>, not div+onclick, for Tab/Enter/Space support."""
        src = _src()
        self.assertNotIn('<div onclick', src)
        self.assertIn('<button type="button"', src)
        self.assertIn('<select', src)


# ---------------------------------------------------------------------------
# Test 5: CSS support for new pagination controls
# ---------------------------------------------------------------------------

class TestPaginationStyles(unittest.TestCase):
    """styles.css provides styling for the new size dropdown and indicator."""

    def test_pagination_size_styled(self):
        styles = _styles()
        self.assertIn('.pagination-size', styles)

    def test_pagination_info_styled(self):
        styles = _styles()
        self.assertIn('.pagination-info', styles)


# ---------------------------------------------------------------------------
# Test 6: Behavioral — slicing, reset, clamping (requires Node.js)
# ---------------------------------------------------------------------------

@unittest.skipUnless(NODE_BIN, "Node.js not available")
class TestPaginatorBehavior(unittest.TestCase):
    """Headless behavioral checks (containerEl=null) of the data API."""

    def test_slices_first_page(self):
        """Test 6a: getPage() returns the first pageSize items."""
        out = _run_paginator_script("""
            const p = createPaginator(null, { pageSize: 10 });
            p.setData(Array.from({length: 25}, (_, i) => i));
            console.log(JSON.stringify(p.getPage()));
        """)
        self.assertEqual(out, list(range(10)))

    def test_slices_last_partial_page(self):
        """Test 6b: getPage() returns a partial final page."""
        out = _run_paginator_script("""
            const p = createPaginator(null, { pageSize: 10 });
            p.setData(Array.from({length: 25}, (_, i) => i));
            p.currentPage = 2;
            console.log(JSON.stringify(p.getPage()));
        """)
        self.assertEqual(out, [20, 21, 22, 23, 24])

    def test_page_size_50_fits_in_one_page(self):
        """Test 6c: pageSize=50 with 25 items fits on a single page."""
        out = _run_paginator_script("""
            const p = createPaginator(null, { pageSize: 50 });
            p.setData(Array.from({length: 25}, (_, i) => i));
            console.log(JSON.stringify({ page: p.getPage(), currentPage: p.currentPage }));
        """)
        self.assertEqual(out['page'], list(range(25)))
        self.assertEqual(out['currentPage'], 0)

    def test_reset_preserves_page_size_returns_to_page_1(self):
        """Test 6d: reset() sets currentPage back to 0 without touching pageSize."""
        out = _run_paginator_script("""
            const p = createPaginator(null, { pageSize: 25 });
            p.setData(Array.from({length: 100}, (_, i) => i));
            p.currentPage = 3;
            p.reset();
            console.log(JSON.stringify({ currentPage: p.currentPage, pageSize: p.pageSize }));
        """)
        self.assertEqual(out, {'currentPage': 0, 'pageSize': 25})

    def test_set_data_clamps_current_page_when_data_shrinks(self):
        """Test 6e: setData() clamps currentPage if it now exceeds the new total pages."""
        out = _run_paginator_script("""
            const p = createPaginator(null, { pageSize: 10 });
            p.setData(Array.from({length: 50}, (_, i) => i));
            p.currentPage = 4;
            p.setData(Array.from({length: 12}, (_, i) => i));
            console.log(JSON.stringify({ currentPage: p.currentPage, page: p.getPage() }));
        """)
        self.assertEqual(out['currentPage'], 1)
        self.assertEqual(out['page'], [10, 11])


if __name__ == "__main__":
    unittest.main()
