// --- Dividends section ---
let _dividendChart = null;

function updateDividends() {
  const div = D.dividends;
  const calTickers = D.dividend_calendar && D.dividend_calendar.by_ticker;
  const hasIncome = div && div.by_ticker && div.by_ticker.length > 0;
  const hasCalTickers = calTickers && calTickers.length > 0;

  if (!hasIncome && !hasCalTickers) {
    document.getElementById('navDividends').style.display = 'none';
    return;
  }
  document.getElementById('navDividends').style.display = '';

  if (!hasIncome && hasCalTickers) {
    const tickerList = calTickers.map(function(tk) {
      return typeof tk === 'string' ? tk : tk.ticker;
    }).join(', ');
    document.getElementById('dividendCards').innerHTML =
      '<div class="empty-state" style="grid-column:1/-1;padding:2rem 1rem;text-align:center;color:var(--muted)">'
      + '<div style="font-size:1.5rem;margin-bottom:0.5rem">\uD83D\uDCED</div>'
      + '<p style="margin:0 0 0.5rem;font-weight:600;color:var(--text)">Dividend income will appear here once your imported files include dividend transactions.</p>'
      + '<p style="margin:0;font-size:0.85rem">Your holdings include dividend-paying tickers: <strong>' + tickerList + '</strong></p>'
      + '</div>';
    ['dividendChartSection','dividendGrowthSection','dividendProjectionSection','dividendTableSection']
      .forEach(function(id) { document.getElementById(id).style.display = 'none'; });
    _buildDividendCalendar();
    return;
  }

  // Withholding tax reclaim alert badge
  (function() {
    var badge = document.getElementById('divReclaimBadge');
    if (!badge) return;
    var dtby = D.dividend_tax || {};
    var years = Object.keys(dtby).map(Number).sort(function(a, b) { return a - b; });
    if (!years.length) { badge.style.display = 'none'; return; }
    var yr = years[years.length - 1];
    var data = dtby[yr];
    if (!data || !(data.total_reclaimable_eur > 0)) { badge.style.display = 'none'; return; }

    // Find country with highest reclaimable amount
    var topCountry = '';
    if (data.by_country) {
      var entries = Object.entries(data.by_country).filter(function(e) { return e[1].reclaimable_eur > 0.01; });
      entries.sort(function(a, b) { return b[1].reclaimable_eur - a[1].reclaimable_eur; });
      if (entries.length > 0) topCountry = entries[0][1].country_name || entries[0][0];
    }

    var amount = data.total_reclaimable_eur;
    var severity = amount >= 50 ? 'red' : 'amber';
    var countryText = topCountry ? ' from ' + topCountry : '';
    badge.innerHTML = '<span style="margin-right:0.4rem">⚠️</span>'
      + '<span>€' + amount.toLocaleString(D.locale || 'en', {minimumFractionDigits: 2, maximumFractionDigits: 2})
      + ' in withholding tax may be reclaimable' + countryText + '.</span>'
      + ' <a href="#dividendTaxSection" onclick="document.getElementById(\'dividendTaxSection\').scrollIntoView({behavior:\'smooth\'});return false;"'
      + ' style="color:inherit;font-weight:600;text-decoration:underline">See reclaim guide →</a>';
    badge.className = 'reclaim-alert-badge reclaim-alert-' + severity;
    badge.style.display = '';
  })();

  // Summary cards
  const monthly = div.by_month || [];
  const last12 = monthly.slice(-12);
  const ttm = last12.reduce((s, m) => s + m.total_eur, 0);
  const avgMonthly = monthly.length > 0 ? div.total_eur / monthly.length : 0;
  const tickers = div.by_ticker.length;
  const portfolioValue = D.summary ? D.summary.portfolio_value_eur : 0;
  const portfolioYield = portfolioValue > 0 && ttm > 0 ? (ttm / portfolioValue * 100) : null;

  document.getElementById('dividendCards').innerHTML = [
    ['div.total_income', t('div.total_income'), fmtCcy(div.total_eur), '', div.total_eur],
    ['div.last_12m', t('div.last_12m'), fmtCcy(ttm), '', ttm],
    ['div.ttm_yield', t('div.ttm_yield'), portfolioYield != null ? fmt(portfolioYield, 2) + '%' : '—', '', portfolioYield],
    ['div.monthly_avg', t('div.monthly_avg'), fmtCcy(avgMonthly), '', avgMonthly],
    ['div.paying_tickers', t('div.paying_tickers'), tickers, '', null],
  ].map(([key, l, v, c, raw]) => {
    var ttIcon = '';
    if (typeof METRIC_TOOLTIPS !== 'undefined' && METRIC_TOOLTIPS[key]) {
      var rv = raw != null ? raw : '';
      ttIcon = ' <span class="tt-icon" data-tt-key="' + key + '" data-tt-val="' + rv + '" tabindex="0" aria-label="Info">&#9432;</span>';
    }
    return `<div class="metric-card"><div class="label">${l}${ttIcon}</div><div class="value ${c}">${v}</div></div>`;
  }).join('');

  // Monthly bar chart
  _buildDividendChart(monthly);

  // Dividend calendar & forecast
  _buildDividendCalendar();

  // Per-ticker table
  const dt = document.getElementById('dividendTable');
  dt.innerHTML = '<thead><tr>'
    + '<th>' + t('pos.ticker') + '</th>'
    + '<th>' + t('div.total') + '</th>'
    + '<th>' + t('div.ttm_income') + '</th>'
    + '<th>' + t('div.ttm_yield_col') + '</th>'
    + '<th title="Yield on your original purchase cost, ignoring price changes.">' + t('div.yoc_col') + '</th>'
    + '<th>' + t('div.payments') + '</th>'
    + '<th>' + t('div.share') + '</th>'
    + '</tr></thead><tbody>'
    + div.by_ticker.map(t => {
      const share = div.total_eur > 0 ? (t.total_eur / div.total_eur * 100) : 0;
      const ttm = (div.ttm_by_ticker || {})[t.ticker] || 0;
      const pos = D.positions.find(p => p.ticker === t.ticker);
      const mv = pos ? pos.market_value_eur : 0;
      const yieldPct = mv > 0 && ttm > 0 ? (ttm / mv * 100) : null;
      const costBasis = pos ? pos.cost_basis_eur : 0;
      const yoc = costBasis > 0 && ttm > 0 ? (ttm / costBasis * 100) : null;
      return `<tr>`
        + `<td><strong>${t.ticker}</strong></td>`
        + `<td>${fmtEur(t.total_eur)}</td>`
        + `<td>${fmtEur(ttm)}</td>`
        + `<td>${yieldPct != null ? fmt(yieldPct, 2) + '%' : '—'}</td>`
        + `<td>${yoc != null ? fmt(yoc, 2) + '%' : '—'}</td>`
        + `<td>${t.count}</td>`
        + `<td>${fmt(share, 1)}%</td>`
        + `</tr>`;
    }).join('')
    + '</tbody>';

  makeSortable(dt);
}

