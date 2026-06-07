// --- Monte Carlo portfolio projection ---
(function() {
  var section = scopedFind(null, 'monteCarloSection');
  if (!section || !ds || !ds.value_eur || ds.value_eur.length < 60) return;

  // Compute daily log returns from portfolio value
  var values = ds.value_eur;
  var invested = ds.invested_eur;
  var dailyReturns = [];
  for (var i = 1; i < values.length; i++) {
    if (values[i - 1] > 0 && invested[i] === invested[i - 1]) {
      // Only use days without cash flows for unbiased returns
      dailyReturns.push(values[i] / values[i - 1] - 1);
    }
  }

  if (dailyReturns.length < 30) return;
  section.style.display = '';

  var NUM_SIMULATIONS = 500;
  var TRADING_DAYS_PER_YEAR = 252;
  var currentValue = values[values.length - 1];
  var currentHorizon = 5; // default 5 years
  var _mcChart = null;

  // Build horizon selector buttons
  var bar = scopedFind(null, 'mcHorizonBar');
  [1, 3, 5, 10].forEach(function(yr) {
    var btn = document.createElement('button');
    btn.className = 'range-btn' + (yr === currentHorizon ? ' active' : '');
    btn.textContent = yr + 'Y';
    btn.addEventListener('click', function() {
      currentHorizon = yr;
      bar.querySelectorAll('.range-btn').forEach(function(b) { b.classList.remove('active'); });
      btn.classList.add('active');
      runSimulation();
    });
    bar.appendChild(btn);
  });

  function runSimulation() {
    var days = currentHorizon * TRADING_DAYS_PER_YEAR;
    var paths = [];

    // Simple bootstrap: resample daily returns with replacement
    for (var s = 0; s < NUM_SIMULATIONS; s++) {
      var path = [currentValue];
      var val = currentValue;
      for (var d = 0; d < days; d++) {
        var idx = Math.floor(Math.random() * dailyReturns.length);
        val = val * (1 + dailyReturns[idx]);
        // Sample at monthly intervals for chart
        if ((d + 1) % 21 === 0 || d === days - 1) {
          path.push(val);
        }
      }
      paths.push(path);
    }

    var months = paths[0].length;

    // Compute percentiles at each time step
    var p10 = [], p25 = [], p50 = [], p75 = [], p90 = [];
    for (var m = 0; m < months; m++) {
      var vals = [];
      for (s = 0; s < paths.length; s++) {
        vals.push(paths[s][m]);
      }
      vals.sort(function(a, b) { return a - b; });
      p10.push(percentile(vals, 10));
      p25.push(percentile(vals, 25));
      p50.push(percentile(vals, 50));
      p75.push(percentile(vals, 75));
      p90.push(percentile(vals, 90));
    }

    // Final outcomes for summary
    var finalVals = paths.map(function(p) { return p[p.length - 1]; });
    finalVals.sort(function(a, b) { return a - b; });
    var medianFinal = percentile(finalVals, 50);
    var lossProb = finalVals.filter(function(v) { return v < currentValue; }).length / finalVals.length * 100;
    var bestCase = percentile(finalVals, 90);
    var worstCase = percentile(finalVals, 10);

    // Summary cards
    scopedFind(null, 'mcTitle').textContent = t('mc.title');
    scopedFind(null, 'mcDesc').textContent =
      t('mc.desc', {sims: NUM_SIMULATIONS, years: currentHorizon});

    scopedFind(null, 'mcCards').innerHTML = [
      [t('mc.median_outcome'), fmtCcy(medianFinal), medianFinal >= currentValue ? 'pos' : 'neg'],
      [t('mc.best_case'), fmtCcy(bestCase), 'pos', '90th ' + t('mc.percentile')],
      [t('mc.worst_case'), fmtCcy(worstCase), worstCase >= currentValue ? '' : 'neg', '10th ' + t('mc.percentile')],
      [t('mc.loss_probability'), fmt(lossProb, 1) + '%', lossProb > 50 ? 'neg' : ''],
    ].map(function(row) {
      return '<div class="metric-card"><div class="label">' + row[0] + '</div><div class="value ' + (row[2] || '') + '">' + row[1] + '</div>'
        + (row[3] ? '<div class="sub" style="color:var(--muted);font-size:0.65rem">' + row[3] + '</div>' : '')
        + '</div>';
    }).join('');

    // Chart labels (months from now)
    var labels = [];
    for (m = 0; m < months; m++) {
      if (m === 0) labels.push(t('mc.now'));
      else labels.push(m + ' ' + t('mc.months'));
    }

    // Build fan chart
    if (_mcChart) { _mcChart.destroy(); _mcChart = null; }
    var canvas = scopedFind(null, 'mcChart');
    _mcChart = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          // 10-90 band
          { label: '90th', data: p90, borderColor: 'transparent', backgroundColor: 'rgba(99,102,241,0.06)', fill: '+4', pointRadius: 0, tension: 0.3 },
          // 25-75 band
          { label: '75th', data: p75, borderColor: 'transparent', backgroundColor: 'rgba(99,102,241,0.1)', fill: '+2', pointRadius: 0, tension: 0.3 },
          // Median line
          { label: t('mc.median'), data: p50, borderColor: '#6366f1', borderWidth: 2.5, backgroundColor: 'transparent', fill: false, pointRadius: 0, tension: 0.3 },
          // 25th
          { label: '25th', data: p25, borderColor: 'transparent', backgroundColor: 'transparent', fill: false, pointRadius: 0, tension: 0.3 },
          // 10th
          { label: '10th', data: p10, borderColor: 'transparent', backgroundColor: 'transparent', fill: false, pointRadius: 0, tension: 0.3 },
          // Current value line
          { label: t('mc.current'), data: new Array(months).fill(currentValue), borderColor: '#9e9e9e', borderDash: [5, 5], borderWidth: 1, pointRadius: 0, fill: false },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: 'index', intersect: false },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              color: '#556075',
              font: { size: 9 },
              maxTicksLimit: 8,
            },
          },
          y: {
            title: { display: true, text: _currency },
            ticks: { color: '#556075', callback: function(v) { return (v * _fx).toLocaleString(_locale); } },
            grid: { color: 'rgba(30,42,58,0.5)' },
          },
        },
        plugins: {
          legend: {
            display: true,
            labels: {
              filter: function(item) {
                return item.text === t('mc.median') || item.text === t('mc.current');
              },
              font: { size: 10 },
            },
          },
          tooltip: {
            callbacks: {
              label: function(c) {
                if (c.dataset.label === t('mc.median') || c.dataset.label === t('mc.current')) {
                  return c.dataset.label + ': ' + fmtCcy(c.parsed.y);
                }
                return '';
              },
            },
          },
        },
      },
    });
  }

  function percentile(sorted, p) {
    var i = (p / 100) * (sorted.length - 1);
    var lo = Math.floor(i);
    var hi = Math.ceil(i);
    if (lo === hi) return sorted[lo];
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
  }

  runSimulation();
})();

