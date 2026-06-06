/**
 * RealEstateEmptyState — renders an empty state when no properties exist.
 *
 * @param {string} addPropertyUrl - URL to the property management page (e.g. /properties/new)
 * @returns {string} HTML string for the empty state UI
 */
function createRealEstateEmptyState(addPropertyUrl) {
  var url = addPropertyUrl || '/properties/new';
  return '<div class="empty-state-card">' +
    '<div class="empty-state-icon">🏠</div>' +
    '<h3 class="empty-state-title">No properties yet</h3>' +
    '<p class="empty-state-message">Add your first property to track its value, gains, and portfolio contribution.</p>' +
    '<div class="empty-state-actions">' +
    '<a href="' + url + '" class="btn btn-primary re-add-property-cta">Add Property</a>' +
    '</div>' +
    '</div>';
}
