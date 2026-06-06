// Tax Advanced sub-tab: accordion single-expand behavior
(function () {
  var container = document.querySelector('[data-role="taxAdvancedContainer"]');
  if (!container) return;

  var headers = container.querySelectorAll('[data-accordion-toggle]');

  headers.forEach(function (btn) {
    btn.addEventListener('click', function () {
      var targetId = btn.getAttribute('data-accordion-toggle');
      var targetContent = container.querySelector('[data-accordion-content="' + targetId + '"]');
      var isExpanded = btn.getAttribute('aria-expanded') === 'true';

      // Collapse all accordion sections
      headers.forEach(function (h) {
        h.setAttribute('aria-expanded', 'false');
        var contentId = h.getAttribute('data-accordion-toggle');
        var content = container.querySelector('[data-accordion-content="' + contentId + '"]');
        if (content) {
          content.classList.remove('expanded');
          content.style.maxHeight = '0';
        }
      });

      // Expand the clicked section if it was collapsed
      if (!isExpanded && targetContent) {
        btn.setAttribute('aria-expanded', 'true');
        targetContent.classList.add('expanded');
        targetContent.style.maxHeight = targetContent.scrollHeight + 'px';
      }
    });
  });

  // Initialise max-height for the default-expanded (timeline) section
  var expandedContent = container.querySelector('.tax-accordion-content.expanded');
  if (expandedContent) {
    expandedContent.style.maxHeight = expandedContent.scrollHeight + 'px';
  }
})();
