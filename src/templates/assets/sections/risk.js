// --- Risk page rendering ---
let _geoChart = null;
let _riskSectorChart = null;
let _riskAllocationChart = null;
let _riskCurrencyChart = null;

const _RISK_COLORS = [
  '#6366f1','#34d399','#f59e0b','#f87171','#a78bfa',
  '#38bdf8','#fb923c','#4ade80','#e879f9','#fbbf24',
  '#22d3ee','#c084fc','#f472b6','#2dd4bf','#818cf8',
];

function _initRiskToggle(btnRole, labelRole, panelRole, showText, hideText) {
  const btn = scopedFind(null, btnRole);
  const panel = scopedFind(null, panelRole);
  if (!btn || !panel || btn._toggleBound) return;
  btn._toggleBound = true;
  btn.addEventListener('click', () => {
    const expanded = btn.getAttribute('aria-expanded') === 'true';
    btn.setAttribute('aria-expanded', String(!expanded));
    panel.classList.toggle('is-expanded', !expanded);
    scopedFind(null, labelRole).textContent = expanded ? showText : hideText;
  });
}

function updateRiskPage() {
  updateRiskWarnings();
  updateRiskConcentrationMetrics();
  updateRiskAllocation();
  updateRiskSector();
  updateRiskCurrency();
  updateGeoAllocation();
  updateRiskDiversification();
  updateRiskCorrelation();
  _initRiskToggle('riskMetricsToggle', 'riskMetricsToggleLabel', 'riskMetricsPanel', 'Show more metrics', 'Hide extra metrics');
}

function updateRiskWarnings() {
  const section = scopedFind(null, 'riskWarningsSection');
  const cr = D.concentration_risk;
  if (!cr || !cr.warnings || cr.warnings.length === 0) {
    section.style.display = 'none';
    return;
  }
  section.style.display = '';

  const el = scopedFind(null, 'riskWarnings');
  el.innerHTML = cr.warnings.map(w =>
    `<div class="risk-warning-item">`
    + `<div class="risk-warning-icon">&#9888;</div>`
    + `<div class="risk-warning-body">`
    + `<strong>${w.ticker}</strong> represents <span class="neg">${fmt(w.weight_pct, 1)}%</span> of your portfolio`
    + `<div style="color:var(--muted);font-size:0.75rem">${fmtCcy(w.value_eur)} — consider rebalancing to reduce single-stock risk</div>`
    + `</div>`
    + `</div>`
  ).join('');
}

function updateRiskConcentrationMetrics() {
  const section = scopedFind(null, 'riskMetricsSection');
  const cr = D.concentration_risk;
  if (!cr || !cr.metrics || !cr.metrics.total_positions) {
    section.style.display = 'none';
    return;
  }
  section.style.display = '';

  const m = cr.metrics;
  const hhiLabel = m.hhi < 1500 ? 'Well Diversified' : m.hhi < 2500 ? 'Moderate' : 'Concentrated';
  const hhiColor = m.hhi < 1500 ? 'pos' : m.hhi < 2500 ? '' : 'neg';

  const renderCards = cards => cards.map(([l, v, c, sub]) =>
    `<div class="metric-card"><div class="label">${l}</div><div class="value ${c || ''}">${v}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`
  ).join('');

  const el = scopedFind(null, 'riskMetricsCards');
  el.innerHTML = renderCards([
    ['Positions', m.total_positions, ''],
    ['HHI', m.hhi.toLocaleString(_locale), hhiColor, hhiLabel],
    ['Largest Position', m.largest_ticker, '', fmt(m.largest_pct, 1) + '% of portfolio'],
  ]);

  const elExtra = scopedFind(null, 'riskMetricsCardsExtra');
  elExtra.innerHTML = renderCards([
    ['Effective N', m.effective_n, '', 'Diversification-adjusted count'],
    ['Top 5 Weight', fmt(m.top5_pct, 1) + '%', m.top5_pct > 70 ? 'neg' : ''],
    ['Top 10 Weight', fmt(m.top10_pct, 1) + '%', ''],
  ]);
}

