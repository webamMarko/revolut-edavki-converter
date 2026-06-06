/**
 * ShowAllMetricsToggle — text link toggling between 'Show all metrics' and 'Show fewer'.
 * Includes aria-expanded reflecting current state.
 *
 * @param {boolean} expanded - initial expanded state
 * @returns {string} HTML string for the toggle button
 */
function createShowAllMetricsToggle(expanded) {
  var isExpanded = expanded ? 'true' : 'false';
  var label = expanded ? 'Show fewer' : 'Show all metrics';
  return '<button type="button" class="metrics-toggle-link" aria-expanded="' + isExpanded + '">' +
    label +
    '</button>';
}
