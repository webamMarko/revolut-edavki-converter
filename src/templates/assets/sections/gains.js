// --- Gains breakdown ---
let _gainsChart = null;

function updateGains() {
  const gt = document.getElementById('gainsTable');
  const wrap = document.getElementById('gainsChartWrap');
  if (isZoomed) {
    const m = computePeriodMetrics(selStart, selEnd);
    const unrealized = m.endVal - m.endInv - ds.realized_gain_eur[selEnd];
    gt.innerHTML='<tbody>'+[
      ['Period Realized Gains', m.periodRealized],
      ['Unrealized (at end)', unrealized],
      ['Period Dividends', m.periodDividends],
    ].map(([l,v])=>`<tr><td>${l}</td><td class="${cls(v)}">${sign(v)} EUR</td></tr>`).join('')+'</tbody>';
    _buildGainsChart([
      { label: 'Realized', value: m.periodRealized },
      { label: 'Unrealized', value: unrealized },
      { label: 'Dividends', value: m.periodDividends },
    ]);
  } else {
    const g = getActiveGains();
    gt.innerHTML='<tbody>'+[
      ['Realized Gains',g.realized_eur],['Unrealized Gains',g.unrealized_eur],
      ['Dividends',g.dividends_eur],['Fees',g.fees_eur],
    ].map(([l,v])=>`<tr><td>${l}</td><td class="${cls(v)}">${sign(v)} EUR</td></tr>`).join('')+'</tbody>';
    _buildGainsChart([
      { label: 'Realized', value: g.realized_eur },
      { label: 'Unrealized', value: g.unrealized_eur },
      { label: 'Dividends', value: g.dividends_eur },
      { label: 'Fees', value: g.fees_eur },
    ]);
  }
}

function _buildGainsChart(items) {
  if (_gainsChart) { _gainsChart.destroy(); _gainsChart = null; }
  const wrap = document.getElementById('gainsChartWrap');
  const canvas = document.getElementById('gainsChart');
  if (!canvas || items.length === 0) { wrap.style.display = 'none'; return; }

  // Filter out near-zero items
  const filtered = items.filter(i => Math.abs(i.value) > 0.01);
  if (filtered.length < 2) { wrap.style.display = 'none'; return; }
  wrap.style.display = '';

  // Add total bar
  const total = filtered.reduce((s, i) => s + i.value, 0);
  const labels = filtered.map(i => i.label).concat(['Total']);
  const values = filtered.map(i => i.value).concat([total]);

  const colors = values.map((v, i) =>
    i === values.length - 1 ? 'rgba(99,102,241,0.7)' // total: indigo
    : v >= 0 ? 'rgba(52,211,153,0.7)' : 'rgba(248,113,113,0.7)'
  );
  const borderColors = values.map((v, i) =>
    i === values.length - 1 ? '#6366f1' : v >= 0 ? '#34d399' : '#f87171'
  );

  _gainsChart = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        data: values,
        backgroundColor: colors,
        borderColor: borderColors,
        borderWidth: 1,
        borderRadius: 3,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      scales: {
        x: { grid: { display: false }, ticks: { color: '#556075', font: { size: 10 } } },
        y: {
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
}
