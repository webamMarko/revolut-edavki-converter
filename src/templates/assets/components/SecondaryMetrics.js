/**
 * SecondaryMetrics — renders PURCHASE TOTAL and ETN ESTIMATE metric cards.
 * Hidden behind the ShowAllMetricsToggle on first load.
 *
 * @param {number} purchaseTotal - total purchase value in EUR
 * @param {number} etnEstimate - ETN estimated value in EUR
 * @returns {string} HTML string for the two secondary metric cards
 */
function createSecondaryMetrics(purchaseTotal, etnEstimate) {
  return '<div class="metric-card">' +
    '<div class="label">PURCHASE TOTAL</div>' +
    '<div class="value">' + fmtEur(purchaseTotal) + '</div>' +
    '</div>' +
    '<div class="metric-card">' +
    '<div class="label">ETN ESTIMATE</div>' +
    '<div class="value">' + fmtEur(etnEstimate) + '</div>' +
    '</div>';
}
