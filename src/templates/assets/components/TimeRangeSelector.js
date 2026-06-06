/**
 * TimeRangeSelector — button group for 1Y, 5Y, All time range selection.
 * Uses aria-pressed for active state.
 *
 * @param {TimeRange} selected - currently selected range ('1Y' | '5Y' | 'ALL')
 * @returns {string} HTML string for the time range button group
 */
function createTimeRangeSelector(selected) {
  var ranges = ['1Y', '5Y', 'ALL'];
  var buttons = ranges.map(function(range) {
    var isPressed = range === selected ? 'true' : 'false';
    var activeClass = range === selected ? ' time-range-btn--active' : '';
    return '<button type="button" class="time-range-btn' + activeClass + '" ' +
      'aria-pressed="' + isPressed + '" data-range="' + range + '">' +
      (range === 'ALL' ? 'All' : range) +
      '</button>';
  }).join('');
  return '<div class="time-range-selector" role="group" aria-label="Chart time range">' +
    buttons + '</div>';
}

/**
 * filterByTimeRange — filters PropertyValueDataPoint[] by time range.
 *
 * @param {Array<{x: string, y: number}>} data - chart data points with x as date string
 * @param {string} range - '1Y', '5Y', or 'ALL'
 * @returns {Array<{x: string, y: number}>} filtered data
 */
function filterByTimeRange(data, range) {
  if (range === 'ALL') return data;
  var now = new Date();
  var years = range === '1Y' ? 1 : 5;
  var cutoff = new Date(now.getFullYear() - years, now.getMonth(), now.getDate());
  return data.filter(function(point) {
    return new Date(point.x) >= cutoff;
  });
}
