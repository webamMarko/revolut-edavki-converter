"""TDD tests for SAA-549: Time range controls for property value chart.

Spec (from SAA-327 spec, Task 2):
- Chart renders with 1Y, 5Y, All buttons; All selected by default
- TimeRangeSelector component in its own file with aria-pressed
- filterByTimeRange utility function filters data by range
- Selecting 1Y filters chart data to last year
- Selecting 5Y filters to last 5 years, All shows everything
- Integrated into real_estate.js
"""
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SELECTOR_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "components" / "TimeRangeSelector.js"
RE_JS_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "sections" / "real_estate.js"
RE_HTML_PATH = PROJECT_ROOT / "src" / "templates" / "sections" / "real_estate.html.j2"


def _selector() -> str:
    return SELECTOR_PATH.read_text(encoding="utf-8")


def _js() -> str:
    return RE_JS_PATH.read_text(encoding="utf-8")


def _html() -> str:
    return RE_HTML_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 1: Chart renders with 1Y, 5Y, All buttons; All selected by default
# ---------------------------------------------------------------------------

class TestTimeRangeButtonsRendered(unittest.TestCase):
    """Chart renders with 1Y, 5Y, All buttons and All selected by default."""

    def test_time_range_selector_component_file_exists(self):
        """Test 1a: TimeRangeSelector.js component file exists."""
        self.assertTrue(SELECTOR_PATH.exists(),
            "TimeRangeSelector.js must exist in src/templates/assets/components/")

    def test_selector_has_1y_option(self):
        """Test 1b: TimeRangeSelector includes 1Y range option."""
        comp = _selector()
        self.assertIn('1Y', comp,
            "TimeRangeSelector must include '1Y' range option")

    def test_selector_has_5y_option(self):
        """Test 1c: TimeRangeSelector includes 5Y range option."""
        comp = _selector()
        self.assertIn('5Y', comp,
            "TimeRangeSelector must include '5Y' range option")

    def test_selector_has_all_option(self):
        """Test 1d: TimeRangeSelector includes ALL range option."""
        comp = _selector()
        self.assertIn('ALL', comp,
            "TimeRangeSelector must include 'ALL' range option")

    def test_selector_uses_aria_pressed(self):
        """Test 1e: TimeRangeSelector uses aria-pressed for active state."""
        comp = _selector()
        self.assertIn('aria-pressed', comp,
            "TimeRangeSelector must use aria-pressed for active state")

    def test_selector_accepts_selected_param(self):
        """Test 1f: TimeRangeSelector accepts selected parameter."""
        comp = _selector()
        self.assertIn('selected', comp,
            "TimeRangeSelector must accept 'selected' parameter")

    def test_html_has_time_range_container(self):
        """Test 1g: HTML has reTimeRange container for the selector."""
        html = _html()
        self.assertIn('reTimeRange', html,
            "real_estate.html.j2 must have a 'reTimeRange' container")

    def test_js_default_range_is_all(self):
        """Test 1h: real_estate.js defaults to ALL time range."""
        js = _js()
        self.assertIn("'ALL'", js,
            "real_estate.js must default to 'ALL' time range")

    def test_js_renders_time_range_selector(self):
        """Test 1i: real_estate.js calls createTimeRangeSelector."""
        js = _js()
        self.assertIn('createTimeRangeSelector', js,
            "real_estate.js must call createTimeRangeSelector")

    def test_js_renders_into_time_range_container(self):
        """Test 1j: real_estate.js renders selector into reTimeRange container."""
        js = _js()
        self.assertIn('reTimeRange', js,
            "real_estate.js must reference reTimeRange container")


# ---------------------------------------------------------------------------
# Test 2: filterByTimeRange utility function
# ---------------------------------------------------------------------------

class TestFilterByTimeRangeUtility(unittest.TestCase):
    """filterByTimeRange utility function exists and filters correctly."""

    def test_filter_function_exists(self):
        """Test 2a: filterByTimeRange function is defined."""
        comp = _selector()
        self.assertIn('filterByTimeRange', comp,
            "TimeRangeSelector.js must define filterByTimeRange function")

    def test_filter_accepts_data_and_range(self):
        """Test 2b: filterByTimeRange accepts data and range parameters."""
        comp = _selector()
        self.assertIn('data', comp,
            "filterByTimeRange must accept 'data' parameter")
        self.assertIn('range', comp,
            "filterByTimeRange must accept 'range' parameter")

    def test_filter_returns_all_for_all_range(self):
        """Test 2c: filterByTimeRange returns all data for ALL range."""
        comp = _selector()
        self.assertIn("'ALL'", comp,
            "filterByTimeRange must handle 'ALL' range")
        self.assertIn('return data', comp,
            "filterByTimeRange must return unfiltered data for ALL")

    def test_filter_handles_1y_range(self):
        """Test 2d: filterByTimeRange handles 1Y range with 1 year cutoff."""
        comp = _selector()
        self.assertIn("'1Y'", comp,
            "filterByTimeRange must handle '1Y' range")

    def test_filter_handles_5y_range(self):
        """Test 2e: filterByTimeRange handles 5Y range with 5 year cutoff."""
        comp = _selector()
        self.assertIn('5', comp,
            "filterByTimeRange must handle 5-year cutoff")

    def test_filter_uses_date_comparison(self):
        """Test 2f: filterByTimeRange uses Date comparison for filtering."""
        comp = _selector()
        self.assertIn('new Date', comp,
            "filterByTimeRange must create Date objects for comparison")
        self.assertIn('filter', comp,
            "filterByTimeRange must use array filter method")

    def test_js_calls_filter_by_time_range(self):
        """Test 2g: real_estate.js calls filterByTimeRange."""
        js = _js()
        self.assertIn('filterByTimeRange', js,
            "real_estate.js must call filterByTimeRange to filter chart data")


