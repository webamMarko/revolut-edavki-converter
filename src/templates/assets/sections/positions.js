const _ALLOC_COLORS = [
  '#6366f1','#34d399','#f59e0b','#f87171','#a78bfa',
  '#38bdf8','#fb923c','#4ade80','#e879f9','#fbbf24',
  '#22d3ee','#c084fc','#f472b6','#2dd4bf','#818cf8',
];

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

// --- Bracket progress helpers ---
const _MS_PER_DAY = 1000 * 60 * 60 * 24;

function _getAssetClassForTicker(ticker) {
  if (ticker.startsWith('CFD:')) return 'cfd';
  if (ticker.startsWith('CRYPTO:')) return 'crypto';
  if (ticker.startsWith('SAVINGS:')) return 'savings';
  return 'stock';
}

// Strip scope prefix from ticker for API queries (CFD:TSLA → TSLA)
function _rawTickerForApi(ticker) {
  if (ticker.startsWith('CFD:')) return ticker.slice(4);
  if (ticker.startsWith('CRYPTO:')) return ticker.slice(7);
  if (ticker.startsWith('SAVINGS:')) return ticker.slice(8);
  return ticker;
}

function _renderTxPanel(ticker) {
  const isPremium = typeof D !== 'undefined' && D.user && (D.user.role === 'premium' || D.user.role === 'admin');
  const rawTicker = _rawTickerForApi(ticker);
  const ac = _getAssetClassForTicker(ticker);
  const tickerEsc = rawTicker.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
  const addBtn = isPremium
    ? `<button class="tax-export-btn" style="font-size:0.72rem;padding:0.25rem 0.6rem" onclick="openMtxModal('${tickerEsc}','${ac}')">+ Add Transaction</button>`
    : '';
  return `<div class="pos-tx-panel">
    <div class="pos-tx-panel-header">
      <h4>Transaction History</h4>
      ${addBtn}
    </div>
    <div class="pos-tx-content" data-raw-ticker="${rawTicker}">
      <span style="color:var(--muted);font-size:0.8rem">Loading…</span>
    </div>
  </div>`;
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
        const an = _parseSortNum(ac.textContent), bn = _parseSortNum(bc.textContent);
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
  const section = scopedFind(null, 'attributionSection');
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

  const at = scopedFind(null, 'attributionTable');
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
  const section = scopedFind(null, 'positionsSection');
  if (positions.length === 0) { section.style.display = 'none'; return; }
  section.style.display = '';

  const pt = scopedFind(null, 'positionsTable');

  // Destroy all existing mini-charts before rebuilding
  Object.keys(_posCharts).forEach(_destroyPosChart);

  const tbody = positions.map((p, idx) => {
    const hasPriceHistory = (D.position_price_history || {})[p.ticker]?.dates?.length > 1;
    const expandable = 'pos-row-expandable';
    const chevron = `<span class="pos-chevron" data-idx="${idx}">&#x25B6;</span>`;

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
              <span class="pos-stat-label">${t('pos.annualized_return')}</span>
              <span class="pos-stat-value ${p.annualized_return_pct != null ? cls(p.annualized_return_pct) : ''}">${p.annualized_return_pct != null ? sign(p.annualized_return_pct) + '%' : '—'}</span>
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
          ${_renderTxPanel(p.ticker)}
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
  // Use DOM relationships (not getElementById) since the positions section
  // markup is duplicated into the "My Dashboard" widget, which would make
  // pos-detail-/pos-chart- ids non-unique across the document.
  pt.querySelectorAll('.pos-row-expandable').forEach(row => {
    row.addEventListener('click', () => {
      const ticker = row.dataset.ticker;
      const detailRow = row.nextElementSibling;
      const chevron = row.querySelector('.pos-chevron');
      const isOpen = detailRow.style.display !== 'none';

      if (isOpen) {
        detailRow.style.display = 'none';
        chevron.classList.remove('pos-chevron-open');
        _destroyPosChart(ticker);
      } else {
        detailRow.style.display = '';
        chevron.classList.add('pos-chevron-open');
        const canvas = detailRow.querySelector('canvas');
        if (canvas) {
          const p = positions.find(x => x.ticker === ticker);
          _buildPosChart(ticker, canvas, p ? p.avg_cost_eur : 0);
        }
        // Load per-ticker transaction history
        const txContent = detailRow.querySelector('.pos-tx-content');
        if (txContent && window.refreshPosTickerTx) {
          const rawTicker = _rawTickerForApi(ticker);
          refreshPosTickerTx(rawTicker, null, txContent);
        }
      }
    });
  });
}

function updateClosedPositions() {
  const closed = getActiveClosedPositions();
  const section = scopedFind(null, 'closedPositionsSection');
  if (closed.length === 0) { section.style.display = 'none'; return; }
  section.style.display = '';

  const ct = scopedFind(null, 'closedPositionsTable');
  ct.innerHTML = '<thead><tr>'
    + '<th>' + t('pos.ticker') + '</th>'
    + '<th>' + t('pos.cost_basis') + '</th>'
    + '<th>' + t('closed.proceeds') + '</th>'
    + '<th>' + t('pos.realized_pl') + '</th>'
    + '<th>' + t('closed.return_pct') + '</th>'
    + '<th>' + t('closed.annualized') + '</th>'
    + '</tr></thead><tbody>'
    + closed.map(p =>
      `<tr>`
      + `<td><strong>${p.ticker}</strong></td>`
      + `<td>${fmtCcy(p.total_cost_eur)}</td>`
      + `<td>${fmtCcy(p.total_proceeds_eur)}</td>`
      + `<td class="${cls(p.realized_gain_eur)}">${signCcy(p.realized_gain_eur)}</td>`
      + `<td class="${cls(p.realized_gain_pct)}">${sign(p.realized_gain_pct)}%</td>`
      + `<td class="${p.annualized_return_pct != null ? cls(p.annualized_return_pct) : ''}">${p.annualized_return_pct != null ? sign(p.annualized_return_pct) + '%' : '—'}</td>`
      + `</tr>`
    ).join('')
    + '</tbody>';

  makeSortable(ct);
}

function updateTopMovers() {
  const positions = getActivePositions();
  const section = scopedFind(null, 'topMoversSection');
  if (positions.length < 2) { section.style.display = 'none'; return; }
  section.style.display = '';

  const names = D.company_names || {};

  // Sort by unrealized gain % for meaningful ranking
  const sorted = [...positions].filter(p => p.cost_basis_eur > 0);
  const gainers = sorted.filter(p => p.unrealized_gain_eur > 0)
    .sort((a, b) => b.unrealized_gain_pct - a.unrealized_gain_pct).slice(0, 5);
  const losers = sorted.filter(p => p.unrealized_gain_eur < 0)
    .sort((a, b) => a.unrealized_gain_pct - b.unrealized_gain_pct).slice(0, 5);

  function renderList(items, el) {
    if (items.length === 0) { el.innerHTML = '<div style="color:var(--muted);font-size:0.8rem;padding:0.5rem">' + t('movers.none') + '</div>'; return; }
    el.innerHTML = items.map(p => {
      const name = names[p.ticker] || '';
      return `<div class="mover-row">
        <div>
          <div class="mover-ticker">${p.ticker}</div>
          ${name ? `<div class="mover-name">${name}</div>` : ''}
        </div>
        <div class="mover-right">
          <div class="mover-gain ${cls(p.unrealized_gain_eur)}">${signCcy(p.unrealized_gain_eur)}</div>
          <div class="mover-pct">${sign(p.unrealized_gain_pct)}%</div>
        </div>
      </div>`;
    }).join('');
  }

  renderList(gainers, scopedFind(null, 'topGainers'));
  renderList(losers, scopedFind(null, 'topLosers'));
}

// --- Export positions to CSV ---
(function() {
  const btn = scopedFind(null, 'exportPositionsBtn');
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

  scopedFind(null, 'simulateBtn').textContent = t('sim.simulate');
  scopedFind(null, 'simResetBtn').textContent = t('sim.reset');
  scopedFind(null, 'simCloseBtn').textContent = t('sim.close');
  var _simTaxEfficient = true;
  scopedFind(null, 'simulateBtn').addEventListener('click', function() {
    var section = scopedFind(null, 'simulatorSection');
    section.style.display = section.style.display === 'none' ? '' : 'none';
    if (section.style.display !== 'none') _renderSimulator();
  });
  scopedFind(null, 'simCloseBtn').addEventListener('click', function() {
    scopedFind(null, 'simulatorSection').style.display = 'none';
  });
  scopedFind(null, 'simResetBtn').addEventListener('click', function() {
    for (var k in _simAdjustments) delete _simAdjustments[k];
    _renderSimulator();
  });
  var taxEffToggle = scopedFind(null, 'simTaxEfficientToggle');
  if (taxEffToggle) {
    taxEffToggle.checked = _simTaxEfficient;
    scopedFind(null, 'simTaxEfficientLabel').textContent = t('sim.tax_efficient');
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

    scopedFind(null, 'simTitle').textContent = t('sim.title');
    scopedFind(null, 'simDesc').textContent = t('sim.desc');
    scopedFind(null, 'simAllocTitle').textContent = t('sim.alloc_title');

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

    scopedFind(null, 'simCards').innerHTML = [
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
    scopedFind(null, 'simTable').innerHTML = html;

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

    var canvas = scopedFind(null, 'simChart');
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

    var legend = scopedFind(null, 'simLegend');
    legend.innerHTML = items.map(function(item, i) {
      return '<div class="alloc-item">'
        + '<span class="alloc-dot" style="background:' + _ALLOC_COLORS[i % _ALLOC_COLORS.length] + '"></span>'
        + '<span>' + item.ticker + '</span>'
        + '<span class="alloc-pct">' + fmt(item.pct, 1) + '%</span>'
        + '</div>';
    }).join('');
  }

})();
