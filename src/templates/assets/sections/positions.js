// --- Allocation chart ---
let _allocationChart = null;
const _ALLOC_COLORS = [
  '#6366f1','#34d399','#f59e0b','#f87171','#a78bfa',
  '#38bdf8','#fb923c','#4ade80','#e879f9','#fbbf24',
  '#22d3ee','#c084fc','#f472b6','#2dd4bf','#818cf8',
];

function updateAllocation() {
  const positions = getActivePositions();
  const section = document.getElementById('allocationSection');
  if (positions.length === 0) { section.style.display = 'none'; return; }
  section.style.display = '';

  // Sort by market value descending, group small (<2%) into "Other"
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

  // Build chart
  if (_allocationChart) { _allocationChart.destroy(); _allocationChart = null; }
  const canvas = document.getElementById('allocationChart');
  _allocationChart = new Chart(canvas.getContext('2d'), {
    type: 'doughnut',
    data: {
      labels: items.map(i => i.ticker),
      datasets: [{
        data: items.map(i => i.value),
        backgroundColor: items.map((_, i) => _ALLOC_COLORS[i % _ALLOC_COLORS.length]),
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

  // Build legend
  const legend = document.getElementById('allocationLegend');
  legend.innerHTML = items.map((item, i) =>
    `<div class="alloc-item">`
    + `<span class="alloc-dot" style="background:${_ALLOC_COLORS[i % _ALLOC_COLORS.length]}"></span>`
    + `<span>${item.ticker}</span>`
    + `<span class="alloc-pct">${fmt(item.pct, 1)}%</span>`
    + `</div>`
  ).join('');
}

// --- Currency exposure chart ---
let _currencyChart = null;
const _CURRENCY_COLORS = ['#6366f1','#f59e0b','#34d399','#f87171','#a78bfa','#38bdf8','#fb923c'];

function updateCurrencyExposure() {
  const section = document.getElementById('currencySection');
  const data = D.currency_exposure;
  if (!data || data.length === 0) { section.style.display = 'none'; return; }
  section.style.display = '';

  if (_currencyChart) { _currencyChart.destroy(); _currencyChart = null; }
  const canvas = document.getElementById('currencyChart');

  _currencyChart = new Chart(canvas.getContext('2d'), {
    type: 'doughnut',
    data: {
      labels: data.map(d => d.currency),
      datasets: [{
        data: data.map(d => d.value_eur),
        backgroundColor: data.map((_, i) => _CURRENCY_COLORS[i % _CURRENCY_COLORS.length]),
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

  const legend = document.getElementById('currencyLegend');
  legend.innerHTML = data.map((d, i) =>
    `<div class="alloc-item">`
    + `<span class="alloc-dot" style="background:${_CURRENCY_COLORS[i % _CURRENCY_COLORS.length]}"></span>`
    + `<span>${d.currency}</span>`
    + `<span class="alloc-pct">${fmt(d.pct, 1)}%</span>`
    + `</div>`
  ).join('');
}

// --- Cost basis lots ---
function _getLotsForTicker(ticker) {
  if (isDefaultSelection()) return (D.position_lots || {})[ticker] || [];
  let lots = [];
  activeClasses.forEach(ac => {
    const pcLots = ((perClass[ac] || {}).position_lots || {})[ticker];
    if (pcLots) lots = lots.concat(pcLots);
  });
  return lots;
}

function _renderLots(ticker, currentPrice) {
  const lots = _getLotsForTicker(ticker);
  if (lots.length === 0) return '';
  return `<div class="pos-lots">
    <div class="pos-lots-title">${t('pos.lots_title')}</div>
    <table class="pos-lots-table">
      <thead><tr><th>${t('pos.lots.date')}</th><th>${t('pos.qty')}</th><th>${t('pos.lots.cost_share')}</th><th>${t('pos.lots.cost')}</th><th>${t('pos.lots.pl')}</th></tr></thead>
      <tbody>${lots.map(l => {
        const cost = l.qty * l.cost_eur;
        const mv = currentPrice != null ? l.qty * currentPrice : null;
        const pl = mv != null ? mv - cost : null;
        return `<tr>
          <td>${l.date}</td>
          <td>${fmt(l.qty, 4)}</td>
          <td>${fmt(l.cost_eur, 4)} ${_currency}</td>
          <td>${fmtCcy(cost)}</td>
          <td class="${pl != null ? cls(pl) : ''}">${pl != null ? sign(pl) + ' ' + _currency : '—'}</td>
        </tr>`;
      }).join('')}</tbody>
    </table>
  </div>`;
}

// --- Diversification metrics ---
function updateConcentration() {
  const positions = getActivePositions();
  const section = document.getElementById('concentrationSection');
  if (positions.length < 3) { section.style.display = 'none'; return; }
  section.style.display = '';

  const totalMV = positions.reduce((s, p) => s + p.market_value_eur, 0) || 1;
  const weights = positions.map(p => p.market_value_eur / totalMV);

  // HHI: sum of squared weights (0-10000 scale)
  const hhi = Math.round(weights.reduce((s, w) => s + w * w, 0) * 10000);
  const hhiLabel = hhi < 1500 ? t('concentration.well_diversified') : hhi < 2500 ? t('concentration.moderate') : t('concentration.concentrated');

  // Top 5 concentration
  const sorted = [...weights].sort((a, b) => b - a);
  const top5Pct = sorted.slice(0, 5).reduce((s, w) => s + w, 0) * 100;
  const top10Pct = sorted.slice(0, 10).reduce((s, w) => s + w, 0) * 100;

  // Effective number of positions (1/HHI normalized)
  const effective = weights.reduce((s, w) => s + w * w, 0);
  const effectiveN = effective > 0 ? Math.round(1 / effective) : positions.length;

  // Largest position
  const largest = positions.length > 0
    ? positions.reduce((a, b) => a.market_value_eur > b.market_value_eur ? a : b)
    : null;
  const largestPct = largest ? (largest.market_value_eur / totalMV * 100) : 0;

  const el = document.getElementById('concentrationCards');
  el.innerHTML = [
    [t('concentration.positions'), positions.length, ''],
    [t('concentration.effective'), effectiveN, '', t('concentration.effective_sub')],
    [t('concentration.hhi'), hhi.toLocaleString(_locale), '', hhiLabel],
    [t('concentration.top5'), fmt(top5Pct, 1) + '%', ''],
    [t('concentration.top10'), fmt(top10Pct, 1) + '%', ''],
    [t('concentration.largest'), largest ? largest.ticker : '—', '', largest ? fmt(largestPct, 1) + '% ' + t('alloc.of_portfolio') : ''],
  ].map(([l, v, c, sub]) =>
    `<div class="metric-card"><div class="label">${l}</div><div class="value ${c || ''}">${v}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`
  ).join('');
}

// --- Positions table ---
const _posCharts = {};  // ticker -> Chart instance

function _destroyPosChart(ticker) {
  if (_posCharts[ticker]) {
    _posCharts[ticker].destroy();
    delete _posCharts[ticker];
  }
}

function _buildPosChart(ticker, canvasEl, avgCost) {
  _destroyPosChart(ticker);
  const hist = (D.position_price_history || {})[ticker];
  if (!hist || hist.dates.length < 2) {
    canvasEl.parentElement.style.display = 'none';
    return;
  }

  const data = hist.dates.map((d, i) => ({ x: d, y: hist.values[i] }));
  const lastPrice = hist.values[hist.values.length - 1];
  const firstPrice = hist.values[0];
  const isUp = lastPrice >= firstPrice;
  const lineColor = isUp ? '#34d399' : '#f87171';
  const fillColor = isUp ? 'rgba(52,211,153,0.08)' : 'rgba(248,113,113,0.08)';

  const datasets = [{
    label: t('pos.current_price') + ' (' + _currency + ')',
    data,
    borderColor: lineColor,
    backgroundColor: fillColor,
    fill: true,
    tension: 0.2,
    pointRadius: 0,
    borderWidth: 1.5,
  }];

  if (avgCost > 0) {
    datasets.push({
      label: 'Avg Cost',
      data: hist.dates.map(d => ({ x: d, y: avgCost })),
      borderColor: 'rgba(245,158,11,0.6)',
      borderDash: [4, 3],
      borderWidth: 1,
      pointRadius: 0,
      fill: false,
    });
  }

  _posCharts[ticker] = new Chart(canvasEl.getContext('2d'), {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: {
          type: 'time',
          time: { unit: 'month', tooltipFormat: 'yyyy-MM-dd' },
          grid: { display: false },
          ticks: { color: '#556075', font: { size: 10 }, maxTicksLimit: 6 },
        },
        y: {
          position: 'right',
          grid: { color: 'rgba(30,42,58,0.8)' },
          ticks: { color: '#556075', font: { size: 10 }, maxTicksLimit: 5,
                   callback: v => v.toLocaleString(_locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: c => c.dataset.label + ': ' + fmt(c.parsed.y, 4) + ' ' + _currency,
          },
        },
      },
    },
  });
}

function _makePositionsSortable(table, positions) {
  const ths = table.querySelectorAll('th');
  ths.forEach((th, colIdx) => {
    th.innerHTML = th.textContent + ' <span class="arrow"></span>';
    th.style.cursor = 'pointer';
    th.addEventListener('click', () => {
      const tbody = table.querySelector('tbody');
      if (!tbody) return;
      const dir = th.dataset.dir === 'asc' ? 'desc' : 'asc';
      ths.forEach(h => { h.dataset.dir = ''; h.querySelector('.arrow').textContent = ''; });
      th.dataset.dir = dir;
      th.querySelector('.arrow').textContent = dir === 'asc' ? '▲' : '▼';

      // Collect pairs: [mainRow, detailRow]
      const pairs = [];
      const allRows = Array.from(tbody.rows);
      for (let i = 0; i < allRows.length; i++) {
        if (allRows[i].classList.contains('pos-row')) {
          const detail = allRows[i + 1];
          pairs.push([allRows[i], detail && detail.classList.contains('pos-detail-row') ? detail : null]);
          if (detail && detail.classList.contains('pos-detail-row')) i++;
        }
      }

      pairs.sort(([a], [b]) => {
        const ac = a.cells[colIdx], bc = b.cells[colIdx];
        if (!ac || !bc) return 0;
        let av = ac.textContent.replace(/[^\d.\-]/g, '');
        let bv = bc.textContent.replace(/[^\d.\-]/g, '');
        const an = parseFloat(av), bn = parseFloat(bv);
        if (!isNaN(an) && !isNaN(bn)) return dir === 'asc' ? an - bn : bn - an;
        return dir === 'asc'
          ? ac.textContent.localeCompare(bc.textContent)
          : bc.textContent.localeCompare(ac.textContent);
      });

      pairs.forEach(([main, detail]) => {
        tbody.appendChild(main);
        if (detail) tbody.appendChild(detail);
      });
    });
  });
}

function updateAttribution() {
  const positions = getActivePositions();
  const section = document.getElementById('attributionSection');
  if (positions.length < 2) { section.style.display = 'none'; return; }
  section.style.display = '';

  const s = getActiveSummary();
  const totalInvested = s.total_invested_eur || 1;

  // Compute each position's total P&L contribution
  const items = positions.map(p => {
    const totalPL = p.unrealized_gain_eur + (p.realized_gain_eur || 0);
    const contribution = totalPL / totalInvested * 100;
    return { ...p, totalPL, contribution };
  }).sort((a, b) => b.contribution - a.contribution);

  const at = document.getElementById('attributionTable');
  at.innerHTML = '<thead><tr>'
    + '<th>' + t('pos.ticker') + '</th>'
    + '<th>' + t('pos.weight') + '</th>'
    + '<th>' + t('pos.unrealized') + '</th>'
    + '<th>' + t('pos.realized') + '</th>'
    + '<th>' + t('pos.total_pl') + '</th>'
    + '<th>' + t('attribution.contribution') + '</th>'
    + '</tr></thead><tbody>'
    + items.map(p => {
      const barWidth = Math.min(Math.abs(p.contribution) * 5, 100);
      const barColor = p.contribution >= 0 ? 'rgba(52,211,153,0.4)' : 'rgba(248,113,113,0.4)';
      const barAlign = p.contribution >= 0 ? 'left' : 'right';
      return `<tr>`
        + `<td><strong>${p.ticker}</strong></td>`
        + `<td>${fmt(p.weight_pct, 1)}%</td>`
        + `<td class="${cls(p.unrealized_gain_eur)}">${sign(p.unrealized_gain_eur)} ${_currency}</td>`
        + `<td class="${cls(p.realized_gain_eur || 0)}">${sign(p.realized_gain_eur || 0)} ${_currency}</td>`
        + `<td class="${cls(p.totalPL)}">${sign(p.totalPL)} ${_currency}</td>`
        + `<td class="${cls(p.contribution)}"><div style="position:relative">`
          + `<div style="position:absolute;top:0;${barAlign}:0;height:100%;width:${barWidth}%;background:${barColor};border-radius:2px"></div>`
          + `<span style="position:relative">${sign(p.contribution)}%</span>`
        + `</div></td>`
        + `</tr>`;
    }).join('')
    + '</tbody>';
  makeSortable(at);
}

function updatePositions() {
  const positions = getActivePositions();
  const section = document.getElementById('positionsSection');
  if (positions.length === 0) { section.style.display = 'none'; return; }
  section.style.display = '';

  const pt = document.getElementById('positionsTable');

  // Destroy all existing mini-charts before rebuilding
  Object.keys(_posCharts).forEach(_destroyPosChart);

  const tbody = positions.map((p, idx) => {
    const hasPriceHistory = (D.position_price_history || {})[p.ticker]?.dates?.length > 1;
    const expandable = hasPriceHistory ? 'pos-row-expandable' : '';
    const chevron = hasPriceHistory
      ? `<span class="pos-chevron" data-idx="${idx}">&#x25B6;</span>`
      : `<span class="pos-chevron-placeholder"></span>`;

    const totalGain = p.unrealized_gain_eur + (p.realized_gain_eur || 0);
    const row = `<tr class="pos-row ${expandable}" data-idx="${idx}" data-ticker="${p.ticker}">
      <td><div class="pos-ticker-cell">${chevron}<strong>${p.ticker}</strong></div></td>
      <td>${fmt(p.quantity, 4)}</td>
      <td>${fmtEur(p.avg_cost_eur)}</td>
      <td>${fmtEur(p.cost_basis_eur)}</td>
      <td>${fmtEur(p.market_value_eur)}</td>
      <td class="${cls(p.unrealized_gain_eur)}">${sign(p.unrealized_gain_eur)} ${_currency}</td>
      <td class="${cls(p.realized_gain_eur || 0)}">${sign(p.realized_gain_eur || 0)} ${_currency}</td>
      <td class="${cls(totalGain)}">${sign(totalGain)} ${_currency}</td>
      <td>${fmt(p.weight_pct, 1)}%</td>
    </tr>`;

    const lastHist = (D.position_price_history || {})[p.ticker];
    const currentPrice = lastHist?.values?.[lastHist.values.length - 1] ?? null;
    const firstPrice   = lastHist?.values?.[0] ?? null;
    const priceChange  = currentPrice != null && firstPrice != null && firstPrice > 0
      ? ((currentPrice - firstPrice) / firstPrice * 100) : null;

    const companyName = (D.company_names || {})[p.ticker] || '';
    const detail = `<tr class="pos-detail-row" id="pos-detail-${idx}" style="display:none">
      <td colspan="9">
        <div class="pos-detail">
          ${companyName ? `<div class="pos-detail-name">${companyName}</div>` : ''}
          <div class="pos-detail-body">
          <div class="pos-detail-stats">
            <div class="pos-stat">
              <span class="pos-stat-label">${t('pos.current_price')}</span>
              <span class="pos-stat-value">${currentPrice != null ? fmt(currentPrice, 4) + ' ' + _currency : '—'}</span>
            </div>
            <div class="pos-stat">
              <span class="pos-stat-label">${t('pos.avg_cost_share')}</span>
              <span class="pos-stat-value">${p.avg_cost_eur > 0 ? fmt(p.avg_cost_eur, 4) + ' ' + _currency : '—'}</span>
            </div>
            <div class="pos-stat">
              <span class="pos-stat-label">${t('pos.qty_held')}</span>
              <span class="pos-stat-value">${fmt(p.quantity, 4)}</span>
            </div>
            <div class="pos-stat">
              <span class="pos-stat-label">${t('pos.cost_basis')}</span>
              <span class="pos-stat-value">${fmtCcy(p.cost_basis_eur)}</span>
            </div>
            <div class="pos-stat">
              <span class="pos-stat-label">${t('pos.market_value')}</span>
              <span class="pos-stat-value">${fmtCcy(p.market_value_eur)}</span>
            </div>
            <div class="pos-stat">
              <span class="pos-stat-label">${t('pos.unrealized_pl')}</span>
              <span class="pos-stat-value ${cls(p.unrealized_gain_eur)}">${sign(p.unrealized_gain_eur)} ${_currency} (${sign(p.unrealized_gain_pct)}%)</span>
            </div>
            <div class="pos-stat">
              <span class="pos-stat-label">${t('pos.realized_pl')}</span>
              <span class="pos-stat-value ${cls(p.realized_gain_eur || 0)}">${sign(p.realized_gain_eur || 0)} ${_currency}</span>
            </div>
            <div class="pos-stat">
              <span class="pos-stat-label">${t('pos.total_pl')}</span>
              <span class="pos-stat-value ${cls(totalGain)}">${sign(totalGain)} ${_currency}</span>
            </div>
            <div class="pos-stat">
              <span class="pos-stat-label">${t('pos.price_change_2yr')}</span>
              <span class="pos-stat-value ${priceChange != null ? cls(priceChange) : ''}">${priceChange != null ? sign(priceChange) + '%' : '—'}</span>
            </div>
            <div class="pos-stat">
              <span class="pos-stat-label">${t('pos.portfolio_weight')}</span>
              <span class="pos-stat-value">${fmt(p.weight_pct, 1)}%</span>
            </div>
          </div>
          <div class="pos-chart-wrap">
            <canvas id="pos-chart-${idx}" height="140"></canvas>
          </div>
          </div>
          ${_renderLots(p.ticker, currentPrice)}
        </div>
      </td>
    </tr>`;

    return row + detail;
  }).join('');

  pt.innerHTML = '<thead><tr>'
    + '<th>' + t('pos.ticker') + '</th>'
    + '<th>' + t('pos.qty') + '</th>'
    + '<th>' + t('pos.avg_cost') + '</th>'
    + '<th>' + t('pos.cost_basis') + '</th>'
    + '<th>' + t('pos.market_value') + '</th>'
    + '<th>' + t('pos.unrealized') + '</th>'
    + '<th>' + t('pos.realized') + '</th>'
    + '<th>' + t('pos.total_pl') + '</th>'
    + '<th>' + t('pos.weight') + '</th>'
    + '</tr></thead><tbody>' + tbody + '</tbody>';

  // Custom sortable that keeps detail rows paired with their parent rows
  _makePositionsSortable(pt, positions);

  // Attach expand/collapse handlers
  pt.querySelectorAll('.pos-row-expandable').forEach(row => {
    row.addEventListener('click', () => {
      const idx = row.dataset.idx;
      const ticker = row.dataset.ticker;
      const detailRow = document.getElementById('pos-detail-' + idx);
      const chevron = row.querySelector('.pos-chevron');
      const isOpen = detailRow.style.display !== 'none';

      if (isOpen) {
        detailRow.style.display = 'none';
        chevron.classList.remove('pos-chevron-open');
        _destroyPosChart(ticker);
      } else {
        detailRow.style.display = '';
        chevron.classList.add('pos-chevron-open');
        const canvas = document.getElementById('pos-chart-' + idx);
        if (canvas) {
          const p = positions.find(x => x.ticker === ticker);
          _buildPosChart(ticker, canvas, p ? p.avg_cost_eur : 0);
        }
      }
    });
  });
}

function updateClosedPositions() {
  const closed = getActiveClosedPositions();
  const section = document.getElementById('closedPositionsSection');
  if (closed.length === 0) { section.style.display = 'none'; return; }
  section.style.display = '';

  const ct = document.getElementById('closedPositionsTable');
  ct.innerHTML = '<thead><tr>'
    + '<th>' + t('pos.ticker') + '</th>'
    + '<th>' + t('pos.cost_basis') + '</th>'
    + '<th>' + t('closed.proceeds') + '</th>'
    + '<th>' + t('pos.realized_pl') + '</th>'
    + '<th>' + t('closed.return_pct') + '</th>'
    + '</tr></thead><tbody>'
    + closed.map(p =>
      `<tr>`
      + `<td><strong>${p.ticker}</strong></td>`
      + `<td>${fmtCcy(p.total_cost_eur)}</td>`
      + `<td>${fmtCcy(p.total_proceeds_eur)}</td>`
      + `<td class="${cls(p.realized_gain_eur)}">${sign(p.realized_gain_eur)} ${_currency}</td>`
      + `<td class="${cls(p.realized_gain_pct)}">${sign(p.realized_gain_pct)}%</td>`
      + `</tr>`
    ).join('')
    + '</tbody>';

  makeSortable(ct);
}

// --- Export positions to CSV ---
(function() {
  const btn = document.getElementById('exportPositionsBtn');
  if (!btn) return;
  btn.addEventListener('click', function() {
    const positions = getActivePositions();
    if (positions.length === 0) return;
    const names = D.company_names || {};
    const header = 'Ticker,Company,Quantity,Avg Cost (EUR),Cost Basis (EUR),Market Value (EUR),Unrealized P&L (EUR),Unrealized %,Realized P&L (EUR),Weight %';
    const rows = positions.map(p => {
      const name = (names[p.ticker] || '').replace(/,/g, ' ');
      return [
        p.ticker, name, p.quantity, p.avg_cost_eur,
        p.cost_basis_eur, p.market_value_eur,
        p.unrealized_gain_eur, p.unrealized_gain_pct,
        p.realized_gain_eur || 0, p.weight_pct
      ].join(',');
    });
    const csv = header + '\n' + rows.join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'portfolio_positions_' + D.end_date + '.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
  });

  // --- Correlation matrix ---
  window.updateCorrelation = function() {
    const section = document.getElementById('correlationSection');
    const corr = D.correlation;
    if (!corr || !corr.tickers || corr.tickers.length < 2) {
      if (section) section.style.display = 'none';
      return;
    }
    section.style.display = '';
    document.getElementById('correlationTitle').textContent = t('correlation.title');
    document.getElementById('correlationDesc').textContent =
      t('correlation.desc', {days: corr.data_points});

    const tickers = corr.tickers;
    const matrix = corr.matrix;
    const n = tickers.length;

    // Color scale: -1 = red, 0 = neutral, 1 = blue
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
    document.getElementById('correlationGrid').innerHTML = html;
  };

  // --- Sector allocation ---
  let _sectorChart = null;
  const _SECTOR_COLORS = [
    '#6366f1','#34d399','#f59e0b','#f87171','#a78bfa',
    '#38bdf8','#fb923c','#4ade80','#e879f9','#fbbf24',
    '#22d3ee','#c084fc','#f472b6','#2dd4bf','#818cf8',
  ];

  window.updateSectorAllocation = function() {
    const sa = D.sector_allocation;
    const row = document.getElementById('sectorRow');
    if (!sa || !sa.sectors || sa.sectors.length === 0) {
      if (row) row.style.display = 'none';
      return;
    }

    // Filter out "Other" if it's the only sector
    const sectors = sa.sectors.filter(s => s.pct > 0);
    if (sectors.length === 0 || (sectors.length === 1 && sectors[0].name === 'Other')) {
      if (row) row.style.display = 'none';
      return;
    }
    row.style.display = '';

    document.getElementById('sectorTitle').textContent = t('sector.title');
    document.getElementById('industryTitle').textContent = t('sector.industry_title');

    // Sector donut chart
    if (_sectorChart) { _sectorChart.destroy(); _sectorChart = null; }
    const canvas = document.getElementById('sectorChart');
    _sectorChart = new Chart(canvas.getContext('2d'), {
      type: 'doughnut',
      data: {
        labels: sectors.map(s => s.name),
        datasets: [{
          data: sectors.map(s => s.value_eur),
          backgroundColor: sectors.map((_, i) => _SECTOR_COLORS[i % _SECTOR_COLORS.length]),
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
              label: function(c) { return c.label + ': ' + fmtCcy(c.parsed) + ' (' + fmt(sectors[c.dataIndex].pct, 1) + '%)'; },
            },
          },
        },
      },
    });

    // Sector legend
    const legend = document.getElementById('sectorLegend');
    legend.innerHTML = sectors.map((s, i) =>
      `<div class="alloc-item">`
      + `<span class="alloc-dot" style="background:${_SECTOR_COLORS[i % _SECTOR_COLORS.length]}"></span>`
      + `<span>${s.name}</span>`
      + `<span class="alloc-pct">${fmt(s.pct, 1)}%</span>`
      + `</div>`
    ).join('');

    // Industry table
    const industries = (sa.industries || []).filter(i => i.pct > 0);
    const it = document.getElementById('industryTable');
    if (industries.length > 0) {
      it.innerHTML =
        '<thead><tr><th>'+t('sector.col.industry')+'</th><th>'+t('sector.col.value')+'</th><th>'+t('sector.col.pct')+'</th></tr></thead><tbody>' +
        industries.map(function(ind, i) {
          return `<tr>` +
            `<td><span class="alloc-dot" style="background:${_SECTOR_COLORS[i % _SECTOR_COLORS.length]};display:inline-block;vertical-align:middle;margin-right:0.3rem"></span>${ind.name}</td>` +
            `<td>${fmtCcy(ind.value_eur)}</td>` +
            `<td>${fmt(ind.pct, 1)}%</td>` +
            `</tr>`;
        }).join('') +
        '</tbody>';
      makeSortable(it);
    }
  };
})();
