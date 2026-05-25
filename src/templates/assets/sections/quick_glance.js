// --- Quick Glance (mobile) ---
(function() {
  var QG_PREF_KEY = 'qg_always_mobile';
  var qgEl = scopedFind(null, 'quickGlance');
  var qgToggle = scopedFind(null, 'qgAlwaysToggle');
  var qgExpandBtn = scopedFind(null, 'qgExpandBtn');
  if (!qgEl) return;

  var sparkChart = null;

  function isMobile() {
    return window.innerWidth < 768;
  }

  function getPref() {
    return localStorage.getItem(QG_PREF_KEY) === '1';
  }

  function setPref(v) {
    localStorage.setItem(QG_PREF_KEY, v ? '1' : '0');
  }

  function showQuickGlance() {
    qgEl.classList.add('active');
    document.body.style.overflow = 'hidden';
    renderQuickGlance();
  }

  function hideQuickGlance() {
    qgEl.classList.remove('active');
    document.body.style.overflow = '';
  }

  function renderQuickGlance() {
    var dates = ds.dates;
    var values = ds.value_eur;
    if (!dates || dates.length < 2) return;

    var N = dates.length;
    var currentValue = values[N - 1];
    var prevValue = values[N - 2];
    var change = currentValue - prevValue;
    var changePct = prevValue > 0 ? (change / prevValue) * 100 : 0;

    // Portfolio value
    scopedFind(null, 'qgValue').textContent = fmtCcy(currentValue);

    // Today's change
    var amountEl = scopedFind(null, 'qgChangeAmount');
    var pctEl = scopedFind(null, 'qgChangePct');
    amountEl.textContent = signCcy(change);
    amountEl.className = 'qg-change-amount ' + cls(change);
    pctEl.textContent = '(' + sign(changePct) + '%)';
    pctEl.className = 'qg-change-pct ' + cls(changePct);

    // Sparkline (last 30 days)
    renderSparkline(values.slice(-30));

    // Top movers
    renderMovers();

    // Notifications count
    renderActions();
  }

  function renderSparkline(data) {
    var canvas = scopedFind(null, 'qgSparkline');
    if (!canvas) return;

    if (sparkChart) {
      sparkChart.destroy();
      sparkChart = null;
    }

    var isUp = data.length >= 2 && data[data.length - 1] >= data[0];
    var color = isUp ? getComputedStyle(document.documentElement).getPropertyValue('--green').trim()
                     : getComputedStyle(document.documentElement).getPropertyValue('--red').trim();

    sparkChart = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: {
        labels: data.map(function(_, i) { return i; }),
        datasets: [{
          data: data,
          borderColor: color,
          backgroundColor: color.replace(')', ', 0.08)').replace('rgb', 'rgba'),
          fill: true,
          tension: 0.3,
          pointRadius: 0,
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        scales: {
          x: { display: false },
          y: { display: false }
        },
        interaction: { enabled: false },
        animation: { duration: 300 }
      }
    });
  }

  function renderMovers() {
    var list = scopedFind(null, 'qgMoversList');
    if (!list) return;

    var positions = getActivePositions();
    if (!positions || positions.length < 2) {
      list.innerHTML = '<div class="qg-empty-movers">No position data available</div>';
      return;
    }

    var names = D.company_names || {};
    var sorted = positions.filter(function(p) { return p.cost_basis_eur > 0; });
    var gainers = sorted.filter(function(p) { return p.unrealized_gain_eur > 0; })
      .sort(function(a, b) { return b.unrealized_gain_pct - a.unrealized_gain_pct; }).slice(0, 3);
    var losers = sorted.filter(function(p) { return p.unrealized_gain_eur < 0; })
      .sort(function(a, b) { return a.unrealized_gain_pct - b.unrealized_gain_pct; }).slice(0, 3);

    var movers = gainers.concat(losers).slice(0, 3);
    if (movers.length === 0 && sorted.length > 0) {
      movers = sorted.slice(0, 3);
    }

    if (movers.length === 0) {
      list.innerHTML = '<div class="qg-empty-movers">No movers today</div>';
      return;
    }

    list.innerHTML = movers.map(function(p) {
      var name = names[p.ticker] || '';
      var valCls = cls(p.unrealized_gain_pct);
      return '<div class="qg-mover-row">'
        + '<div><div class="qg-mover-ticker">' + p.ticker + '</div>'
        + (name ? '<div class="qg-mover-name">' + name + '</div>' : '')
        + '</div>'
        + '<div class="qg-mover-value ' + valCls + '">' + sign(p.unrealized_gain_pct) + '%</div>'
        + '</div>';
    }).join('');
  }

  function renderActions() {
    var actionsEl = scopedFind(null, 'qgActions');
    var badgeEl = scopedFind(null, 'qgActionsBadge');
    if (!actionsEl || !badgeEl) return;

    // Count notifications from the badge system
    var count = 0;
    var navItems = document.querySelectorAll('.nav-item .notify-badge');
    navItems.forEach(function(badge) {
      if (badge.style.display !== 'none') {
        var n = parseInt(badge.textContent, 10);
        if (!isNaN(n)) count += n;
      }
    });

    if (count > 0) {
      actionsEl.style.display = 'flex';
      badgeEl.textContent = count;
    } else {
      actionsEl.style.display = 'none';
    }
  }

  // Swipe down to dismiss
  var touchStartY = 0;
  qgEl.addEventListener('touchstart', function(e) {
    touchStartY = e.touches[0].clientY;
  }, { passive: true });

  qgEl.addEventListener('touchend', function(e) {
    var dy = e.changedTouches[0].clientY - touchStartY;
    if (dy > 80) {
      hideQuickGlance();
    }
  }, { passive: true });

  // Expand button
  qgExpandBtn.addEventListener('click', function() {
    hideQuickGlance();
  });

  // Toggle preference
  qgToggle.checked = getPref();
  qgToggle.addEventListener('change', function() {
    setPref(qgToggle.checked);
  });

  // Show Quick Glance on mobile load if preference is set or first visit
  function initQuickGlance() {
    if (!isMobile()) return;
    var pref = getPref();
    var firstVisit = !localStorage.getItem(QG_PREF_KEY);
    if (pref || firstVisit) {
      showQuickGlance();
      if (firstVisit) setPref(true);
    }
  }

  // Re-check on resize (orientation change)
  window.addEventListener('resize', function() {
    if (!isMobile() && qgEl.classList.contains('active')) {
      hideQuickGlance();
    }
  });

  // Expose for external updates
  window._quickGlanceRefresh = renderQuickGlance;

  // Initialize after data is ready (called after updateAll)
  setTimeout(initQuickGlance, 100);
})();
