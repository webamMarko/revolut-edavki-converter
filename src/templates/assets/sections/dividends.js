// --- Dividends section ---
let _dividendChart = null;

function updateDividends() {
  const div = D.dividends;
  if (!div || !div.by_ticker || div.by_ticker.length === 0) {
    document.getElementById('navDividends').style.display = 'none';
    return;
  }
  document.getElementById('navDividends').style.display = '';

  // Summary cards
  const monthly = div.by_month || [];
  const last12 = monthly.slice(-12);
  const ttm = last12.reduce((s, m) => s + m.total_eur, 0);
  const avgMonthly = monthly.length > 0 ? div.total_eur / monthly.length : 0;
  const tickers = div.by_ticker.length;

  document.getElementById('dividendCards').innerHTML = [
    ['Total Income', fmtEur(div.total_eur), ''],
    ['Last 12 Months', fmtEur(ttm), ''],
    ['Monthly Avg', fmtEur(avgMonthly), ''],
    ['Paying Tickers', tickers, ''],
  ].map(([l, v, c]) =>
    `<div class="metric-card"><div class="label">${l}</div><div class="value ${c}">${v}</div></div>`
  ).join('');

  // Monthly bar chart
  _buildDividendChart(monthly);

  // Per-ticker table
  const dt = document.getElementById('dividendTable');
  dt.innerHTML = '<thead><tr>'
    + '<th>Ticker</th>'
    + '<th>Total Income</th>'
    + '<th>Payments</th>'
    + '<th>Share</th>'
    + '</tr></thead><tbody>'
    + div.by_ticker.map(t => {
      const share = div.total_eur > 0 ? (t.total_eur / div.total_eur * 100) : 0;
      return `<tr>`
        + `<td><strong>${t.ticker}</strong></td>`
        + `<td>${fmtEur(t.total_eur)}</td>`
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
        label: 'Dividend Income (EUR)',
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
}
