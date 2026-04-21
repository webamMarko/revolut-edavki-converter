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
  const savedPage = localStorage.getItem('activePage');
  let currentPage = (savedPage && document.getElementById('page-' + savedPage)) ? savedPage : 'overview';

  // Apply saved page on load (the HTML has 'overview' active by default)
  if (currentPage !== 'overview') {
    document.getElementById('page-overview').style.display = 'none';
    document.getElementById('page-overview').classList.remove('active');
    const initPage = document.getElementById('page-' + currentPage);
    if (initPage) { initPage.style.display = 'block'; initPage.classList.add('active'); }
    navItems.forEach(function(i) { i.classList.toggle('active', i.dataset.page === currentPage); });
  }

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
      localStorage.setItem('activePage', id);
    }, 110);
  }

  // Wire nav items
  navItems.forEach(function(item) {
    item.addEventListener('click', function() { switchPage(item.dataset.page); });
  });

  // Keyboard: ← → or ↑ ↓ to step through visible nav items, plus page shortcuts
  var _shortcutMap = {
    '1': 'overview', '2': 'charts', '3': 'positions', '4': 'dividends',
    '5': 'notes', '6': 'tax', '7': 'history',
    'o': 'overview', 'c': 'charts', 'p': 'positions', 'd': 'dividends',
    'n': 'notes', 't': 'tax', 'h': 'history',
  };
  document.addEventListener('keydown', function(e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (e.altKey || e.ctrlKey || e.metaKey) return;

    // ? or / to toggle help modal
    if (e.key === '?' || (e.key === '/' && !e.shiftKey)) {
      e.preventDefault();
      _toggleShortcutHelp();
      return;
    }
    // Escape to close help modal
    if (e.key === 'Escape') {
      var modal = document.getElementById('shortcutHelpModal');
      if (modal && modal.style.display !== 'none') { modal.style.display = 'none'; return; }
    }

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
    // Page shortcuts
    var target = _shortcutMap[e.key];
    if (target && document.getElementById('page-' + target)) {
      e.preventDefault();
      switchPage(target);
    }
  });

  // Shortcut help modal
  function _toggleShortcutHelp() {
    var modal = document.getElementById('shortcutHelpModal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'shortcutHelpModal';
      modal.className = 'shortcut-modal-overlay';
      modal.innerHTML = '<div class="shortcut-modal">'
        + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.75rem">'
        + '<h3 style="margin:0">Keyboard Shortcuts</h3>'
        + '<button onclick="document.getElementById(\'shortcutHelpModal\').style.display=\'none\'" style="background:none;border:none;color:var(--muted);cursor:pointer;font-size:1.2rem">&times;</button>'
        + '</div>'
        + '<div class="shortcut-grid">'
        + _shortcutRow('?', 'Toggle this help')
        + _shortcutRow('← →', 'Previous / next page')
        + _shortcutRow('↑ ↓', 'Previous / next page')
        + _shortcutRow('1-7', 'Jump to page by number')
        + _shortcutRow('O', 'Overview')
        + _shortcutRow('C', 'Charts')
        + _shortcutRow('P', 'Positions')
        + _shortcutRow('D', 'Dividends')
        + _shortcutRow('N', 'Notes')
        + _shortcutRow('T', 'Tax')
        + _shortcutRow('H', 'History')
        + _shortcutRow('Esc', 'Close modal')
        + '</div></div>';
      document.body.appendChild(modal);
      modal.addEventListener('click', function(e) {
        if (e.target === modal) modal.style.display = 'none';
      });
    }
    modal.style.display = modal.style.display === 'none' ? '' : 'none';
  }
  function _shortcutRow(key, desc) {
    return '<div class="shortcut-key"><kbd>' + key + '</kbd></div><div class="shortcut-desc">' + desc + '</div>';
  }

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
