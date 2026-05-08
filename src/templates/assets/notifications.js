// --- Smart Notification Badges ---
(function() {
  var STORAGE_PREFIX = 'notify_';
  var FIRST_VISIT_KEY = STORAGE_PREFIX + 'initialized';
  var TOAST_DISMISSED_KEY = STORAGE_PREFIX + 'toast_dismissed_at';

  // Check if this is the very first visit (no baseline yet)
  var isFirstVisit = !localStorage.getItem(FIRST_VISIT_KEY);

  function getLastVisited(page) {
    var raw = localStorage.getItem(STORAGE_PREFIX + 'visited_' + page);
    return raw ? parseInt(raw, 10) : 0;
  }

  function setLastVisited(page) {
    localStorage.setItem(STORAGE_PREFIX + 'visited_' + page, Date.now().toString());
  }

  function getSnapshot(page) {
    var raw = localStorage.getItem(STORAGE_PREFIX + 'snap_' + page);
    if (!raw) return null;
    try { return JSON.parse(raw); } catch(e) { return null; }
  }

  function setSnapshot(page, data) {
    localStorage.setItem(STORAGE_PREFIX + 'snap_' + page, JSON.stringify(data));
  }

  // --- Detection functions ---
  // Each returns an array of notification strings (empty = no notifications)

  function detectDividendChanges() {
    var items = [];
    var div = D.dividends;
    if (!div || !div.by_month || div.by_month.length === 0) return items;

    var snap = getSnapshot('dividends');
    var currentMonths = div.by_month.length;
    var currentTotal = Math.round(div.total_eur * 100);

    if (snap) {
      var newMonths = currentMonths - (snap.monthCount || 0);
      if (newMonths > 0) {
        items.push(newMonths + ' new dividend month' + (newMonths > 1 ? 's' : ''));
      } else if (currentTotal > (snap.totalCents || 0)) {
        items.push('Dividend income increased');
      }
    }
    return items;
  }

  function detectTaxBracketProximity() {
    var items = [];
    var positions = D.positions || [];
    var lots = D.position_lots || {};
    var regime = D.regime || {};

    if (!positions.length) return items;

    var today = new Date();
    var MS_PER_DAY = 1000 * 60 * 60 * 24;

    function getBrackets(ac) {
      if (ac === 'cfd') return regime.cfd_brackets || [];
      if (ac === 'crypto') return regime.crypto_brackets || [];
      if (ac === 'savings') return regime.savings_brackets || [];
      return regime.stock_brackets || [];
    }

    function getAssetClass(ticker) {
      if (ticker.startsWith('CFD:')) return 'cfd';
      if (ticker.startsWith('CRYPTO:')) return 'crypto';
      if (ticker.startsWith('SAVINGS:')) return 'savings';
      return 'stock';
    }

    var count = 0;
    for (var pi = 0; pi < positions.length; pi++) {
      var pos = positions[pi];
      if (pos.quantity <= 0) continue;
      var ac = getAssetClass(pos.ticker);
      var brackets = getBrackets(ac);
      if (!brackets || brackets.length <= 1) continue;
      var posLots = lots[pos.ticker] || [];

      for (var li = 0; li < posLots.length; li++) {
        var lot = posLots[li];
        var holdingDays = Math.floor((today - new Date(lot.date)) / MS_PER_DAY);
        var holdingYears = holdingDays / 365.25;

        for (var bi = 0; bi < brackets.length; bi++) {
          if (brackets[bi].min_years > holdingYears) {
            var daysToNext = Math.ceil(brackets[bi].min_years * 365.25 - holdingDays);
            if (daysToNext > 0 && daysToNext <= 30) {
              count++;
            }
            break;
          }
        }
      }
    }
    if (count > 0) {
      items.push(count + ' lot' + (count > 1 ? 's' : '') + ' near tax bracket change');
    }
    return items;
  }

  function detectOverviewChanges() {
    var items = [];
    if (!D.summary) return items;

    var snap = getSnapshot('overview');
    if (!snap) return items;

    // ATH detection: current value is the highest ever
    var values = D.value_eur || [];
    if (values.length > 1) {
      var lastVal = values[values.length - 1];
      var prevMax = 0;
      for (var i = 0; i < values.length - 1; i++) {
        if (values[i] > prevMax) prevMax = values[i];
      }
      if (lastVal > prevMax && !snap.wasAtATH) {
        items.push('Portfolio reached all-time high');
      }
    }

    // Milestone threshold crossings
    var currentValue = D.summary.portfolio_value_eur || 0;
    var thresholds = [1000, 5000, 10000, 25000, 50000, 100000, 250000, 500000, 1000000];
    var prevValue = snap.portfolioValue || 0;
    for (var ti = 0; ti < thresholds.length; ti++) {
      if (currentValue >= thresholds[ti] && prevValue < thresholds[ti]) {
        var label = thresholds[ti] >= 1000000 ? (thresholds[ti] / 1000000) + 'M' : (thresholds[ti] / 1000) + 'K';
        items.push('Crossed ' + label + ' milestone');
        break;
      }
    }

    return items;
  }

  function detectPositionChanges() {
    var items = [];
    var positions = D.positions || [];
    if (!positions.length) return items;

    var snap = getSnapshot('positions');
    if (!snap) return items;

    // New positions
    var currentTickers = positions.filter(function(p) { return p.quantity > 0; }).map(function(p) { return p.ticker; });
    var prevTickers = snap.tickers || [];
    var newOnes = currentTickers.filter(function(t) { return prevTickers.indexOf(t) === -1; });
    if (newOnes.length > 0) {
      items.push(newOnes.length + ' new position' + (newOnes.length > 1 ? 's' : ''));
    }

    // Significant gain milestones (any position crossing +50%, +100%, or going negative)
    var significantCount = 0;
    var prevGains = snap.gains || {};
    for (var i = 0; i < positions.length; i++) {
      var p = positions[i];
      if (p.quantity <= 0) continue;
      var prevPct = prevGains[p.ticker] || 0;
      var curPct = p.unrealized_gain_pct || 0;
      var milestones = [-20, 50, 100, 200];
      for (var m = 0; m < milestones.length; m++) {
        var ml = milestones[m];
        if (ml > 0 && curPct >= ml && prevPct < ml) { significantCount++; break; }
        if (ml < 0 && curPct <= ml && prevPct > ml) { significantCount++; break; }
      }
    }
    if (significantCount > 0) {
      items.push(significantCount + ' position' + (significantCount > 1 ? 's' : '') + ' hit gain milestone');
    }

    return items;
  }

  // --- Map pages to their detection functions ---
  var pageDetectors = {
    overview: detectOverviewChanges,
    dividends: detectDividendChanges,
    tax: detectTaxBracketProximity,
    positions: detectPositionChanges
  };

  // --- Compute current snapshots for future comparison ---
  function computeSnapshot(page) {
    if (page === 'overview') {
      var values = D.value_eur || [];
      var lastVal = values.length > 0 ? values[values.length - 1] : 0;
      var prevMax = 0;
      for (var i = 0; i < values.length - 1; i++) {
        if (values[i] > prevMax) prevMax = values[i];
      }
      return {
        portfolioValue: D.summary ? D.summary.portfolio_value_eur : 0,
        wasAtATH: lastVal >= prevMax && values.length > 1
      };
    }
    if (page === 'dividends') {
      var div = D.dividends;
      return {
        monthCount: div && div.by_month ? div.by_month.length : 0,
        totalCents: div ? Math.round((div.total_eur || 0) * 100) : 0
      };
    }
    if (page === 'positions') {
      var positions = D.positions || [];
      var tickers = positions.filter(function(p) { return p.quantity > 0; }).map(function(p) { return p.ticker; });
      var gains = {};
      for (var i = 0; i < positions.length; i++) {
        if (positions[i].quantity > 0) gains[positions[i].ticker] = positions[i].unrealized_gain_pct || 0;
      }
      return { tickers: tickers, gains: gains };
    }
    return null;
  }

  // --- Badge rendering ---
  function renderBadge(navItem, count) {
    var existing = navItem.querySelector('.nav-badge');
    if (count <= 0) {
      if (existing) existing.remove();
      return;
    }
    if (!existing) {
      existing = document.createElement('span');
      existing.className = 'nav-badge';
      navItem.appendChild(existing);
    }
    existing.textContent = count;
    existing.classList.add('nav-badge-enter');
    setTimeout(function() { existing.classList.remove('nav-badge-enter'); }, 400);
  }

  function clearBadge(page) {
    var navItem = document.querySelector('.nav-item[data-page="' + page + '"]');
    if (navItem) {
      var badge = navItem.querySelector('.nav-badge');
      if (badge) badge.remove();
    }
  }

  // --- Toast notification ---
  function showToast(notifications) {
    var total = 0;
    for (var page in notifications) {
      total += notifications[page].length;
    }
    if (total === 0) return;

    var toast = document.createElement('div');
    toast.className = 'notify-toast';
    toast.innerHTML = '<div class="notify-toast-content">'
      + '<span class="notify-toast-icon">&#x1F514;</span>'
      + '<span class="notify-toast-text">' + total + ' update' + (total > 1 ? 's' : '') + ' since your last visit</span>'
      + '<button class="notify-toast-close" aria-label="Dismiss">&times;</button>'
      + '</div>';

    document.body.appendChild(toast);

    // Animate in
    requestAnimationFrame(function() {
      toast.classList.add('notify-toast-visible');
    });

    // Dismiss handlers
    var dismiss = function() {
      toast.classList.remove('notify-toast-visible');
      toast.classList.add('notify-toast-exit');
      setTimeout(function() { toast.remove(); }, 300);
      localStorage.setItem(TOAST_DISMISSED_KEY, Date.now().toString());
    };

    toast.querySelector('.notify-toast-close').addEventListener('click', dismiss);

    // Auto-dismiss after 6 seconds
    setTimeout(dismiss, 6000);
  }

  // --- Main initialization ---
  function init() {
    if (isFirstVisit) {
      // First visit: set baseline snapshots, mark initialized, no badges
      localStorage.setItem(FIRST_VISIT_KEY, Date.now().toString());
      var pages = ['overview', 'dividends', 'positions'];
      for (var i = 0; i < pages.length; i++) {
        var snap = computeSnapshot(pages[i]);
        if (snap) setSnapshot(pages[i], snap);
        setLastVisited(pages[i]);
      }
      // Also set tax as visited
      setLastVisited('tax');
      return;
    }

    // Detect changes for each page
    var notifications = {};
    var totalCount = 0;

    for (var page in pageDetectors) {
      var detector = pageDetectors[page];
      var items = detector();
      if (items.length > 0) {
        notifications[page] = items;
        totalCount += items.length;
      }
    }

    // Don't badge the currently active page — user is already looking at it
    var activePage = localStorage.getItem('activePage') || 'overview';
    if (notifications[activePage]) {
      totalCount -= notifications[activePage].length;
      delete notifications[activePage];
    }
    // Update snapshot for active page
    var activeSnap = computeSnapshot(activePage);
    if (activeSnap) setSnapshot(activePage, activeSnap);
    setLastVisited(activePage);

    // Render badges on nav items
    for (var page in notifications) {
      var navItem = document.querySelector('.nav-item[data-page="' + page + '"]');
      if (navItem && navItem.style.display !== 'none') {
        renderBadge(navItem, notifications[page].length);
      }
    }

    // Show toast if there are notifications
    if (totalCount > 0) {
      showToast(notifications);
    }
  }

  // --- Public API for nav.js integration ---
  window.notifyBadgeClear = function(page) {
    clearBadge(page);
    setLastVisited(page);
    // Update snapshot so same change doesn't re-trigger
    var snap = computeSnapshot(page);
    if (snap) setSnapshot(page, snap);
  };

  // Run on load
  init();
})();