// --- FIRE section on Projections page ---
var _fireChart = null;
function updateFire() {
  var fireSection = scopedFind(null, 'fireSection');
  if (!fireSection || D.fire == null) return;

  var s = getActiveSummary();
  if (!s || s.portfolio_value_eur == null) { fireSection.style.display = 'none'; return; }

  fireSection.style.display = '';

  var expensesInput = scopedFind(null, 'projFireExpenses');
  var incomeInput = scopedFind(null, 'projFireIncome');
  var withdrawalInput = scopedFind(null, 'projFireWithdrawal');
  var inflInput = scopedFind(null, 'projFireInflation');
  var contribInput = scopedFind(null, 'projFireContrib');

  var expenses = expensesInput ? parseFloat(expensesInput.value) || 0 : 0;
  var income = incomeInput ? parseFloat(incomeInput.value) || 0 : 0;
  var withdrawalRate = withdrawalInput ? parseFloat(withdrawalInput.value) || 4 : 4;
  var infl = inflInput ? parseFloat(inflInput.value) || 0 : 3;
  var monthlyContrib = contribInput ? parseFloat(contribInput.value) || 0 : 0;
  var annualContrib = monthlyContrib * 12;

  var gap = Math.max(expenses - income, 0);
  var fireTarget = withdrawalRate > 0 ? Math.round(gap / (withdrawalRate / 100) * 100) / 100 : 0;
  var portfolioVal = s.portfolio_value_eur;
  var progress = fireTarget > 0 ? portfolioVal / fireTarget * 100 : 100;
  var remaining = fireTarget - portfolioVal;

  var yearsToFire = null;
  var nominalCAGR = 0;
  var realReturn = 0;
  if (remaining > 0 && s.cagr_pct != null && s.cagr_pct > 0) {
    nominalCAGR = s.cagr_pct / 100;
    var inflation = infl / 100;
    realReturn = (1 + nominalCAGR) / (1 + inflation) - 1;
    if (realReturn > 0) {
      yearsToFire = annualContrib > 0
        ? yearsToFireWithContrib(portfolioVal, fireTarget, realReturn, annualContrib)
        : Math.log(fireTarget / portfolioVal) / Math.log(1 + realReturn);
    }
  }

  var fireYear = yearsToFire != null ? new Date().getFullYear() + Math.ceil(yearsToFire) : null;

  function cardHtml(row) {
    return '<div class="metric-card"><div class="label">' + row[0] + '</div><div class="value ' + (row[2] || '') + '">' + row[1] + '</div></div>';
  }

  var primaryCards = [
    [t('summary.fire_progress'), fmt(progress, 1) + '%', progress >= 100 ? 'pos' : ''],
    ['Target', fmtCcy(fireTarget), ''],
    ['Current Value', fmtCcy(portfolioVal), ''],
  ];
  if (yearsToFire != null) {
    primaryCards.push(['Est. Years', '~' + fmt(yearsToFire, 1), '']);
  }

  var secondaryCards = [
    ['Remaining', remaining > 0 ? fmtCcy(remaining) : t('summary.fire_achieved'), remaining > 0 ? '' : 'pos'],
  ];
  if (yearsToFire != null) {
    secondaryCards.push(['Est. Year', String(fireYear), '']);
  }

  scopedFind(null, 'fireCards').innerHTML = primaryCards.map(cardHtml).join('');
  var secondaryEl = scopedFind(null, 'fireSecondaryCards');
  if (secondaryEl) secondaryEl.innerHTML = secondaryCards.map(cardHtml).join('');

  // --- FIRE projection chart ---
  if (_fireChart) { _fireChart.destroy(); _fireChart = null; }
  var canvas = scopedFind(null, 'fireChart');
  if (!canvas) return;

  var inflRate = infl / 100;
  var horizon = Math.max(Math.ceil((yearsToFire || 10) * 1.2), 10);
  horizon = Math.min(horizon, 50);
  var currentYear = new Date().getFullYear();

  var labels = [];
  var projectedValues = [];
  var targetLine = [];
  var contribOnlyValues = [];
  var val = portfolioVal;
  var contribVal = portfolioVal;
  var target = fireTarget;

  for (var y = 0; y <= horizon; y++) {
    labels.push(String(currentYear + y));
    projectedValues.push(val);
    targetLine.push(target);
    contribOnlyValues.push(contribVal);

    if (realReturn > 0) {
      val = val * (1 + realReturn) + annualContrib;
    } else {
      val = val + annualContrib;
    }
    contribVal = contribVal + annualContrib;
    target = target * (1 + inflRate);
  }

  _fireChart = new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: { labels: labels, datasets: [
      {
        label: 'Projected (CAGR + contributions)',
        data: projectedValues,
        borderColor: '#6366f1',
        backgroundColor: 'rgba(99,102,241,0.08)',
        fill: true, tension: 0.3, pointRadius: 0, borderWidth: 2.5,
      },
      {
        label: 'Contributions only (no growth)',
        data: contribOnlyValues,
        borderColor: '#556075',
        borderDash: [4, 4], borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0.3,
      },
      {
        label: 'FIRE Target (inflation-adjusted)',
        data: targetLine,
        borderColor: '#f59e0b',
        borderDash: [8, 4], borderWidth: 2, pointRadius: 0, fill: false,
      },
    ]},
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: { grid: { display: false }, ticks: { color: '#556075', font: { size: 10 }, maxTicksLimit: 12 } },
        y: {
          title: { display: true, text: _currency },
          ticks: { color: '#556075', font: { size: 10 }, callback: function(v) { return (v * _fx).toLocaleString(_locale); } },
          grid: { color: 'rgba(30,42,58,0.5)' },
        },
      },
      plugins: {
        legend: { display: true, labels: { font: { size: 10 } } },
        tooltip: { callbacks: { label: function(c) { return c.dataset.label + ': ' + fmtCcy(c.parsed.y); } } },
      },
    },
  });
}

