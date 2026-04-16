// --- Theme toggle ---
(function() {
  function syncIcons() {
    var isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    var icon = isDark ? '☀️' : '🌙';
    var d = document.getElementById('themeIconDesktop');
    var m = document.getElementById('themeIconMobile');
    if (d) d.textContent = icon;
    if (m) m.textContent = icon;
  }
  window.toggleTheme = function() {
    var current = document.documentElement.getAttribute('data-theme');
    var next = current === 'light' ? 'dark' : 'light';
    if (next === 'dark') {
      document.documentElement.removeAttribute('data-theme');
      localStorage.removeItem('theme');
    } else {
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('theme', next);
    }
    syncIcons();
  };
  syncIcons();
})();

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

  // Touch swipe: left/right to navigate between pages.
  // Requires the gesture to be clearly horizontal: |dx| > 70px AND |dx| > 3*|dy|
  // (angle within ~18° of horizontal). This prevents vertical scrolls from
  // accidentally triggering a page switch regardless of speed.
  (function() {
    var content = document.querySelector('.content');
    if (!content) return;
    var touchStartX = 0, touchStartY = 0, touchStartTime = 0;

    content.addEventListener('touchstart', function(e) {
      touchStartX = e.touches[0].clientX;
      touchStartY = e.touches[0].clientY;
      touchStartTime = Date.now();
    }, { passive: true });

    content.addEventListener('touchend', function(e) {
      // Ignore slow gestures — a swipe must complete within 300ms
      if (Date.now() - touchStartTime > 300) return;
      var dx = e.changedTouches[0].clientX - touchStartX;
      var dy = e.changedTouches[0].clientY - touchStartY;
      var adx = Math.abs(dx), ady = Math.abs(dy);
      // Must travel at least 70px horizontally AND be 3× more horizontal than vertical
      if (adx < 70 || adx < ady * 3) return;

      var ids = [...navItems]
        .filter(function(i) { return i.style.display !== 'none'; })
        .map(function(i) { return i.dataset.page; });
      var idx = ids.indexOf(currentPage);

      if (dx < 0 && idx < ids.length - 1) switchPage(ids[idx + 1]); // swipe left → next
      if (dx > 0 && idx > 0)              switchPage(ids[idx - 1]); // swipe right → prev
    }, { passive: true });
  })();

  window.switchPage = switchPage;
})();
