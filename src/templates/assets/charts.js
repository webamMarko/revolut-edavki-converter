// --- Zoom plugin config (shared) ---
const zoomOpts = {
  zoom: {
    drag: { enabled: true, backgroundColor: 'rgba(66,133,244,0.15)', borderColor: '#4285f4', borderWidth: 1 },
    mode: 'x',
    onZoomComplete: function(ctx) {
      const scale = ctx.chart.scales.x;
      const minMs = scale.min, maxMs = scale.max;
      let si = 0, ei = N - 1;
      for (let i = 0; i < N; i++) { if (new Date(allDates[i]).getTime() >= minMs) { si = i; break; } }
      for (let i = N - 1; i >= 0; i--) { if (new Date(allDates[i]).getTime() <= maxMs) { ei = i; break; } }
      if (si > ei) { si = 0; ei = N - 1; }
      selStart = si; selEnd = ei; isZoomed = true;
      syncChartZoom(ctx.chart);
      updateAll();
    }
  }
};

// --- Charts ---
let portfolioChart, benchmarkChart;

function _buildCumulativeTaxSeries() {
  var tby = D.tax_by_year || {};
  var events = [];
  Object.keys(tby).forEach(function(yr) {
    var sales = (tby[yr].realized_sales || []);
    sales.forEach(function(s) {
      if (s.sell_date && s.tax_eur) events.push({date: s.sell_date.substring(0, 10), tax: s.tax_eur});
    });
  });
  events.sort(function(a, b) { return a.date < b.date ? -1 : a.date > b.date ? 1 : 0; });
  var dateMap = {};
  events.forEach(function(e) { dateMap[e.date] = (dateMap[e.date] || 0) + e.tax; });
  var cumulative = new Array(allDates.length);
  var running = 0;
  for (var i = 0; i < allDates.length; i++) {
    var d = allDates[i];
    if (dateMap[d]) running += dateMap[d];
    cumulative[i] = Math.round(running * 100) / 100;
  }
  return cumulative;
}

function buildPortfolioChart() {
  const ctx1 = scopedFind(null, 'portfolioChart').getContext('2d');
  let chartLabels = allDates.slice();
  let portfolioData = ds.value_eur.slice();
  let investedData  = ds.invested_eur.slice();
  let taxData = _buildCumulativeTaxSeries();
  const chartDatasets = [
    {label:'Portfolio Value', data:portfolioData, borderColor:'#4285f4', backgroundColor:'rgba(66,133,244,0.08)', fill:true,  tension:0.15, pointRadius:0, borderWidth:2},
    {label:'Cash Invested',   data:investedData,  borderColor:'#9e9e9e', borderDash:[5,5],   fill:false, tension:0.15, pointRadius:0, borderWidth:1.5},
    {label:'Total Tax (Est.)', data:taxData, borderColor:'#e53935', borderDash:[3,3], fill:false, tension:0.15, pointRadius:0, borderWidth:1.5, hidden:true},
  ];

  return new Chart(ctx1, {
    type: 'line',
    data: { labels: chartLabels, datasets: chartDatasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: {mode:'index', intersect:false},
      scales: {
        x: {type:'time', time:{unit:'month', tooltipFormat:'yyyy-MM-dd'}, grid:{display:false}},
        y: {title:{display:true, text:_currency}, ticks:{callback: v => (v * _fx).toLocaleString(_locale)}}
      },
      plugins: {
        tooltip: {callbacks: {label: c => c.parsed.y != null ? c.dataset.label + ': ' + fmt(c.parsed.y * _fx) + ' ' + _currency : ''}},
        zoom: zoomOpts
      }
    }
  });
}