function _buildDividendChart(monthly) {
  if (_dividendChart) {
    _dividendChart.destroy();
    _dividendChart = null;
  }

  const canvas = document.getElementById('dividendChart');
  if (!canvas || monthly.length === 0) return;

  const labels = monthly.map(m => m.month);
  const values = monthly.map(m => m.total_eur);

  _dividendChart = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: t('div.chart_label') + ' (' + _currency + ')',
        data: values,
        backgroundColor: 'rgba(52,211,153,0.5)',
        borderColor: '#34d399',
        borderWidth: 1,
        borderRadius: 3,
      }],
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
            font: { size: 10 },
            maxTicksLimit: 12,
            callback: function(val, i) {
              // Show only year labels to reduce clutter
              const label = this.getLabelForValue(val);
              return label.endsWith('-01') ? label.slice(0, 4) : '';
            },
          },
        },
        y: {
          position: 'right',
          grid: { color: 'rgba(30,42,58,0.8)' },
          ticks: {
            color: '#556075',
            font: { size: 10 },
            callback: v => fmtEur(v),
          },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: c => c[0].label,
            label: c => fmtEur(c.parsed.y),
          },
        },
      },
    },
  });

  // Build annual growth chart and table
  _buildDividendGrowth(monthly);
}

let _dividendGrowthChart = null;