function updateRiskAllocation() {
  const positions = getActivePositions();
  const row = scopedFind(null, 'riskChartsRow');
  const section = scopedFind(null, 'riskAllocationSection');
  if (positions.length === 0) { section.style.display = 'none'; return; }
  section.style.display = '';
  row.style.display = '';

  const sorted = [...positions].sort((a, b) => b.market_value_eur - a.market_value_eur);
  const totalMV = sorted.reduce((s, p) => s + p.market_value_eur, 0) || 1;
  const items = [];
  let otherVal = 0;
  for (const p of sorted) {
    const pct = p.market_value_eur / totalMV * 100;
    if (pct >= 2 || items.length < 10) {
      items.push({ ticker: p.ticker, value: p.market_value_eur, pct });
    } else {
      otherVal += p.market_value_eur;
    }
  }
  if (otherVal > 0) {
    items.push({ ticker: 'Other', value: otherVal, pct: otherVal / totalMV * 100 });
  }

  if (_riskAllocationChart) { _riskAllocationChart.destroy(); _riskAllocationChart = null; }
  const canvas = scopedFind(null, 'riskAllocationChart');
  _riskAllocationChart = new Chart(canvas.getContext('2d'), {
    type: 'doughnut',
    data: {
      labels: items.map(i => i.ticker),
      datasets: [{
        data: items.map(i => i.value),
        backgroundColor: items.map((_, i) => _RISK_COLORS[i % _RISK_COLORS.length]),
        borderWidth: 0,
        hoverOffset: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      cutout: '55%',
      animation: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: c => c.label + ': ' + fmtEur(c.parsed) + ' (' + fmt(items[c.dataIndex].pct, 1) + '%)',
          },
        },
      },
    },
  });

  const legend = scopedFind(null, 'riskAllocationLegend');
  legend.innerHTML = items.map((item, i) =>
    `<div class="alloc-item">`
    + `<span class="alloc-dot" style="background:${_RISK_COLORS[i % _RISK_COLORS.length]}"></span>`
    + `<span>${item.ticker}</span>`
    + `<span class="alloc-pct">${fmt(item.pct, 1)}%</span>`
    + `</div>`
  ).join('');
}

function updateRiskCurrency() {
  const row = scopedFind(null, 'riskBreakdownRow');
  const section = scopedFind(null, 'riskCurrencySection');
  const data = D.currency_exposure;
  if (!data || data.length === 0) {
    section.style.display = 'none';
    return;
  }
  section.style.display = '';
  row.style.display = '';

  if (_riskCurrencyChart) { _riskCurrencyChart.destroy(); _riskCurrencyChart = null; }
  const canvas = scopedFind(null, 'riskCurrencyChart');
  _riskCurrencyChart = new Chart(canvas.getContext('2d'), {
    type: 'doughnut',
    data: {
      labels: data.map(d => d.currency),
      datasets: [{
        data: data.map(d => d.value_eur),
        backgroundColor: data.map((_, i) => _RISK_COLORS[i % _RISK_COLORS.length]),
        borderWidth: 0,
        hoverOffset: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      cutout: '55%',
      animation: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: c => c.label + ': ' + fmtEur(c.parsed) + ' (' + fmt(data[c.dataIndex].pct, 1) + '%)',
          },
        },
      },
    },
  });

  const legend = scopedFind(null, 'riskCurrencyLegend');
  legend.innerHTML = data.map((d, i) =>
    `<div class="alloc-item">`
    + `<span class="alloc-dot" style="background:${_RISK_COLORS[i % _RISK_COLORS.length]}"></span>`
    + `<span>${d.currency}</span>`
    + `<span class="alloc-pct">${fmt(d.pct, 1)}%</span>`
    + `</div>`
  ).join('');
}

