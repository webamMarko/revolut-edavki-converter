// --- DCA Strategy section ---
let _dcaChart = null;
let _dcaDetailChart = null;

function updateDCAStrategy() {
  const dca = D.dca_strategy;
  const navEl = scopedFind(null, 'navDCA');
  if (!dca || !dca.tickers || dca.tickers.length === 0) {
    if (navEl) navEl.style.display = 'none';
    return;
  }
  if (navEl) navEl.style.display = '';

  const tickers = dca.tickers;
  const totalInvested = tickers.reduce((s, t) => s + t.total_invested_eur, 0);
  const totalValue = tickers.reduce((s, t) => s + t.dca_value_eur, 0);
  const totalReturn = totalValue - totalInvested;
  const totalReturnPct = totalInvested > 0 ? (totalReturn / totalInvested * 100) : 0;
  const avgConsistency = tickers.reduce((s, t) => s + t.consistency_score, 0) / tickers.length;
  const dcaWins = tickers.filter(t => t.lump_sum && t.lump_sum.dca_advantage_pct > 0).length;

  scopedFind(null, 'dcaCards').innerHTML = [
    ['dca.patterns', 'DCA Patterns', tickers.length + ' tickers', ''],
    ['dca.consistency', 'Avg Consistency', fmt(avgConsistency, 0) + '%', avgConsistency >= 70 ? 'positive' : ''],
    ['dca.total_return', 'DCA Return', fmtCcy(totalReturn), totalReturn >= 0 ? 'positive' : 'negative'],
    ['dca.return_pct', 'DCA Return %', fmt(totalReturnPct, 2) + '%', totalReturnPct >= 0 ? 'positive' : 'negative'],
    ['dca.vs_lump', 'DCA Beats Lump Sum', dcaWins + '/' + tickers.length, ''],
  ].map(([key, l, v, c]) => {
    return `<div class="metric-card"><div class="label">${l}</div><div class="value ${c}">${v}</div></div>`;
  }).join('');

  _buildDCATable(tickers);
  _buildDCAOverviewChart(tickers);
}

function _buildDCATable(tickers) {
  const section = scopedFind(null, 'dcaTableSection');
  section.style.display = '';

  const table = scopedFind(null, 'dcaTable');
  table.innerHTML = '<thead><tr>'
    + '<th>Ticker</th>'
    + '<th>Purchases</th>'
    + '<th>Frequency</th>'
    + '<th>Consistency</th>'
    + '<th>Avg Cost</th>'
    + '<th>Current Price</th>'
    + '<th>DCA Return</th>'
    + '<th>Lump Sum Return</th>'
    + '<th>DCA Advantage</th>'
    + '</tr></thead><tbody>'
    + tickers.map(t => {
      const adv = t.lump_sum ? t.lump_sum.dca_advantage_pct : 0;
      const advClass = adv > 0 ? 'positive' : adv < 0 ? 'negative' : '';
      const retClass = t.dca_return_pct >= 0 ? 'positive' : 'negative';
      const lsClass = t.lump_sum && t.lump_sum.return_pct >= 0 ? 'positive' : 'negative';
      return `<tr style="cursor:pointer" onclick="_showDCADetail('${t.ticker}')">`
        + `<td><strong>${t.ticker}</strong></td>`
        + `<td>${t.purchase_count}</td>`
        + `<td>${t.frequency}</td>`
        + `<td>${fmt(t.consistency_score, 0)}%</td>`
        + `<td>${fmtCcy(t.avg_cost_eur)}</td>`
        + `<td>${fmtCcy(t.current_price_eur)}</td>`
        + `<td class="${retClass}">${fmt(t.dca_return_pct, 2)}%</td>`
        + `<td class="${lsClass}">${t.lump_sum ? fmt(t.lump_sum.return_pct, 2) + '%' : '—'}</td>`
        + `<td class="${advClass}">${adv > 0 ? '+' : ''}${fmt(adv, 2)}%</td>`
        + `</tr>`;
    }).join('')
    + '</tbody>';

  makeSortable(table);
}