// Initialize FIRE section
(function() {
  if (!scopedFind(null, 'fireSection') || D.fire == null) return;
  var fire = D.fire;
  var ids = ['projFireExpenses', 'projFireIncome', 'projFireWithdrawal', 'projFireInflation', 'projFireContrib'];
  var defaults = [fire.annual_expenses || 0, fire.annual_income || 0, fire.withdrawal_rate || 4, fire.inflation_rate || 2.5, 0];
  ids.forEach(function(id, i) {
    var el = scopedFind(null, id);
    if (el) {
      el.value = defaults[i];
      el.addEventListener('change', updateFire);
      el.addEventListener('input', updateFire);
    }
  });

  // Wire accordion toggle for collapsible panel inside fire section
  var fireSection = scopedFind(null, 'fireSection');
  if (fireSection) {
    fireSection.querySelectorAll('.coll-panel-hdr').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var open = this.getAttribute('aria-expanded') === 'true';
        this.setAttribute('aria-expanded', open ? 'false' : 'true');
        var body = document.getElementById(this.getAttribute('aria-controls'));
        if (body) body.classList.toggle('is-open', !open);
      });
    });
  }

  updateFire();
})();

// --- Projection sub-tab switching ---
(function() {
  var tabBar = scopedFind(null, 'projSubtabs');
  if (!tabBar) return;

  var tabs = tabBar.querySelectorAll('[data-proj-tab]');
  var panels = document.querySelectorAll('[data-proj-panel]');

  function switchTab(tabId) {
    tabs.forEach(function(t) {
      t.classList.toggle('active', t.getAttribute('data-proj-tab') === tabId);
    });
    panels.forEach(function(p) {
      var match = p.getAttribute('data-proj-panel') === tabId;
      var hasData = p.getAttribute('data-has-data') !== 'false';
      p.style.display = match && hasData ? '' : 'none';
    });
  }

  tabs.forEach(function(tab) {
    tab.addEventListener('click', function() {
      switchTab(this.getAttribute('data-proj-tab'));
    });
  });

  // Mark panels that have data; hide tabs with no data
  setTimeout(function() {
    panels.forEach(function(p) {
      if (p.style.display === 'none' && !p.getAttribute('data-has-data')) {
        p.setAttribute('data-has-data', 'false');
      }
    });
    tabs.forEach(function(tab) {
      var tabId = tab.getAttribute('data-proj-tab');
      var panel = document.querySelector('[data-proj-panel="' + tabId + '"]');
      if (panel && panel.getAttribute('data-has-data') === 'false') {
        tab.style.opacity = '0.4';
      }
    });
    // Show the first tab that has data
    var activeTab = tabBar.querySelector('.proj-subtab.active');
    var activePanel = activeTab ? document.querySelector('[data-proj-panel="' + activeTab.getAttribute('data-proj-tab') + '"]') : null;
    if (activePanel && activePanel.getAttribute('data-has-data') === 'false') {
      var firstAvailable = null;
      tabs.forEach(function(t) {
        if (!firstAvailable) {
          var p = document.querySelector('[data-proj-panel="' + t.getAttribute('data-proj-tab') + '"]');
          if (p && p.getAttribute('data-has-data') !== 'false') firstAvailable = t.getAttribute('data-proj-tab');
        }
      });
      if (firstAvailable) switchTab(firstAvailable);
    } else if (activeTab) {
      switchTab(activeTab.getAttribute('data-proj-tab'));
    }
  }, 100);
})();