function updateGeoAllocation() {
  const row = scopedFind(null, 'riskGeoRow');
  const ga = D.geographic_allocation;
  if (!ga || !ga.countries || ga.countries.length === 0) {
    row.style.display = 'none';
    return;
  }

  const countries = ga.countries.filter(c => c.pct > 0);
  if (countries.length === 0 || (countries.length === 1 && countries[0].name === 'Other')) {
    row.style.display = 'none';
    return;
  }
  row.style.display = '';

  if (_geoChart) { _geoChart.destroy(); _geoChart = null; }
  const canvas = scopedFind(null, 'geoChart');
  _geoChart = new Chart(canvas.getContext('2d'), {
    type: 'doughnut',
    data: {
      labels: countries.map(c => c.name),
      datasets: [{
        data: countries.map(c => c.value_eur),
        backgroundColor: countries.map((_, i) => _RISK_COLORS[i % _RISK_COLORS.length]),
        borderWidth: 0,
        hoverOffset: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      cutout: '55%',
      animation: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: c => c.label + ': ' + fmtEur(c.parsed) + ' (' + fmt(countries[c.dataIndex].pct, 1) + '%)',
          },
        },
      },
    },
  });

  const legend = scopedFind(null, 'geoLegend');
  legend.innerHTML = countries.map((c, i) =>
    `<div class="alloc-item">`
    + `<span class="alloc-dot" style="background:${_RISK_COLORS[i % _RISK_COLORS.length]}"></span>`
    + `<span>${c.name}</span>`
    + `<span class="alloc-pct">${fmt(c.pct, 1)}%</span>`
    + `</div>`
  ).join('');

  const table = scopedFind(null, 'geoTable');
  table.innerHTML = '<thead><tr><th>Country</th><th>Value</th><th>Weight</th></tr></thead><tbody>'
    + countries.map(c =>
      `<tr><td>${c.name}</td><td>${fmtCcy(c.value_eur)}</td><td>${fmt(c.pct, 1)}%</td></tr>`
    ).join('')
    + '</tbody>';
  makeSortable(table);
}

function updateRiskSector() {
  const row = scopedFind(null, 'riskChartsRow');
  const section = scopedFind(null, 'riskSectorSection');
  const sa = D.sector_allocation;
  if (!sa || !sa.sectors || sa.sectors.length === 0) {
    section.style.display = 'none';
    return;
  }

  const sectors = sa.sectors.filter(s => s.pct > 0);
  if (sectors.length === 0 || (sectors.length === 1 && sectors[0].name === 'Other')) {
    section.style.display = 'none';
    return;
  }
  section.style.display = '';
  row.style.display = '';

  if (_riskSectorChart) { _riskSectorChart.destroy(); _riskSectorChart = null; }
  const canvas = scopedFind(null, 'riskSectorChart');
  _riskSectorChart = new Chart(canvas.getContext('2d'), {
    type: 'doughnut',
    data: {
      labels: sectors.map(s => s.name),
      datasets: [{
        data: sectors.map(s => s.value_eur),
        backgroundColor: sectors.map((_, i) => _RISK_COLORS[i % _RISK_COLORS.length]),
        borderWidth: 0,
        hoverOffset: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      cutout: '55%',
      animation: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: c => c.label + ': ' + fmtEur(c.parsed) + ' (' + fmt(sectors[c.dataIndex].pct, 1) + '%)',
          },
        },
      },
    },
  });

  const legend = scopedFind(null, 'riskSectorLegend');
  legend.innerHTML = sectors.map((s, i) =>
    `<div class="alloc-item">`
    + `<span class="alloc-dot" style="background:${_RISK_COLORS[i % _RISK_COLORS.length]}"></span>`
    + `<span>${s.name}</span>`
    + `<span class="alloc-pct">${fmt(s.pct, 1)}%</span>`
    + `</div>`
  ).join('');

  // Industry table
  const industries = (sa.industries || []).filter(i => i.pct > 0);
  const breakdownRow = scopedFind(null, 'riskBreakdownRow');
  const industrySec = scopedFind(null, 'riskIndustrySection');
  const table = scopedFind(null, 'riskIndustryTable');
  if (industries.length > 0) {
    industrySec.style.display = '';
    breakdownRow.style.display = '';
    table.innerHTML = '<thead><tr><th>Industry</th><th>Value</th><th>Weight</th></tr></thead><tbody>'
      + industries.map(ind =>
        `<tr><td>${ind.name}</td><td>${fmtCcy(ind.value_eur)}</td><td>${fmt(ind.pct, 1)}%</td></tr>`
      ).join('')
      + '</tbody>';
    makeSortable(table);
  } else {
    industrySec.style.display = 'none';
  }
}