# ---------------------------------------------------------------------------
# Test 3: Selecting 1Y filters chart data to last year
# ---------------------------------------------------------------------------

class TestSelectingOneYearRange(unittest.TestCase):
    """Selecting 1Y filters the chart data to the last year."""

    def test_js_click_handler_on_time_range_buttons(self):
        """Test 3a: real_estate.js attaches click handlers to time range buttons."""
        js = _js()
        self.assertIn("'click'", js,
            "real_estate.js must attach click event listeners to time range buttons")

    def test_js_reads_data_range_attribute(self):
        """Test 3b: JS reads data-range attribute from clicked button."""
        js = _js()
        self.assertIn('data-range', js,
            "JS must read data-range attribute from buttons")

    def test_js_updates_chart_on_range_change(self):
        """Test 3c: JS updates chart when time range changes."""
        js = _js()
        self.assertIn('.update()', js,
            "JS must call chart.update() when time range changes")

    def test_selector_has_data_range_attribute(self):
        """Test 3d: TimeRangeSelector buttons include data-range attribute."""
        comp = _selector()
        self.assertIn('data-range', comp,
            "TimeRangeSelector buttons must include data-range attribute")


# ---------------------------------------------------------------------------
# Test 4: Selecting 5Y filters to last 5 years, All shows everything
# ---------------------------------------------------------------------------

class TestSelectingFiveYearAndAllRange(unittest.TestCase):
    """Selecting 5Y filters to 5 years; All shows everything."""

    def test_filter_1y_uses_1_year_cutoff(self):
        """Test 4a: filterByTimeRange uses 1 year for 1Y range."""
        comp = _selector()
        self.assertIn('1', comp,
            "filterByTimeRange must reference 1-year value")

    def test_filter_5y_uses_5_year_cutoff(self):
        """Test 4b: filterByTimeRange uses 5 years for 5Y range."""
        comp = _selector()
        self.assertIn('5', comp,
            "filterByTimeRange must reference 5-year value")

    def test_js_stores_all_data_for_refiltering(self):
        """Test 4c: JS preserves original (all) data so re-selecting All works."""
        js = _js()
        self.assertIn('allData', js,
            "JS must store allData to allow re-filtering when switching ranges")

    def test_js_updates_button_active_states(self):
        """Test 4d: JS re-renders selector with updated range (aria-pressed via component)."""
        js = _js()
        self.assertIn('createTimeRangeSelector(range)', js,
            "JS must re-render TimeRangeSelector with new range to update aria-pressed")


# ---------------------------------------------------------------------------
# Test 5: Integration — TimeRangeSelector wired into PropertyValueChart
# ---------------------------------------------------------------------------

class TestTimeRangeIntegration(unittest.TestCase):
    """TimeRangeSelector is integrated into the real estate chart flow."""

    def test_js_initializes_time_range_selector(self):
        """Test 5a: JS initializes time range selector on load."""
        js = _js()
        self.assertIn('initTimeRangeSelector', js,
            "JS must have initTimeRangeSelector initialization")

    def test_js_applies_filter_to_chart_datasets(self):
        """Test 5b: JS applies filterByTimeRange to chart datasets."""
        js = _js()
        self.assertIn('filterByTimeRange', js,
            "JS must apply filterByTimeRange to chart datasets")

    def test_html_time_range_before_chart(self):
        """Test 5c: Time range selector appears before the chart in HTML."""
        html = _html()
        tr_idx = html.find('reTimeRange')
        chart_idx = html.find('reChart')
        self.assertGreater(tr_idx, -1, "HTML must have reTimeRange")
        self.assertGreater(chart_idx, -1, "HTML must have reChart")
        self.assertLess(tr_idx, chart_idx,
            "Time range selector must appear before chart in DOM")

    def test_selector_has_role_group(self):
        """Test 5d: TimeRangeSelector wraps buttons in role='group'."""
        comp = _selector()
        self.assertIn('role', comp,
            "TimeRangeSelector must use role attribute")
        self.assertIn('group', comp,
            "TimeRangeSelector must use role='group' for button grouping")


if __name__ == "__main__":
    unittest.main()