function _benchmarkDatasets() {
  // Build benchmark datasets rebased to 100 at selStart date.
  const startDate = allDates[selStart];
  const endDate   = allDates[selEnd];

  // Portfolio: rebase perf_index so value at selStart = 100
  const pi = (ds.perf_index && ds.perf_index.length > 0) ? ds.perf_index : null;
  let portData = [];
  if (pi) {
    const base = pi[selStart] > 0 ? pi[selStart] : null;
    for (let i = selStart; i <= selEnd; i++) {
      portData.push({x: allDates[i], y: base ? Math.round(pi[i] / base * 100 * 100) / 100 : null});
    }
  }

  const bColors = {'S&P 500':'#ea4335', 'NASDAQ':'#34a853', 'Dow Jones':'#fbbc04', 'FTSE 100':'#7c3aed', 'VWCE':'#f97316', 'MSCI World':'#0ea5e9', 'STOXX Europe 600':'#ec4899'};
  const bds = [{label:'Portfolio', data:portData, borderColor:'#4285f4', borderWidth:2, pointRadius:0, tension:0.15}];

  bKeys.forEach(tk => {
    const b = D.benchmark_series[tk];
    // Find the index in benchmark dates closest to selStart date
    let bsi = 0;
    for (let i = 0; i < b.dates.length; i++) {
      if (b.dates[i] >= startDate) { bsi = i; break; }
      bsi = i;
    }
    const baseVal = b.values[bsi] > 0 ? b.values[bsi] : null;
    const data = [];
    for (let i = bsi; i < b.dates.length; i++) {
      if (b.dates[i] > endDate) break;
      data.push({x: b.dates[i], y: baseVal ? Math.round(b.values[i] / baseVal * 100 * 100) / 100 : null});
    }
    bds.push({label:b.name, data, borderColor:bColors[b.name]||'#999', borderWidth:1.5, pointRadius:0, tension:0.15});
  });
  return bds;
}

function buildBenchmarkChart() {
  scopedFind(null, 'benchmarkSkeleton').style.display = 'none';
  scopedFind(null, 'benchmarkChart').style.display = '';
  if (bKeys.length === 0) {
    scopedFind(null, 'benchmarkSection').style.display = 'none';
  } else {
    scopedFind(null, 'benchmarkTableCard').style.display = '';
    scopedFind(null, 'benchmarkSectionTitle').textContent = 'Performance vs Benchmarks';
  }
  const ctx2 = scopedFind(null, 'benchmarkChart').getContext('2d');
  return new Chart(ctx2, {
    type: 'line',
    data: { datasets: _benchmarkDatasets() },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: {mode:'index', intersect:false},
      scales: {
        x: {type:'time', time:{unit:'month', tooltipFormat:'yyyy-MM-dd'}, grid:{display:false}},
        y: {title:{display:true, text:'Index (start of period = 100)'}}
      },
      plugins: {tooltip: {callbacks: {label: c => c.dataset.label + ': ' + fmt(c.parsed.y)}}, zoom: zoomOpts}
    }
  });
}

function updateBenchmarkChart() {
  if (!benchmarkChart) return;
  const bds = _benchmarkDatasets();
  bds.forEach((bd, i) => {
    if (benchmarkChart.data.datasets[i]) {
      benchmarkChart.data.datasets[i].data = bd.data;
    }
  });
  // Explicitly pin the x-axis to the selection window so Chart.js doesn't
  // misplace points when auto-fitting after data replacement.
  benchmarkChart.options.scales.x.min = new Date(allDates[selStart]).getTime();
  benchmarkChart.options.scales.x.max = new Date(allDates[selEnd]).getTime();
  benchmarkChart.update();
}

function rebuildCharts() {
  if (portfolioChart) portfolioChart.destroy();
  if (benchmarkChart) benchmarkChart.destroy();
  benchmarkChart = null;
  portfolioChart = buildPortfolioChart();
  benchmarkChart = buildBenchmarkChart();
}

// Shared benchmark key list (used by benchmark_table.js)
const bKeys = Object.keys(D.benchmark_series);

// --- Sync zoom between charts ---
// Only the portfolio chart is zoom-draggable; the benchmark chart rebasess via updateBenchmarkChart().
function syncChartZoom(sourceChart) {
  // No-op: benchmark chart is updated via updateBenchmarkChart() in updateAll()
}

// --- Reset to "All" time range (shared by the All range button and the
// selection banner's Reset button — they must behave identically) ---
function applyAllRange() {
  selStart = 0; selEnd = N - 1; isZoomed = false;
  if (portfolioChart) {
    delete portfolioChart.options.scales.x.min;
    delete portfolioChart.options.scales.x.max;
    portfolioChart.update();
  }
  const bar = scopedFind(null, 'rangeBar');
  if (bar) {
    bar.querySelectorAll('.range-btn').forEach(function(b) { b.classList.remove('active'); });
    const allBtn = bar.querySelector('.range-btn[data-days="-1"]');
    if (allBtn) allBtn.classList.add('active');
  }
  updateAll();
}
window.resetZoom = applyAllRange;