// --- Dividend Projection on Projections page ---
(function() {
  var section = scopedFind(null, 'projDividendSection');
  if (!section) return;

  var div = D.dividends;
  if (!div || !div.by_month || div.by_month.length === 0) {
    section.setAttribute('data-has-data', 'false');
    return;
  }

  var monthly = div.by_month;
  var yearTotals = {};
  monthly.forEach(function(m) {
    var y = m.month.slice(0, 4);
    yearTotals[y] = (yearTotals[y] || 0) + m.total_eur;
  });
  var years = Object.keys(yearTotals).sort();
  var currentYear = new Date().getFullYear().toString();
  var completeYears = years.filter(function(y) { return y < currentYear; });
  if (completeYears.length < 2) {
    section.setAttribute('data-has-data', 'false');
    return;
  }

  section.style.display = '';
  section.setAttribute('data-has-data', 'true');

  var firstYear = completeYears[0];
  var lastYear = completeYears[completeYears.length - 1];
  var firstVal = yearTotals[firstYear];
  var lastVal = yearTotals[lastYear];
  var numYears = parseInt(lastYear) - parseInt(firstYear);
  var cagr = numYears > 0 && firstVal > 0 ? Math.pow(lastVal / firstVal, 1 / numYears) - 1 : 0;

  var last12 = monthly.slice(-12);
  var ttmIncome = last12.reduce(function(s, m) { return s + m.total_eur; }, 0);

  var projectionYears = 5;
  var startYear = parseInt(currentYear);
  var projectedYears = [], projectedValues = [], projectedLow = [], projectedHigh = [];

  for (var i = 0; i <= projectionYears; i++) {
    projectedYears.push((startYear + i).toString());
    projectedValues.push(Math.round(ttmIncome * Math.pow(1 + cagr, i)));
    projectedLow.push(Math.round(ttmIncome * Math.pow(1 + cagr * 0.5, i)));
    projectedHigh.push(Math.round(ttmIncome * Math.pow(1 + Math.min(cagr * 1.5, 0.25), i)));
  }

  var titleEl = scopedFind(null, 'projDivTitle');
  if (titleEl) titleEl.textContent = t('div.projection.title') || 'Dividend Income Projection';
  var descEl = scopedFind(null, 'projDivDesc');
  if (descEl) descEl.textContent = (t('div.projection.desc', {years: numYears, cagr: fmt(cagr * 100, 1)}) || 'Based on ' + numYears + ' years of data, ' + fmt(cagr * 100, 1) + '% CAGR');

  var year5 = projectedValues[projectionYears];
  var cardsEl = scopedFind(null, 'projDivCards');
  if (cardsEl) {
    cardsEl.innerHTML = [
      [t('div.projection.ttm') || 'TTM Income', fmtCcy(ttmIncome), ''],
      [t('div.projection.growth_rate') || 'Growth Rate', (cagr >= 0 ? '+' : '') + fmt(cagr * 100, 1) + '% CAGR', cagr >= 0 ? 'pos' : 'neg'],
      [t('div.projection.year5') || '5-Year Est.', fmtCcy(year5), ''],
    ].map(function(row) {
      return '<div class="metric-card"><div class="label">' + row[0] + '</div><div class="value ' + row[2] + '">' + row[1] + '</div></div>';
    }).join('');
  }

  var noteEl = scopedFind(null, 'projDivBandNote');
  if (noteEl) noteEl.textContent = (t('div.projection.band_note', {years: numYears, cagr: fmt(cagr * 100, 1)}) || 'Shaded band shows conservative (0.5x) to optimistic (1.5x) growth scenarios.');

  // Chart
  var historicalYears = completeYears.slice();
  if (years.indexOf(currentYear) >= 0) historicalYears.push(currentYear);
  var allLabels = historicalYears.slice();
  for (i = 1; i <= projectionYears; i++) {
    var fy = (startYear + i).toString();
    if (allLabels.indexOf(fy) < 0) allLabels.push(fy);
  }
  allLabels.sort();

  var histData = allLabels.map(function(y) { return yearTotals[y] != null ? yearTotals[y] : null; });
  var projLine = allLabels.map(function(y) { var idx = projectedYears.indexOf(y); return idx >= 0 ? projectedValues[idx] : null; });
  var bandLow = allLabels.map(function(y) { var idx = projectedYears.indexOf(y); return idx >= 0 ? projectedLow[idx] : null; });
  var bandHigh = allLabels.map(function(y) { var idx = projectedYears.indexOf(y); return idx >= 0 ? projectedHigh[idx] : null; });

  var canvas = scopedFind(null, 'projDividendChart');
  if (!canvas) return;
  new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels: allLabels,
      datasets: [
        { label: t('div.projection.historical') || 'Historical', data: histData, backgroundColor: 'rgba(52,211,153,0.5)', borderColor: '#34d399', borderWidth: 1, borderRadius: 4, order: 2 },
        { label: t('div.projection.projected') || 'Projected', data: projLine, type: 'line', borderColor: '#6366f1', backgroundColor: 'rgba(99,102,241,0.1)', borderWidth: 2, pointRadius: 3, fill: false, tension: 0.3, order: 1 },
        { label: 'Optimistic', data: bandHigh, type: 'line', borderColor: 'transparent', backgroundColor: 'rgba(99,102,241,0.06)', fill: '+1', pointRadius: 0, tension: 0.3, order: 0 },
        { label: 'Conservative', data: bandLow, type: 'line', borderColor: 'transparent', backgroundColor: 'transparent', fill: false, pointRadius: 0, tension: 0.3, order: 0 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: { grid: { display: false }, ticks: { color: '#556075', font: { size: 10 } } },
        y: { ticks: { color: '#556075', callback: function(v) { return fmtCcy(v); } }, grid: { color: 'rgba(30,42,58,0.5)' } },
      },
      plugins: {
        legend: { display: true, labels: { filter: function(item) { return item.text !== 'Optimistic' && item.text !== 'Conservative'; }, font: { size: 10 } } },
        tooltip: { callbacks: { label: function(c) { if (c.dataset.label === 'Optimistic' || c.dataset.label === 'Conservative') return ''; return c.dataset.label + ': ' + fmtCcy(c.parsed.y); } } },
      },
    },
  });
})();

