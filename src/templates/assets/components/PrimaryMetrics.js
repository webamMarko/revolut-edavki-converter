/**
 * PrimaryMetrics — renders PROPERTIES count and UNREALIZED GAIN % metric cards.
 *
 * @param {number} propertyCount
 * @param {number} unrealizedGainPct
 * @returns {string} HTML string for the two primary metric cards
 */
function createPrimaryMetrics(propertyCount, unrealizedGainPct) {
  var gainCls = cls(unrealizedGainPct);
  var gainStr = sign(unrealizedGainPct) + '%';
  return '<div class="metric-card">' +
    '<div class="label">PROPERTIES</div>' +
    '<div class="value">' + propertyCount + '</div>' +
    '</div>' +
    '<div class="metric-card">' +
    '<div class="label">UNREALIZED GAIN %</div>' +
    '<div class="value ' + gainCls + '">' + gainStr + '</div>' +
    '</div>';
}
