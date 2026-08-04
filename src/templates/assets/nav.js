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

  var switchPage = function(id) {
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
      prev.classList.remove('active');
      prev.style.transition = '';
      prev.style.opacity = '';

      next.style.display = 'block';
      next.classList.add('active');
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
      if (window.notifyBadgeClear) window.notifyBadgeClear(id);

      // Re-render the newly active page. scopedFind(null) now resolves elements
      // in the active page container, so section JS correctly binds charts/tables
      // to the visible page rather than the hidden #widgetTemplates pool.
      if (typeof updateAll === 'function') {
        requestAnimationFrame(function() { updateAll(); });
      }
    }, 110);
  }

  // Wire nav items
  navItems.forEach(function(item) {
    item.addEventListener('click', function() { if (item.dataset.href) { window.location.href = item.dataset.href; return; } switchPage(item.dataset.page); });
    item.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); item.click(); }
    });
  });

  // Keyboard: ← → or ↑ ↓ to step through visible nav items, plus page shortcuts
  var _shortcutMap = {
    '1': 'overview', '2': 'charts', '3': 'positions', '4': 'dividends',
    '5': 'projections', '6': 'notes', '7': 'tax', '8': 'history',
    'o': 'overview', 'c': 'charts', 'p': 'positions', 'd': 'dividends',
    'j': 'projections', 'n': 'notes', 't': 'tax', 'h': 'history',
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
        + _shortcutRow('1-8', 'Jump to page by number')
        + _shortcutRow('O', 'Overview')
        + _shortcutRow('C', 'Performance')
        + _shortcutRow('P', 'Positions')
        + _shortcutRow('D', 'Dividends')
        + _shortcutRow('J', 'Projections')
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

  // Show real estate nav item for premium/admin users regardless of property count
  if (D.user && D.user.role && ['premium', 'admin', 'cofounder'].includes(D.user.role)) {
    var navRE = document.getElementById('navRealestate');
    if (navRE) navRE.style.display = '';
  }

  // Show projections nav item when Monte Carlo, FIRE, or dividend data exists
  if ((D.summary && (D.summary.cagr_pct != null || D.summary.portfolio_value_eur != null)) || D.fire != null || (D.dividends && D.dividends.by_month && D.dividends.by_month.length > 0)) {
    var navProj = document.getElementById('navProjections');
    if (navProj) navProj.style.display = '';
  }

  // --- Mobile "More" bottom sheet ---
  var PRIMARY_PAGES = ['overview', 'charts', 'positions', 'tax'];
  // Promote Risk to primary mobile nav when portfolio has 5+ positions
  if (D.positions && D.positions.length >= 5) {
    PRIMARY_PAGES.push('risk');
  }
  var moreBtn = document.getElementById('navMoreBtn');
  var moreSheet = document.getElementById('moreSheet');
  var moreBackdrop = document.getElementById('moreSheetBackdrop');
  var moreList = document.getElementById('moreSheetList');

  function isMobile() { return window.innerWidth <= 768; }

  function applyMobileHidden() {
    navItems.forEach(function(item) {
      var page = item.dataset.page;
      if (!page) return;
      if (PRIMARY_PAGES.indexOf(page) === -1) {
        item.classList.add('mobile-hidden');
      } else {
        item.classList.remove('mobile-hidden');
      }
    });
  }

  function getSecondaryItems() {
    return [...navItems].filter(function(item) {
      return item.dataset.page &&
             PRIMARY_PAGES.indexOf(item.dataset.page) === -1 &&
             item.style.display !== 'none' &&
             !item.classList.contains('nav-more-btn');
    });
  }

  function populateSheet() {
    if (!moreList) return;
    moreList.innerHTML = '';
    getSecondaryItems().forEach(function(item) {
      var div = document.createElement('div');
      div.className = 'more-sheet-item';
      if (item.dataset.page === currentPage) div.classList.add('sheet-active');
      div.innerHTML = item.querySelector('svg').outerHTML + '<span>' + item.querySelector('span').textContent + '</span>';
      div.addEventListener('click', function() {
        switchPage(item.dataset.page);
        closeMoreSheet();
      });
      moreList.appendChild(div);
    });
  }

  function openMoreSheet() {
    if (!moreSheet || !moreBackdrop) return;
    populateSheet();
    moreBackdrop.classList.add('visible');
    // Force reflow before adding open class for transition
    void moreSheet.offsetWidth;
    moreSheet.classList.add('open');
  }

  function closeMoreSheet() {
    if (!moreSheet || !moreBackdrop) return;
    moreSheet.classList.remove('open');
    setTimeout(function() { moreBackdrop.classList.remove('visible'); }, 250);
  }

  if (moreBtn) {
    moreBtn.addEventListener('click', function() {
      if (moreSheet && moreSheet.classList.contains('open')) {
        closeMoreSheet();
      } else {
        openMoreSheet();
      }
    });
  }
  if (moreBackdrop) {
    moreBackdrop.addEventListener('click', closeMoreSheet);
  }

  // Swipe-down to dismiss sheet
  (function() {
    if (!moreSheet) return;
    var sheetTouchStartY = 0;
    moreSheet.addEventListener('touchstart', function(e) {
      sheetTouchStartY = e.touches[0].clientY;
    }, { passive: true });
    moreSheet.addEventListener('touchend', function(e) {
      var dy = e.changedTouches[0].clientY - sheetTouchStartY;
      if (dy > 60) closeMoreSheet();
    }, { passive: true });
  })();

  // Highlight "More" button when a secondary page is active
  function updateMoreBtnActive() {
    if (!moreBtn) return;
    var secondaryPages = getSecondaryItems().map(function(i) { return i.dataset.page; });
    if (secondaryPages.indexOf(currentPage) !== -1) {
      moreBtn.classList.add('active');
    } else {
      moreBtn.classList.remove('active');
    }
  }

  // Patch switchPage to update More button state
  var _origSwitchPage = switchPage;
  switchPage = function(id) {
    _origSwitchPage(id);
    setTimeout(updateMoreBtnActive, 130);
  };

  // Apply mobile classes on load
  applyMobileHidden();
  updateMoreBtnActive();
  window.addEventListener('resize', function() {
    applyMobileHidden();
    updateMoreBtnActive();
  });

  // Close sheet on Escape
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && moreSheet && moreSheet.classList.contains('open')) {
      closeMoreSheet();
    }
  });

  // Touch swipe: left/right to navigate between pages.
  // On mobile, only cycles through primary pages + "more" secondary page if active.
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
      if (Date.now() - touchStartTime > 300) return;
      var dx = e.changedTouches[0].clientX - touchStartX;
      var dy = e.changedTouches[0].clientY - touchStartY;
      var adx = Math.abs(dx), ady = Math.abs(dy);
      if (adx < 70 || adx < ady * 3) return;

      var ids;
      if (isMobile()) {
        ids = PRIMARY_PAGES.filter(function(p) {
          return document.getElementById('page-' + p);
        });
      } else {
        ids = [...navItems]
          .filter(function(i) { return i.style.display !== 'none'; })
          .map(function(i) { return i.dataset.page; });
      }
      var idx = ids.indexOf(currentPage);

      if (dx < 0 && idx < ids.length - 1) switchPage(ids[idx + 1]);
      if (dx > 0 && idx > 0)              switchPage(ids[idx - 1]);
    }, { passive: true });
  })();

  window.switchPage = switchPage;
})();

