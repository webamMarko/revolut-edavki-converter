// --- Sidebar navigation ---
(function() {
  const navItems = document.querySelectorAll('.nav-item[data-page]');
  let currentPage = 'overview';

  function getPage(id) { return document.getElementById('page-' + id); }

  function switchPage(id) {
    if (id === currentPage) return;
    const prev = getPage(currentPage);
    const next = getPage(id);
    if (!next) return;

    // Update nav active state
    navItems.forEach(function(i) { i.classList.toggle('active', i.dataset.page === id); });

    // Fade out current, swap, fade in next
    prev.style.opacity = '0';
    prev.style.transition = 'opacity 0.12s ease';

    setTimeout(function() {
      prev.style.display = 'none';
      prev.style.transition = '';
      prev.style.opacity = '';

      next.style.display = 'block';
      next.style.opacity = '0';
      next.style.transition = 'opacity 0.12s ease';
      // Force reflow before starting fade-in
      void next.offsetWidth;
      next.style.opacity = '1';

      setTimeout(function() {
        next.style.transition = '';
      }, 130);

      currentPage = id;
    }, 110);
  }

  // Wire nav items
  navItems.forEach(function(item) {
    item.addEventListener('click', function() { switchPage(item.dataset.page); });
  });

  // Keyboard: ← → or ↑ ↓ to step through visible nav items
  document.addEventListener('keydown', function(e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    const ids = [...navItems]
      .filter(function(i) { return i.style.display !== 'none'; })
      .map(function(i) { return i.dataset.page; });
    const idx = ids.indexOf(currentPage);
    if ((e.key === 'ArrowRight' || e.key === 'ArrowDown') && idx < ids.length - 1) {
      e.preventDefault(); switchPage(ids[idx + 1]);
    }
    if ((e.key === 'ArrowLeft' || e.key === 'ArrowUp') && idx > 0) {
      e.preventDefault(); switchPage(ids[idx - 1]);
    }
  });

  // Show real estate nav item only when data exists
  if (D.real_estate && D.real_estate.properties && D.real_estate.properties.length > 0) {
    var navRE = document.getElementById('navRealestate');
    if (navRE) navRE.style.display = '';
  }

  window.switchPage = switchPage;
})();
