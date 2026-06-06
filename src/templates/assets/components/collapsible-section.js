function initCollapsibleSection(sectionId, persistenceKey) {
  var section = document.getElementById(sectionId);
  if (!section) return;

  var hdr = document.getElementById(sectionId + '-hdr');
  var body = document.getElementById(sectionId + '-body');
  if (!hdr || !body) return;

  if (persistenceKey) {
    var storedState = window._layoutGetSectionState
      ? window._layoutGetSectionState(persistenceKey)
      : (function() { var v = localStorage.getItem(persistenceKey); return v === 'open' ? true : v === 'closed' ? false : null; })();
    if (storedState === true && !body.classList.contains('is-open')) {
      body.classList.add('is-open');
      hdr.setAttribute('aria-expanded', 'true');
    } else if (storedState === false && body.classList.contains('is-open')) {
      body.classList.remove('is-open');
      hdr.setAttribute('aria-expanded', 'false');
    }
  }

  function toggle() {
    var isOpen = body.classList.toggle('is-open');
    hdr.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    if (persistenceKey) {
      if (window._layoutSetSectionState) {
        window._layoutSetSectionState(persistenceKey, isOpen);
      } else {
        localStorage.setItem(persistenceKey, isOpen ? 'open' : 'closed');
      }
    }
    if (isOpen) {
      section.dispatchEvent(new CustomEvent('section-expanded', { bubbles: true, detail: { sectionId: sectionId } }));
    }
  }

  hdr.addEventListener('click', toggle);
  hdr.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      toggle();
    }
  });
}