function _buildDividendGrowth(monthly) {
  if (_dividendGrowthChart) { _dividendGrowthChart.destroy(); _dividendGrowthChart = null; }

  const section = document.getElementById('dividendGrowthSection');
  if (!monthly || monthly.length === 0) { section.style.display = 'none'; return; }

  // Aggregate by year
  const yearTotals = {};
  monthly.forEach(m => {
    const y = m.month.slice(0, 4);
    yearTotals[y] = (yearTotals[y] || 0) + m.total_eur;
  });
  const years = Object.keys(yearTotals).sort();
  if (years.length < 2) { section.style.display = 'none'; return; }
  section.style.display = '';

  const totals = years.map(y => yearTotals[y]);

  // Chart
  const canvas = document.getElementById('dividendGrowthChart');
  _dividendGrowthChart = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels: years,
      datasets: [{
        label: t('div.annual_label') + ' (' + _currency + ')',
        data: totals,
        backgroundColor: 'rgba(99,102,241,0.5)',
        borderColor: '#6366f1',
        borderWidth: 1,
        borderRadius: 4,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      scales: {
        x: { grid: { display: false }, ticks: { color: '#556075', font: { size: 11 } } },
        y: {
          position: 'right',
          grid: { color: 'rgba(30,42,58,0.8)' },
          ticks: { color: '#556075', font: { size: 10 }, callback: v => fmtEur(v) },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: c => fmtEur(c.parsed.y) } },
      },
    },
  });

  // Growth table
  const gt = document.getElementById('dividendGrowthTable');
  gt.innerHTML = '<thead><tr><th>' + t('div.growth.year') + '</th><th>' + t('div.growth.income') + '</th><th>' + t('div.growth.yoy') + '</th><th>' + t('div.growth.pct') + '</th></tr></thead><tbody>'
    + years.map((y, i) => {
      const val = yearTotals[y];
      const prev = i > 0 ? yearTotals[years[i - 1]] : null;
      const growth = prev != null ? val - prev : null;
      const growthPct = prev != null && prev > 0 ? (val / prev - 1) * 100 : null;
      return '<tr>'
        + '<td><strong>' + y + '</strong></td>'
        + '<td>' + fmtEur(val) + '</td>'
        + '<td class="' + (growth != null ? cls(growth) : '') + '">'
          + (growth != null ? sign(growth * _fx) + ' ' + _currency : '—') + '</td>'
        + '<td class="' + (growthPct != null ? cls(growthPct) : '') + '">'
          + (growthPct != null ? sign(growthPct) + '%' : '—') + '</td>'
        + '</tr>';
    }).join('')
    + '</tbody>';
  makeSortable(gt);

  // --- Dividend Projection ---
  _buildDividendProjection(monthly);
}

// --- Dividend Calendar ---
let _divCalendarChart = null;