// --- Tax sub-tab switching ---
(function() {
  var tabs = document.querySelectorAll('#taxSubtabs .tax-subtab');
  var panels = document.querySelectorAll('.tax-subtab-content[data-subtab-panel]');
  if (!tabs.length) return;

  // Remap legacy sub-tab values that no longer exist as top-level tabs
  var _legacyRemap = { 'calendar': 'advanced', 'smart-sell': 'advanced', 'file': 'advanced' };

  function switchTaxSubtab(id, silent) {
    var resolved = _legacyRemap[id] || id;
    if (!document.querySelector('[data-subtab-panel="' + resolved + '"]')) resolved = 'summary';
    tabs.forEach(function(t) { t.classList.toggle('active', t.dataset.subtab === resolved); });
    panels.forEach(function(p) { p.style.display = p.dataset.subtabPanel === resolved ? '' : 'none'; });
    if (!silent) localStorage.setItem('taxSubtab', resolved);
  }

  var saved = localStorage.getItem('taxSubtab');
  if (saved) {
    switchTaxSubtab(saved, true);
  }

  tabs.forEach(function(t) {
    t.addEventListener('click', function() { switchTaxSubtab(t.dataset.subtab); });
  });

  window.switchTaxSubtab = switchTaxSubtab;
})();

// --- Performance detail panel toggle ---
document.addEventListener('click', function(e) {
  var btn = e.target.closest('#perfDetailToggle');
  if (!btn) return;
  var stack = btn.closest('.page-stack');
  var panel = stack && stack.querySelector('#perfDetailPanel');
  if (!panel) return;
  var expanded = btn.getAttribute('aria-expanded') === 'true';
  panel.style.display = expanded ? 'none' : '';
  btn.setAttribute('aria-expanded', expanded ? 'false' : 'true');
});
