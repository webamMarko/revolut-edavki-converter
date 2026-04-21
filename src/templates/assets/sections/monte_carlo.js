// --- Monte Carlo portfolio projection ---
(function() {
  var section = document.getElementById('monteCarloSection');
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
  var bar = document.getElementById('mcHorizonBar');
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
    document.getElementById('mcTitle').textContent = t('mc.title');
    document.getElementById('mcDesc').textContent =
      t('mc.desc', {sims: NUM_SIMULATIONS, years: currentHorizon});

    document.getElementById('mcCards').innerHTML = [
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
    var canvas = document.getElementById('mcChart');
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
