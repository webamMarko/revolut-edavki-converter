// --- Risk page rendering ---
let _geoChart = null;
let _riskSectorChart = null;

const _GEO_COLORS = [
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
  updateRiskMetrics();
  updateGeoAllocation();
  updateRiskSector();
  updateRiskCorrelation();
  _initRiskToggle('riskMetricsToggle', 'riskMetricsToggleLabel', 'riskMetricsPanel', 'Show more metrics', 'Hide extra metrics');
  _initRiskToggle('riskGeoToggle', 'riskGeoToggleLabel', 'riskGeoPanel', 'Show geographic exposure', 'Hide geographic exposure');
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

function updateRiskMetrics() {
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

function updateGeoAllocation() {
  const row = scopedFind(null, 'riskGeoRow');
  const toggleWrap = scopedFind(null, 'riskGeoToggleWrap');
  const ga = D.geographic_allocation;
  if (!ga || !ga.countries || ga.countries.length === 0) {
    row.style.display = 'none';
    toggleWrap.style.display = 'none';
    return;
  }

  const countries = ga.countries.filter(c => c.pct > 0);
  if (countries.length === 0 || (countries.length === 1 && countries[0].name === 'Other')) {
    row.style.display = 'none';
    toggleWrap.style.display = 'none';
    return;
  }
  row.style.display = '';
  toggleWrap.style.display = '';

  // Geo donut chart
  if (_geoChart) { _geoChart.destroy(); _geoChart = null; }
  const canvas = scopedFind(null, 'geoChart');
  _geoChart = new Chart(canvas.getContext('2d'), {
    type: 'doughnut',
    data: {
      labels: countries.map(c => c.name),
      datasets: [{
        data: countries.map(c => c.value_eur),
        backgroundColor: countries.map((_, i) => _GEO_COLORS[i % _GEO_COLORS.length]),
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

  // Legend
  const legend = scopedFind(null, 'geoLegend');
  legend.innerHTML = countries.map((c, i) =>
    `<div class="alloc-item">`
    + `<span class="alloc-dot" style="background:${_GEO_COLORS[i % _GEO_COLORS.length]}"></span>`
    + `<span>${c.name}</span>`
    + `<span class="alloc-pct">${fmt(c.pct, 1)}%</span>`
    + `</div>`
  ).join('');

  // Country table
  const table = scopedFind(null, 'geoTable');
  table.innerHTML = '<thead><tr><th>Country</th><th>Value</th><th>Weight</th></tr></thead><tbody>'
    + countries.map(c =>
      `<tr><td>${c.name}</td><td>${fmtCcy(c.value_eur)}</td><td>${fmt(c.pct, 1)}%</td></tr>`
    ).join('')
    + '</tbody>';
  makeSortable(table);
}

function updateRiskSector() {
  const row = scopedFind(null, 'riskSectorRow');
  const sa = D.sector_allocation;
  if (!sa || !sa.sectors || sa.sectors.length === 0) {
    row.style.display = 'none';
    return;
  }

  const sectors = sa.sectors.filter(s => s.pct > 0);
  if (sectors.length === 0 || (sectors.length === 1 && sectors[0].name === 'Other')) {
    row.style.display = 'none';
    return;
  }
  row.style.display = '';

  // Sector donut chart (for risk page)
  if (_riskSectorChart) { _riskSectorChart.destroy(); _riskSectorChart = null; }
  const canvas = scopedFind(null, 'riskSectorChart');
  _riskSectorChart = new Chart(canvas.getContext('2d'), {
    type: 'doughnut',
    data: {
      labels: sectors.map(s => s.name),
      datasets: [{
        data: sectors.map(s => s.value_eur),
        backgroundColor: sectors.map((_, i) => _GEO_COLORS[i % _GEO_COLORS.length]),
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

  // Legend
  const legend = scopedFind(null, 'riskSectorLegend');
  legend.innerHTML = sectors.map((s, i) =>
    `<div class="alloc-item">`
    + `<span class="alloc-dot" style="background:${_GEO_COLORS[i % _GEO_COLORS.length]}"></span>`
    + `<span>${s.name}</span>`
    + `<span class="alloc-pct">${fmt(s.pct, 1)}%</span>`
    + `</div>`
  ).join('');

  // Industry table
  const industries = (sa.industries || []).filter(i => i.pct > 0);
  const table = scopedFind(null, 'riskIndustryTable');
  table.innerHTML = '<thead><tr><th>Industry</th><th>Value</th><th>Weight</th></tr></thead><tbody>'
    + industries.map(ind =>
      `<tr><td>${ind.name}</td><td>${fmtCcy(ind.value_eur)}</td><td>${fmt(ind.pct, 1)}%</td></tr>`
    ).join('')
    + '</tbody>';
  makeSortable(table);
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