// --- Goal Projections on Projections page ---
(function() {
  var section = scopedFind(null, 'projGoalsSection');
  if (!section) return;

  var listEl = scopedFind(null, 'projGoalsList');
  var emptyEl = scopedFind(null, 'projGoalsEmpty');
  if (!listEl) return;

  fetch('/api/goals', { credentials: 'same-origin' })
    .then(function(r) { return r.ok ? r.json() : Promise.reject(); })
    .then(function(goals) {
      if (!goals || goals.length === 0) {
        section.setAttribute('data-has-data', 'false');
        if (emptyEl) emptyEl.style.display = '';
        return;
      }

      section.style.display = '';
      section.setAttribute('data-has-data', 'true');

      var fetches = goals.map(function(g) {
        return fetch('/api/goals/' + g.id + '/projection', { credentials: 'same-origin' })
          .then(function(r) { return r.ok ? r.json() : null; })
          .catch(function() { return null; });
      });

      Promise.all(fetches).then(function(projections) {
        var html = '';
        goals.forEach(function(goal, idx) {
          var proj = projections[idx];
          if (!proj || proj.error) return;

          var progressPct = Math.min(proj.progress_pct || 0, 100);
          var progressColor = progressPct >= 75 ? '#34d399' : progressPct >= 50 ? '#f59e0b' : '#6366f1';

          html += '<div class="card" style="margin-bottom:0.75rem;padding:1rem">'
            + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem">'
            + '<strong>' + (goal.name || 'Goal') + '</strong>'
            + '<span style="font-size:0.8rem;color:var(--muted)">' + fmt(progressPct, 1) + '% complete</span>'
            + '</div>'
            + '<div style="background:var(--border);border-radius:4px;height:8px;overflow:hidden;margin-bottom:0.75rem">'
            + '<div style="width:' + progressPct + '%;height:100%;background:' + progressColor + ';border-radius:4px;transition:width 0.3s"></div>'
            + '</div>'
            + '<div class="card-grid small">'
            + '<div class="metric-card"><div class="label">Current</div><div class="value">' + fmtCcy(proj.current_value_eur) + '</div></div>'
            + '<div class="metric-card"><div class="label">Target</div><div class="value">' + fmtCcy(proj.target_amount_eur) + '</div></div>'
            + (proj.months_remaining != null ? '<div class="metric-card"><div class="label">Est. Months</div><div class="value">' + Math.round(proj.months_remaining) + '</div></div>' : '')
            + (proj.required_monthly_eur != null ? '<div class="metric-card"><div class="label">Monthly Needed</div><div class="value">' + fmtCcy(proj.required_monthly_eur) + '</div></div>' : '')
            + (proj.probability_of_success != null ? '<div class="metric-card"><div class="label">Success Prob.</div><div class="value">' + fmt(proj.probability_of_success, 0) + '%</div></div>' : '')
            + '</div>'
            + (proj.percentile_10 != null ? '<div style="font-size:0.75rem;color:var(--muted);margin-top:0.5rem">Range: ' + fmtCcy(proj.percentile_10) + ' (10th) — ' + fmtCcy(proj.percentile_50) + ' (50th) — ' + fmtCcy(proj.percentile_90) + ' (90th)</div>' : '')
            + '</div>';
        });

        if (html) {
          listEl.innerHTML = html;
        } else {
          section.setAttribute('data-has-data', 'false');
          if (emptyEl) emptyEl.style.display = '';
        }
      });
    })
    .catch(function() {
      section.setAttribute('data-has-data', 'false');
      if (emptyEl) emptyEl.style.display = '';
    });
})();