function _buildDividendCalendar() {
  if (_divCalendarChart) { _divCalendarChart.destroy(); _divCalendarChart = null; }

  var cal = D.dividend_calendar;
  var section = document.getElementById('dividendCalendarSection');
  if (!cal || !cal.upcoming || cal.upcoming.length === 0) {
    section.style.display = 'none';
    return;
  }
  section.style.display = '';

  // Summary cards
  var cards = document.getElementById('divCalendarCards');
  var nextEvent = cal.upcoming[0];
  var daysUntil = Math.ceil((new Date(nextEvent.ex_date) - new Date()) / 86400000);
  cards.innerHTML = [
    [t('div.cal.annual_projected'), fmtCcy(cal.projected_annual_income_eur), ''],
    [t('div.cal.monthly_avg'), fmtCcy(cal.projected_monthly_income_eur), ''],
    [t('div.cal.yield_on_cost'), cal.yield_on_cost != null ? fmt(cal.yield_on_cost, 2) + '%' : '—', ''],
    [t('div.cal.next_exdate'), nextEvent.ticker + ' (' + daysUntil + 'd)', ''],
  ].map(function(row) {
    return '<div class="metric-card"><div class="label">' + row[0] + '</div><div class="value ' + row[2] + '">' + row[1] + '</div></div>';
  }).join('');

  // Dividend change alerts
  var alertsEl = document.getElementById('divCalendarAlerts');
  if (cal.dividend_changes && cal.dividend_changes.length > 0) {
    alertsEl.innerHTML = cal.dividend_changes.map(function(ch) {
      var icon = ch.type === 'increase' ? '↑' : '↓';
      var cls = ch.type === 'increase' ? 'pos' : 'neg';
      return '<div class="alert-badge ' + cls + '" style="display:inline-block;padding:0.25rem 0.6rem;border-radius:4px;font-size:0.75rem;margin-right:0.5rem;margin-bottom:0.25rem;background:var(--card-bg);border:1px solid var(--border)">'
        + '<strong>' + ch.ticker + '</strong> ' + icon + ' '
        + (ch.change_pct > 0 ? '+' : '') + fmt(ch.change_pct, 1) + '% '
        + '($' + fmt(ch.previous_amount, 4) + ' → $' + fmt(ch.latest_amount, 4) + ')'
        + '</div>';
    }).join('');
  } else {
    alertsEl.innerHTML = '';
  }

  // Monthly projected income chart (next 12 months)
  var months = Object.keys(cal.monthly_breakdown).sort().slice(0, 12);
  var values = months.map(function(m) { return cal.monthly_breakdown[m]; });

  if (months.length > 0) {
    var canvas = document.getElementById('divCalendarChart');
    _divCalendarChart = new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: {
        labels: months,
        datasets: [{
          label: t('div.cal.projected_income') + ' (' + _currency + ')',
          data: values,
          backgroundColor: function(ctx) {
            // Past months lighter, future months brighter
            var m = months[ctx.dataIndex];
            var now = new Date().toISOString().slice(0, 7);
            return m <= now ? 'rgba(52,211,153,0.3)' : 'rgba(52,211,153,0.6)';
          },
          borderColor: '#34d399',
          borderWidth: 1,
          borderRadius: 3,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: 'index', intersect: false },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: '#556075', font: { size: 10 } },
          },
          y: {
            position: 'right',
            grid: { color: 'rgba(30,42,58,0.8)' },
            ticks: { color: '#556075', font: { size: 10 }, callback: function(v) { return fmtCcy(v); } },
          },
        },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: function(c) { return fmtCcy(c.parsed.y); } } },
        },
      },
    });
  }

  // Upcoming events table
  var tbl = document.getElementById('divCalendarTable');
  var now = new Date().toISOString().slice(0, 10);
  tbl.innerHTML = '<thead><tr>'
    + '<th>' + t('div.cal.ex_date') + '</th>'
    + '<th>' + t('pos.ticker') + '</th>'
    + '<th>' + t('div.cal.amount_share') + '</th>'
    + '<th>' + t('div.cal.shares') + '</th>'
    + '<th>' + t('div.cal.est_income') + '</th>'
    + '<th>' + t('div.cal.type') + '</th>'
    + '</tr></thead><tbody>'
    + cal.upcoming.slice(0, 30).map(function(ev) {
      var days = Math.ceil((new Date(ev.ex_date) - new Date()) / 86400000);
      var badge = ev.is_projected
        ? '<span style="font-size:0.7rem;padding:0.1rem 0.3rem;border-radius:3px;background:var(--muted-bg,rgba(99,102,241,0.15));color:var(--muted)">projected</span>'
        : '<span style="font-size:0.7rem;padding:0.1rem 0.3rem;border-radius:3px;background:rgba(52,211,153,0.15);color:#34d399">confirmed</span>';
      return '<tr>'
        + '<td><strong>' + ev.ex_date + '</strong><br><span style="font-size:0.7rem;color:var(--muted)">' + (days > 0 ? 'in ' + days + 'd' : 'today') + '</span></td>'
        + '<td><strong>' + ev.ticker + '</strong></td>'
        + '<td>$' + fmt(ev.amount_per_share, 4) + '</td>'
        + '<td>' + fmt(ev.shares_held, 2) + '</td>'
        + '<td>' + fmtEur(ev.projected_income_eur) + '</td>'
        + '<td>' + badge + '</td>'
        + '</tr>';
    }).join('')
    + '</tbody>';
  makeSortable(tbl);
}

