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
    label: 'Price (EUR)',
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
                   callback: v => v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: c => c.dataset.label + ': ' + fmt(c.parsed.y, 4) + ' EUR',
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
      <td class="${cls(p.unrealized_gain_eur)}">${sign(p.unrealized_gain_eur)} EUR</td>
      <td class="${cls(p.realized_gain_eur || 0)}">${sign(p.realized_gain_eur || 0)} EUR</td>
      <td class="${cls(totalGain)}">${sign(totalGain)} EUR</td>
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
              <span class="pos-stat-label">Current Price</span>
              <span class="pos-stat-value">${currentPrice != null ? fmt(currentPrice, 4) + ' EUR' : '—'}</span>
            </div>
            <div class="pos-stat">
              <span class="pos-stat-label">Avg Cost / Share</span>
              <span class="pos-stat-value">${p.avg_cost_eur > 0 ? fmt(p.avg_cost_eur, 4) + ' EUR' : '—'}</span>
            </div>
            <div class="pos-stat">
              <span class="pos-stat-label">Qty Held</span>
              <span class="pos-stat-value">${fmt(p.quantity, 4)}</span>
            </div>
            <div class="pos-stat">
              <span class="pos-stat-label">Cost Basis</span>
              <span class="pos-stat-value">${fmtEur(p.cost_basis_eur)}</span>
            </div>
            <div class="pos-stat">
              <span class="pos-stat-label">Market Value</span>
              <span class="pos-stat-value">${fmtEur(p.market_value_eur)}</span>
            </div>
            <div class="pos-stat">
              <span class="pos-stat-label">Unrealized P&L</span>
              <span class="pos-stat-value ${cls(p.unrealized_gain_eur)}">${sign(p.unrealized_gain_eur)} EUR (${sign(p.unrealized_gain_pct)}%)</span>
            </div>
            <div class="pos-stat">
              <span class="pos-stat-label">Realized P&L</span>
              <span class="pos-stat-value ${cls(p.realized_gain_eur || 0)}">${sign(p.realized_gain_eur || 0)} EUR</span>
            </div>
            <div class="pos-stat">
              <span class="pos-stat-label">Total P&L</span>
              <span class="pos-stat-value ${cls(totalGain)}">${sign(totalGain)} EUR</span>
            </div>
            <div class="pos-stat">
              <span class="pos-stat-label">2yr Price Change</span>
              <span class="pos-stat-value ${priceChange != null ? cls(priceChange) : ''}">${priceChange != null ? sign(priceChange) + '%' : '—'}</span>
            </div>
            <div class="pos-stat">
              <span class="pos-stat-label">Portfolio Weight</span>
              <span class="pos-stat-value">${fmt(p.weight_pct, 1)}%</span>
            </div>
          </div>
          <div class="pos-chart-wrap">
            <canvas id="pos-chart-${idx}" height="140"></canvas>
          </div>
          </div>
        </div>
      </td>
    </tr>`;

    return row + detail;
  }).join('');

  pt.innerHTML = '<thead><tr>'
    + '<th>Ticker</th>'
    + '<th>Qty</th>'
    + '<th>Avg Cost</th>'
    + '<th>Cost Basis</th>'
    + '<th>Market Value</th>'
    + '<th>Unrealized</th>'
    + '<th>Realized</th>'
    + '<th>Total P&L</th>'
    + '<th>Weight</th>'
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
    + '<th>Ticker</th>'
    + '<th>Cost Basis</th>'
    + '<th>Proceeds</th>'
    + '<th>Realized P&L</th>'
    + '<th>Return %</th>'
    + '</tr></thead><tbody>'
    + closed.map(p =>
      `<tr>`
      + `<td><strong>${p.ticker}</strong></td>`
      + `<td>${fmtEur(p.total_cost_eur)}</td>`
      + `<td>${fmtEur(p.total_proceeds_eur)}</td>`
      + `<td class="${cls(p.realized_gain_eur)}">${sign(p.realized_gain_eur)} EUR</td>`
      + `<td class="${cls(p.realized_gain_pct)}">${sign(p.realized_gain_pct)}%</td>`
      + `</tr>`
    ).join('')
    + '</tbody>';

  makeSortable(ct);
}