function updateRiskDiversification() {
  const positions = getActivePositions();
  const section = scopedFind(null, 'riskDiversificationSection');
  if (positions.length < 3) { section.style.display = 'none'; return; }
  section.style.display = '';

  const totalMV = positions.reduce((s, p) => s + p.market_value_eur, 0) || 1;
  const weights = positions.map(p => p.market_value_eur / totalMV);

  const hhi = Math.round(weights.reduce((s, w) => s + w * w, 0) * 10000);
  const hhiLabel = hhi < 1500 ? t('concentration.well_diversified') : hhi < 2500 ? t('concentration.moderate') : t('concentration.concentrated');

  const sorted = [...weights].sort((a, b) => b - a);
  const top5Pct = sorted.slice(0, 5).reduce((s, w) => s + w, 0) * 100;
  const top10Pct = sorted.slice(0, 10).reduce((s, w) => s + w, 0) * 100;

  const effective = weights.reduce((s, w) => s + w * w, 0);
  const effectiveN = effective > 0 ? Math.round(1 / effective) : positions.length;

  const largest = positions.reduce((a, b) => a.market_value_eur > b.market_value_eur ? a : b);
  const largestPct = largest.market_value_eur / totalMV * 100;

  const el = scopedFind(null, 'riskDiversificationCards');
  el.innerHTML = [
    [t('concentration.positions'), positions.length, ''],
    [t('concentration.effective'), effectiveN, '', t('concentration.effective_sub')],
    [t('concentration.hhi'), hhi.toLocaleString(_locale), '', hhiLabel],
    [t('concentration.top5'), fmt(top5Pct, 1) + '%', ''],
    [t('concentration.top10'), fmt(top10Pct, 1) + '%', ''],
    [t('concentration.largest'), largest.ticker, '', fmt(largestPct, 1) + '% ' + t('alloc.of_portfolio')],
  ].map(([l, v, c, sub]) =>
    `<div class="metric-card"><div class="label">${l}</div><div class="value ${c || ''}">${v}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`
  ).join('');
}

function updateRiskCorrelation() {
  const section = scopedFind(null, 'riskCorrelationSection');
  const corr = D.correlation;
  if (!corr || !corr.tickers || corr.tickers.length < 2) {
    section.style.display = 'none';
    return;
  }
  section.style.display = '';
  scopedFind(null, 'riskCorrelationDesc').textContent =
    'Pairwise return correlations over ' + corr.data_points + ' trading days (top holdings by market value)';

  const tickers = corr.tickers;
  const matrix = corr.matrix;
  const n = tickers.length;

  function corrColor(v) {
    if (v >= 0.7) return 'rgba(37,99,235,' + (0.3 + v * 0.5) + ')';
    if (v >= 0.3) return 'rgba(37,99,235,' + (0.1 + v * 0.3) + ')';
    if (v >= -0.3) return 'transparent';
    if (v >= -0.7) return 'rgba(239,68,68,' + (0.1 + Math.abs(v) * 0.3) + ')';
    return 'rgba(239,68,68,' + (0.3 + Math.abs(v) * 0.5) + ')';
  }

  let html = '<table class="corr-table"><thead><tr><th></th>';
  for (let j = 0; j < n; j++) {
    html += '<th class="corr-th">' + tickers[j] + '</th>';
  }
  html += '</tr></thead><tbody>';
  for (let i = 0; i < n; i++) {
    html += '<tr><td class="corr-label">' + tickers[i] + '</td>';
    for (let j = 0; j < n; j++) {
      const v = matrix[i][j];
      const bg = i === j ? 'var(--card-bg)' : corrColor(v);
      const text = i === j ? '1' : (v >= 0 ? '+' : '') + v.toFixed(2);
      const fontWeight = Math.abs(v) >= 0.7 && i !== j ? 'font-weight:600' : '';
      html += '<td class="corr-cell" style="background:' + bg + ';' + fontWeight + '">' + text + '</td>';
    }
    html += '</tr>';
  }
  html += '</tbody></table>';
  scopedFind(null, 'riskCorrelationGrid').innerHTML = html;
}
