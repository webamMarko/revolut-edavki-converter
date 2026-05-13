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
          <td>${fmt(l.cost_eur * _fx, 4)} ${_currency}</td>
          <td>${fmtCcy(cost)}</td>
          <td class="${pl != null ? cls(pl) : ''}">${pl != null ? signCcy(pl) : '—'}</td>
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

// --- Bracket progress helpers ---
const _MS_PER_DAY = 1000 * 60 * 60 * 24;

function _getAssetClassForTicker(ticker) {
  if (ticker.startsWith('CFD:')) return 'cfd';
  if (ticker.startsWith('CRYPTO:')) return 'crypto';
  if (ticker.startsWith('SAVINGS:')) return 'savings';
  return 'stock';
}

function _getBracketsForTicker(ticker) {
  const regime = D.regime || {};
  const ac = _getAssetClassForTicker(ticker);
  if (ac === 'cfd') return regime.cfd_brackets || [];
  if (ac === 'crypto') return regime.crypto_brackets || [];
  if (ac === 'savings') return regime.savings_brackets || [];
  return regime.stock_brackets || [];
}

function _renderBracketProgress(ticker) {
  const brackets = _getBracketsForTicker(ticker);
  if (!brackets || brackets.length <= 1) return '';

  const lots = _getLotsForTicker(ticker);
  if (lots.length === 0) return '';

  // Use oldest lot date to represent the position's holding period
  const today = new Date();
  let oldestDate = null;
  for (let i = 0; i < lots.length; i++) {
    const d = new Date(lots[i].date);
    if (!oldestDate || d < oldestDate) oldestDate = d;
  }
  if (!oldestDate) return '';

  const holdingDays = Math.floor((today - oldestDate) / _MS_PER_DAY);
  const holdingYears = holdingDays / 365.25;

  // Find current and next bracket
  let currentRate = brackets[0].rate;
  for (let i = 0; i < brackets.length; i++) {
    if (holdingYears >= brackets[i].min_years) currentRate = brackets[i].rate;
  }

  let nextBracket = null;
  for (let i = 0; i < brackets.length; i++) {
    if (brackets[i].min_years > holdingYears) { nextBracket = brackets[i]; break; }
  }

  // At final bracket (0% or last step)
  if (!nextBracket) {
    return `<div class="bracket-bar-wrap"><span class="bracket-bar-checkmark">&#x2714;</span> <span class="bracket-bar-label">${t('pos.at_max_bracket')}</span></div>`;
  }

  // Compute progress between prev bracket threshold and next bracket threshold
  let prevMin = 0;
  for (let i = 0; i < brackets.length; i++) {
    if (brackets[i].min_years <= holdingYears) prevMin = brackets[i].min_years;
  }
  const rangeYears = nextBracket.min_years - prevMin;
  const progressYears = holdingYears - prevMin;
  const pct = rangeYears > 0 ? Math.min(100, Math.round(progressYears / rangeYears * 100)) : 100;

  const daysToNext = Math.ceil((nextBracket.min_years * 365.25) - holdingDays);
  const targetDate = new Date(oldestDate.getTime() + nextBracket.min_years * 365.25 * _MS_PER_DAY);
  const targetStr = targetDate.toISOString().slice(0, 10);

  const colorClass = daysToNext <= 30 ? 'bracket-green' : daysToNext <= 90 ? 'bracket-amber' : 'bracket-grey';
  const rateLabel = Math.round(nextBracket.rate * 100) + '%';

  return `<div class="bracket-bar-wrap">`
    + `<div class="bracket-bar-track"><div class="bracket-bar-fill ${colorClass}" style="width:${pct}%"></div></div>`
    + `<div class="bracket-bar-label">${pct}% → ${rateLabel} · ${targetStr}</div>`
    + `</div>`;
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
                   callback: v => (v * _fx).toLocaleString(_locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: c => c.dataset.label + ': ' + fmt(c.parsed.y * _fx, 4) + ' ' + _currency,
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
        + `<td class="${cls(p.unrealized_gain_eur)}">${signCcy(p.unrealized_gain_eur)}</td>`
        + `<td class="${cls(p.realized_gain_eur || 0)}">${signCcy(p.realized_gain_eur || 0)}</td>`
        + `<td class="${cls(p.totalPL)}">${signCcy(p.totalPL)}</td>`
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
      <td class="${cls(p.unrealized_gain_eur)}">${signCcy(p.unrealized_gain_eur)}</td>
      <td class="${cls(p.realized_gain_eur || 0)}">${signCcy(p.realized_gain_eur || 0)}</td>
      <td class="${cls(totalGain)}">${signCcy(totalGain)}</td>
      <td>${fmt(p.weight_pct, 1)}%</td>
      <td>${_renderBracketProgress(p.ticker)}</td>
    </tr>`;

    const lastHist = (D.position_price_history || {})[p.ticker];
    const currentPrice = lastHist?.values?.[lastHist.values.length - 1] ?? null;
    const firstPrice   = lastHist?.values?.[0] ?? null;
    const priceChange  = currentPrice != null && firstPrice != null && firstPrice > 0
      ? ((currentPrice - firstPrice) / firstPrice * 100) : null;

    const companyName = (D.company_names || {})[p.ticker] || '';
    const detail = `<tr class="pos-detail-row" id="pos-detail-${idx}" style="display:none">
      <td colspan="10">
        <div class="pos-detail">
          ${companyName ? `<div class="pos-detail-name">${companyName}</div>` : ''}
          <div class="pos-detail-body">
          <div class="pos-detail-stats">
            <div class="pos-stat">
              <span class="pos-stat-label">${t('pos.current_price')}</span>
              <span class="pos-stat-value">${currentPrice != null ? fmt(currentPrice * _fx, 4) + ' ' + _currency : '—'}</span>
            </div>
            <div class="pos-stat">
              <span class="pos-stat-label">${t('pos.avg_cost_share')}</span>
              <span class="pos-stat-value">${p.avg_cost_eur > 0 ? fmt(p.avg_cost_eur * _fx, 4) + ' ' + _currency : '—'}</span>
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
              <span class="pos-stat-value ${cls(p.unrealized_gain_eur)}">${signCcy(p.unrealized_gain_eur)} (${sign(p.unrealized_gain_pct)}%)</span>
            </div>
            <div class="pos-stat">
              <span class="pos-stat-label">${t('pos.realized_pl')}</span>
              <span class="pos-stat-value ${cls(p.realized_gain_eur || 0)}">${signCcy(p.realized_gain_eur || 0)}</span>
            </div>
            <div class="pos-stat">
              <span class="pos-stat-label">${t('pos.total_pl')}</span>
              <span class="pos-stat-value ${cls(totalGain)}">${signCcy(totalGain)}</span>
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
    + '<th>' + t('pos.next_bracket') + '</th>'
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
      + `<td class="${cls(p.realized_gain_eur)}">${signCcy(p.realized_gain_eur)}</td>`
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
    const header = 'Ticker,Company,Quantity,Avg Cost ('+_currency+'),Cost Basis ('+_currency+'),Market Value ('+_currency+'),Unrealized P&L ('+_currency+'),Unrealized %,Realized P&L ('+_currency+'),Weight %';
    const rows = positions.map(p => {
      const name = (names[p.ticker] || '').replace(/,/g, ' ');
      return [
        p.ticker, name, p.quantity,
        +(p.avg_cost_eur * _fx).toFixed(4),
        +(p.cost_basis_eur * _fx).toFixed(2),
        +(p.market_value_eur * _fx).toFixed(2),
        +(p.unrealized_gain_eur * _fx).toFixed(2),
        p.unrealized_gain_pct,
        +((p.realized_gain_eur || 0) * _fx).toFixed(2),
        p.weight_pct
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

  // --- What-if simulator ---
  let _simChart = null;
  const _simAdjustments = {};

  document.getElementById('simulateBtn').textContent = t('sim.simulate');
  document.getElementById('simResetBtn').textContent = t('sim.reset');
  document.getElementById('simCloseBtn').textContent = t('sim.close');
  var _simTaxEfficient = true;
  document.getElementById('simulateBtn').addEventListener('click', function() {
    var section = document.getElementById('simulatorSection');
    section.style.display = section.style.display === 'none' ? '' : 'none';
    if (section.style.display !== 'none') _renderSimulator();
  });
  document.getElementById('simCloseBtn').addEventListener('click', function() {
    document.getElementById('simulatorSection').style.display = 'none';
  });
  document.getElementById('simResetBtn').addEventListener('click', function() {
    for (var k in _simAdjustments) delete _simAdjustments[k];
    _renderSimulator();
  });
  var taxEffToggle = document.getElementById('simTaxEfficientToggle');
  if (taxEffToggle) {
    taxEffToggle.checked = _simTaxEfficient;
    document.getElementById('simTaxEfficientLabel').textContent = t('sim.tax_efficient');
    taxEffToggle.addEventListener('change', function() {
      _simTaxEfficient = this.checked;
      _renderSimulator();
    });
  }

  // Estimate tax for a hypothetical sale of `saleAmountEur` from `ticker`.
  // When _simTaxEfficient is true, uses oldest-first (FIFO); otherwise newest-first (LIFO).
  function _estimateSaleTax(ticker, saleAmountEur) {
    if (saleAmountEur <= 0) return null;
    var ac = ticker.startsWith('CFD:') ? 'cfd' : ticker.startsWith('CRYPTO:') ? 'crypto' : ticker.startsWith('SAVINGS:') ? 'savings' : 'stock';
    var regime = D.regime || {};
    var brackets = ac === 'cfd' ? (regime.cfd_brackets || []) : ac === 'crypto' ? (regime.crypto_brackets || []) : ac === 'savings' ? (regime.savings_brackets || []) : (regime.stock_brackets || []);
    var pos = getActivePositions().find(function(p) { return p.ticker === ticker; });
    if (!pos || pos.quantity <= 0 || pos.market_value_eur <= 0) return null;
    var pricePerShare = pos.market_value_eur / pos.quantity;
    var sharesToSell = saleAmountEur / pricePerShare;
    var allLots = _getLotsForTicker(ticker);
    if (allLots.length === 0) return null;
    // oldest-first = FIFO = tax-efficient (long holders pay less); newest-first = LIFO
    var lots = _simTaxEfficient ? allLots.slice() : allLots.slice().reverse();
    var today = new Date();
    var MS_PER_DAY = 1000 * 60 * 60 * 24;
    var remaining = Math.min(sharesToSell, pos.quantity);
    var totalGain = 0;
    var totalTax = 0;
    var stdCostRate = ac === 'cfd' ? (regime.std_cost_rate_leveraged || 0.0025) : (regime.std_cost_rate || 0.01);
    for (var i = 0; i < lots.length && remaining > 0; i++) {
      var lot = lots[i];
      var matched = Math.min(lot.qty, remaining);
      var holdingDays = Math.floor((today - new Date(lot.date)) / MS_PER_DAY);
      var holdingYears = holdingDays / 365.25;
      var rate = brackets.length === 0 ? 0.25 : brackets[0].rate;
      for (var j = 0; j < brackets.length; j++) {
        if (holdingYears >= brackets[j].min_years) rate = brackets[j].rate;
      }
      var cost = matched * lot.cost_eur;
      var proceeds = matched * pricePerShare;
      var gain = proceeds - cost;
      var stdCosts = gain > 0 ? stdCostRate * (cost + proceeds) : 0;
      var taxableGain = gain > 0 ? Math.max(0, gain - stdCosts) : gain;
      totalGain += gain;
      totalTax += Math.max(0, taxableGain * rate);
      remaining -= matched;
    }
    return { tax: totalTax, effectiveRate: totalGain > 0 ? (totalTax / totalGain * 100) : 0 };
  }

  function _renderSimulator() {
    var positions = getActivePositions();
    if (positions.length === 0) return;

    document.getElementById('simTitle').textContent = t('sim.title');
    document.getElementById('simDesc').textContent = t('sim.desc');
    document.getElementById('simAllocTitle').textContent = t('sim.alloc_title');

    var sorted = positions.slice().sort(function(a, b) { return b.market_value_eur - a.market_value_eur; });
    var totalCurrent = sorted.reduce(function(s, p) { return s + p.market_value_eur; }, 0);
    var totalAdj = sorted.reduce(function(s, p) { return s + p.market_value_eur + (_simAdjustments[p.ticker] || 0); }, 0);
    var totalChange = totalAdj - totalCurrent;

    // Compute per-ticker tax estimates for all sell adjustments
    var taxByTicker = {};
    var totalEstTax = 0;
    for (var ti = 0; ti < sorted.length; ti++) {
      var tp = sorted[ti];
      var tadj = _simAdjustments[tp.ticker] || 0;
      if (tadj < 0) {
        var est = _estimateSaleTax(tp.ticker, -tadj);
        taxByTicker[tp.ticker] = est;
        if (est) totalEstTax += est.tax;
      }
    }
    var hasSales = Object.keys(taxByTicker).length > 0;

    document.getElementById('simCards').innerHTML = [
      [t('sim.current_value'), fmtCcy(totalCurrent), ''],
      [t('sim.simulated_value'), fmtCcy(totalAdj), ''],
      [t('sim.change'), signCcy(totalChange), cls(totalChange)],
      hasSales ? [t('sim.total_tax'), fmtCcy(totalEstTax), totalEstTax > 0 ? 'neg' : ''] : null,
    ].filter(Boolean).map(function(row) {
      return '<div class="metric-card"><div class="label">' + row[0] + '</div><div class="value ' + row[2] + '">' + row[1] + '</div></div>';
    }).join('');

    // Table with input fields + tax columns
    var html = '<thead><tr><th>' + t('pos.ticker') + '</th><th>' + t('pos.market_value') + '</th><th>' + t('sim.adjust') + ' (' + _currency + ')</th><th>' + t('sim.new_weight') + '</th><th>' + t('sim.col.tax') + '</th><th>' + t('sim.col.rate') + '</th></tr></thead><tbody>';
    for (var i = 0; i < sorted.length; i++) {
      var p = sorted[i];
      var adj = _simAdjustments[p.ticker] || 0;
      var newVal = p.market_value_eur + adj;
      var newWeight = totalAdj > 0 ? (newVal / totalAdj * 100) : 0;
      var taxInfo = taxByTicker[p.ticker] || null;
      var taxCell = taxInfo ? ('<span class="neg">' + fmtCcy(taxInfo.tax) + '</span>') : '—';
      var rateCell = taxInfo && taxInfo.effectiveRate > 0 ? (fmt(taxInfo.effectiveRate, 1) + '%') : '—';
      html += '<tr>'
        + '<td><strong>' + p.ticker + '</strong></td>'
        + '<td>' + fmtCcy(p.market_value_eur) + '</td>'
        + '<td><input type="number" class="sim-input" data-ticker="' + p.ticker + '" value="' + adj + '" step="100" style="width:80px;padding:0.2rem 0.3rem;border:1px solid var(--border);border-radius:4px;background:var(--card-bg);color:var(--text);font-size:0.75rem;text-align:right"></td>'
        + '<td>' + fmt(newWeight, 1) + '%</td>'
        + '<td>' + taxCell + '</td>'
        + '<td>' + rateCell + '</td>'
        + '</tr>';
    }
    if (hasSales) {
      html += '<tr style="border-top:2px solid var(--border);font-weight:600">'
        + '<td colspan="4">' + t('sim.total_tax') + '</td>'
        + '<td class="neg">' + fmtCcy(totalEstTax) + '</td>'
        + '<td>—</td>'
        + '</tr>';
    }
    html += '</tbody>';
    document.getElementById('simTable').innerHTML = html;

    // Attach input handlers
    document.querySelectorAll('.sim-input').forEach(function(input) {
      input.addEventListener('input', function() {
        var ticker = this.getAttribute('data-ticker');
        var val = parseFloat(this.value) || 0;
        _simAdjustments[ticker] = val;
        _updateSimChart(sorted);
        _renderSimulator();
      });
    });

    _updateSimChart(sorted);
  }

  function _updateSimChart(sorted) {
    if (_simChart) { _simChart.destroy(); _simChart = null; }

    var items = [];
    var otherVal = 0;
    var totalAdj = sorted.reduce(function(s, p) { return s + p.market_value_eur + (_simAdjustments[p.ticker] || 0); }, 0) || 1;

    for (var i = 0; i < sorted.length; i++) {
      var p = sorted[i];
      var val = p.market_value_eur + (_simAdjustments[p.ticker] || 0);
      if (val <= 0) continue;
      var pctVal = val / totalAdj * 100;
      if (pctVal >= 2 || items.length < 10) {
        items.push({ticker: p.ticker, value: val, pct: pctVal});
      } else {
        otherVal += val;
      }
    }
    if (otherVal > 0) items.push({ticker: t('alloc.other'), value: otherVal, pct: otherVal / totalAdj * 100});

    var canvas = document.getElementById('simChart');
    _simChart = new Chart(canvas.getContext('2d'), {
      type: 'doughnut',
      data: {
        labels: items.map(function(i) { return i.ticker; }),
        datasets: [{
          data: items.map(function(i) { return i.value; }),
          backgroundColor: items.map(function(_, i) { return _ALLOC_COLORS[i % _ALLOC_COLORS.length]; }),
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
          legend: {display: false},
          tooltip: {callbacks: {label: function(c) { return c.label + ': ' + fmtCcy(c.parsed) + ' (' + fmt(items[c.dataIndex].pct, 1) + '%)'; }}},
        },
      },
    });

    var legend = document.getElementById('simLegend');
    legend.innerHTML = items.map(function(item, i) {
      return '<div class="alloc-item">'
        + '<span class="alloc-dot" style="background:' + _ALLOC_COLORS[i % _ALLOC_COLORS.length] + '"></span>'
        + '<span>' + item.ticker + '</span>'
        + '<span class="alloc-pct">' + fmt(item.pct, 1) + '%</span>'
        + '</div>';
    }).join('');
  }

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