function _buildDCAOverviewChart(tickers) {
  const section = scopedFind(null, 'dcaChartSection');
  section.style.display = '';

  if (_dcaChart) { _dcaChart.destroy(); _dcaChart = null; }

  const canvas = scopedFind(null, 'dcaChart');
  if (!canvas) return;

  const labels = tickers.map(t => t.ticker);
  const dcaReturns = tickers.map(t => t.dca_return_pct);
  const lsReturns = tickers.map(t => t.lump_sum ? t.lump_sum.return_pct : 0);

  _dcaChart = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'DCA Return %',
          data: dcaReturns,
          backgroundColor: 'rgba(52,211,153,0.6)',
          borderColor: '#34d399',
          borderWidth: 1,
          borderRadius: 3,
        },
        {
          label: 'Lump Sum Return %',
          data: lsReturns,
          backgroundColor: 'rgba(99,102,241,0.6)',
          borderColor: '#6366f1',
          borderWidth: 1,
          borderRadius: 3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: _txtColor() } } },
      scales: {
        x: { ticks: { color: _txtColor() }, grid: { color: _gridColor() } },
        y: {
          ticks: { color: _txtColor(), callback: v => v + '%' },
          grid: { color: _gridColor() },
        },
      },
    },
  });
}

function _showDCADetail(ticker) {
  const dca = D.dca_strategy;
  if (!dca) return;
  const t = dca.tickers.find(x => x.ticker === ticker);
  if (!t) return;

  const section = scopedFind(null, 'dcaDetailSection');
  section.style.display = '';
  scopedFind(null, 'dcaDetailTitle').textContent = ticker + ' — Purchase History';

  if (_dcaDetailChart) { _dcaDetailChart.destroy(); _dcaDetailChart = null; }

  const canvas = scopedFind(null, 'dcaDetailChart');
  if (!canvas) return;

  const history = t.purchase_history || [];
  const cumAvg = t.cumulative_avg_cost || [];

  _dcaDetailChart = new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: {
      labels: history.map(h => h.date),
      datasets: [
        {
          label: 'Purchase Price (' + _currency + ')',
          data: history.map(h => h.price_eur),
          borderColor: '#6366f1',
          backgroundColor: 'rgba(99,102,241,0.1)',
          pointRadius: 4,
          pointBackgroundColor: '#6366f1',
          tension: 0,
          fill: false,
        },
        {
          label: 'Running Avg Cost (' + _currency + ')',
          data: cumAvg,
          borderColor: '#f59e0b',
          borderDash: [5, 3],
          pointRadius: 0,
          tension: 0.3,
          fill: false,
        },
        {
          label: 'Current Price',
          data: history.map(() => t.current_price_eur),
          borderColor: '#34d399',
          borderDash: [2, 2],
          pointRadius: 0,
          borderWidth: 1.5,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: _txtColor() } } },
      scales: {
        x: { ticks: { color: _txtColor(), maxTicksLimit: 12 }, grid: { color: _gridColor() } },
        y: { ticks: { color: _txtColor() }, grid: { color: _gridColor() } },
      },
    },
  });

  const table = scopedFind(null, 'dcaDetailTable');
  table.innerHTML = '<thead><tr>'
    + '<th>Date</th><th>Price</th><th>Amount</th><th>Shares</th><th>Avg Cost</th>'
    + '</tr></thead><tbody>'
    + history.map((h, i) => {
      return `<tr>`
        + `<td>${h.date}</td>`
        + `<td>${fmtCcy(h.price_eur)}</td>`
        + `<td>${fmtCcy(h.amount_eur)}</td>`
        + `<td>${fmt(h.shares, 4)}</td>`
        + `<td>${fmtCcy(cumAvg[i] || 0)}</td>`
        + `</tr>`;
    }).join('')
    + '</tbody>';

  section.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function _txtColor() {
  return getComputedStyle(document.documentElement).getPropertyValue('--text').trim() || '#e2e8f0';
}

function _gridColor() {
  return getComputedStyle(document.documentElement).getPropertyValue('--border').trim() || 'rgba(255,255,255,0.06)';
}