let _dividendProjectionChart = null;

function _buildDividendProjection(monthly) {
  if (_dividendProjectionChart) { _dividendProjectionChart.destroy(); _dividendProjectionChart = null; }

  const section = document.getElementById('dividendProjectionSection');
  if (!monthly || monthly.length === 0) { section.style.display = 'none'; return; }

  // Aggregate by year
  const yearTotals = {};
  monthly.forEach(function(m) {
    const y = m.month.slice(0, 4);
    yearTotals[y] = (yearTotals[y] || 0) + m.total_eur;
  });
  const years = Object.keys(yearTotals).sort();

  // Need at least 2 complete years for meaningful projection
  // Consider the latest year potentially incomplete
  const currentYear = new Date().getFullYear().toString();
  const completeYears = years.filter(function(y) { return y < currentYear; });
  if (completeYears.length < 2) { section.style.display = 'none'; return; }
  section.style.display = '';

  // Calculate CAGR from complete years
  const firstYear = completeYears[0];
  const lastYear = completeYears[completeYears.length - 1];
  const firstVal = yearTotals[firstYear];
  const lastVal = yearTotals[lastYear];
  const numYears = parseInt(lastYear) - parseInt(firstYear);
  const cagr = numYears > 0 && firstVal > 0
    ? Math.pow(lastVal / firstVal, 1 / numYears) - 1
    : 0;

  // TTM (trailing 12 months) income as projection base
  const last12 = monthly.slice(-12);
  const ttmIncome = last12.reduce(function(s, m) { return s + m.total_eur; }, 0);

  // Project 5 years forward
  const projectionYears = 5;
  const startYear = parseInt(currentYear);
  const projectedYears = [];
  const projectedValues = [];
  const projectedLow = [];   // conservative: half growth rate
  const projectedHigh = [];  // optimistic: 1.5x growth rate

  for (var i = 0; i <= projectionYears; i++) {
    var yr = startYear + i;
    projectedYears.push(yr.toString());
    var base = ttmIncome * Math.pow(1 + cagr, i);
    var low = ttmIncome * Math.pow(1 + cagr * 0.5, i);
    var high = ttmIncome * Math.pow(1 + Math.min(cagr * 1.5, 0.25), i);
    projectedValues.push(Math.round(base));
    projectedLow.push(Math.round(low));
    projectedHigh.push(Math.round(high));
  }

  // Summary cards
  document.getElementById('divProjectionTitle').textContent = t('div.projection.title');
  document.getElementById('divProjectionDesc').textContent =
    t('div.projection.desc', {years: numYears, cagr: fmt(cagr * 100, 1)});

  var year5 = projectedValues[projectionYears];
  document.getElementById('divProjectionCards').innerHTML = [
    [t('div.projection.ttm'), fmtCcy(ttmIncome), ''],
    [t('div.projection.growth_rate'), (cagr >= 0 ? '+' : '') + fmt(cagr * 100, 1) + '% ' + t('div.projection.cagr'), cagr >= 0 ? 'pos' : 'neg'],
    [t('div.projection.year5'), fmtCcy(year5), ''],
  ].map(function(row) {
    return '<div class="metric-card"><div class="label">' + row[0] + '</div><div class="value ' + row[2] + '">' + row[1] + '</div></div>';
  }).join('');
  document.getElementById('divProjectionBandNote').textContent =
    t('div.projection.band_note', {years: numYears, cagr: fmt(cagr * 100, 1)});

  // Chart: historical bars + projected line with confidence band
  var historicalYears = completeYears.slice();
  if (years.indexOf(currentYear) >= 0) {
    historicalYears.push(currentYear);
  }
  var allLabels = historicalYears.slice();
  for (i = 1; i <= projectionYears; i++) {
    var futureYear = (startYear + i).toString();
    if (allLabels.indexOf(futureYear) < 0) allLabels.push(futureYear);
  }
  allLabels.sort();

  var histData = allLabels.map(function(y) { return yearTotals[y] != null ? yearTotals[y] : null; });
  var projLine = allLabels.map(function(y) {
    var idx = projectedYears.indexOf(y);
    return idx >= 0 ? projectedValues[idx] : null;
  });
  var bandLow = allLabels.map(function(y) {
    var idx = projectedYears.indexOf(y);
    return idx >= 0 ? projectedLow[idx] : null;
  });
  var bandHigh = allLabels.map(function(y) {
    var idx = projectedYears.indexOf(y);
    return idx >= 0 ? projectedHigh[idx] : null;
  });

  var canvas = document.getElementById('dividendProjectionChart');
  _dividendProjectionChart = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels: allLabels,
      datasets: [
        {
          label: t('div.projection.historical'),
          data: histData,
          backgroundColor: 'rgba(52,211,153,0.5)',
          borderColor: '#34d399',
          borderWidth: 1,
          borderRadius: 4,
          order: 2,
        },
        {
          label: t('div.projection.projected'),
          data: projLine,
          type: 'line',
          borderColor: '#6366f1',
          backgroundColor: 'rgba(99,102,241,0.1)',
          borderWidth: 2,
          borderDash: [4, 3],
          pointRadius: 4,
          pointBackgroundColor: '#6366f1',
          fill: false,
          tension: 0.2,
          order: 1,
        },
        {
          label: t('div.projection.range'),
          data: bandHigh,
          type: 'line',
          borderColor: 'rgba(99,102,241,0.35)',
          borderDash: [2, 4],
          borderWidth: 1,
          backgroundColor: 'rgba(99,102,241,0.08)',
          fill: '+1',
          pointRadius: 0,
          tension: 0.2,
          order: 0,
        },
        {
          label: '_low',
          data: bandLow,
          type: 'line',
          borderColor: 'transparent',
          backgroundColor: 'transparent',
          fill: false,
          pointRadius: 0,
          tension: 0.2,
          order: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: { grid: { display: false }, ticks: { color: '#556075', font: { size: 11 } } },
        y: {
          position: 'right',
          grid: { color: 'rgba(30,42,58,0.8)' },
          ticks: { color: '#556075', font: { size: 10 }, callback: function(v) { return fmtCcy(v); } },
        },
      },
      plugins: {
        legend: {
          display: true,
          labels: {
            filter: function(item) { return item.text !== '_low'; },
            font: { size: 10 },
          },
        },
        tooltip: {
          callbacks: {
            label: function(c) {
              if (c.dataset.label === '_low') return '';
              if (c.dataset.label === t('div.projection.range')) {
                var lowDs = c.chart.data.datasets.find(function(d) { return d.label === '_low'; });
                var lowVal = lowDs ? lowDs.data[c.dataIndex] : null;
                if (lowVal == null || c.parsed.y == null) return '';
                return t('div.projection.range_tooltip') + ': ' + fmtCcy(lowVal) + ' – ' + fmtCcy(c.parsed.y);
              }
              return c.dataset.label + ': ' + fmtCcy(c.parsed.y);
            },
          },
        },
      },
    },
  });
}
