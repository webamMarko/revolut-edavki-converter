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

function buildPortfolioChart() {
  const ctx1 = document.getElementById('portfolioChart').getContext('2d');
  let chartLabels = allDates.slice();
  let portfolioData = ds.value_eur.slice();
  let investedData  = ds.invested_eur.slice();
  let fireData = null, projData = null;

  if (D.fire != null && showFire) {
    const fire = D.fire;
    const fireTarget = fire.target;
    const inflation = fire.inflation_rate / 100;
    const nominalCAGR = (D.summary.cagr_pct != null ? D.summary.cagr_pct : 8) / 100;
    const realReturn = (1 + nominalCAGR) / (1 + inflation) - 1;
    const currentValue = ds.value_eur[ds.value_eur.length - 1];
    const lastDate = new Date(allDates[allDates.length - 1]);
    const yearsToFire = realReturn > 0 && currentValue < fireTarget
      ? Math.log(fireTarget / currentValue) / Math.log(1 + realReturn)
      : null;
    const horizonMonths = yearsToFire != null && yearsToFire < 50
      ? Math.ceil(yearsToFire * 12) + 24
      : 36;
    const futureDates = [];
    const futureProj  = [currentValue];
    for (let m = 1; m <= horizonMonths; m++) {
      const d = new Date(lastDate);
      d.setMonth(d.getMonth() + m);
      futureDates.push(d.toISOString().slice(0, 10));
      futureProj.push(Math.round(currentValue * Math.pow(1 + nominalCAGR, m / 12)));
    }
    chartLabels  = allDates.concat(futureDates);
    const futurePad = new Array(futureDates.length).fill(null);
    portfolioData = ds.value_eur.concat(futurePad);
    investedData  = ds.invested_eur.concat(futurePad);
    fireData = new Array(chartLabels.length).fill(fireTarget);
    projData = new Array(allDates.length - 1).fill(null).concat(futureProj);
  }

  const chartDatasets = [
    {label:'Portfolio Value', data:portfolioData, borderColor:'#4285f4', backgroundColor:'rgba(66,133,244,0.08)', fill:true,  tension:0.15, pointRadius:0, borderWidth:2},
    {label:'Cash Invested',   data:investedData,  borderColor:'#9e9e9e', borderDash:[5,5],   fill:false, tension:0.15, pointRadius:0, borderWidth:1.5},
  ];
  if (fireData) {
    chartDatasets.push({label:'FIRE Target',      data:fireData, borderColor:'#22c55e', borderDash:[6,4], fill:false, tension:0,    pointRadius:0, borderWidth:2});
    chartDatasets.push({label:'Projected Growth', data:projData, borderColor:'#4285f4', borderDash:[3,3], fill:false, tension:0.1,  pointRadius:0, borderWidth:1.5, spanGaps:false});
  }

  return new Chart(ctx1, {
    type: 'line',
    data: { labels: chartLabels, datasets: chartDatasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: {mode:'index', intersect:false},
      scales: {
        x: {type:'time', time:{unit:'month', tooltipFormat:'yyyy-MM-dd'}, grid:{display:false}},
        y: {title:{display:true, text:'EUR'}, ticks:{callback: v => v.toLocaleString()}}
      },
      plugins: {
        tooltip: {callbacks: {label: c => c.parsed.y != null ? c.dataset.label + ': ' + fmt(c.parsed.y) + ' EUR' : ''}},
        zoom: zoomOpts
      }
    }
  });
}

function buildBenchmarkChart() {
  document.getElementById('benchmarkSection').style.display = '';
  if (bKeys.length > 0) {
    document.getElementById('benchmarkTableCard').style.display = '';
    document.getElementById('benchmarkSectionTitle').textContent = 'Performance vs Benchmarks';
  }
  const rebased = (ds.perf_index && ds.perf_index.length > 0)
    ? ds.perf_index.map(v => v > 0 ? v : null)
    : ds.value_eur.map(() => null);
  const bds = [{label:'Portfolio', data:rebased.map((v,i) => ({x:allDates[i], y:v})), borderColor:'#4285f4', borderWidth:2, pointRadius:0, tension:0.15}];
  const bColors = {'S&P 500':'#ea4335', 'NASDAQ':'#34a853', 'Dow Jones':'#fbbc04', 'FTSE 100':'#7c3aed'};
  bKeys.forEach(tk => {
    const b = D.benchmark_series[tk];
    bds.push({label:b.name, data:b.dates.map((d,i) => ({x:d, y:b.values[i]})), borderColor:bColors[b.name]||'#999', borderWidth:1.5, pointRadius:0, tension:0.15});
  });
  const ctx2 = document.getElementById('benchmarkChart').getContext('2d');
  return new Chart(ctx2, {
    type: 'line',
    data: { datasets: bds },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: {mode:'index', intersect:false},
      scales: {
        x: {type:'time', time:{unit:'month', tooltipFormat:'yyyy-MM-dd'}, grid:{display:false}},
        y: {title:{display:true, text:'Value per 100 EUR invested'}}
      },
      plugins: {tooltip: {callbacks: {label: c => c.dataset.label + ': ' + fmt(c.parsed.y)}}, zoom: zoomOpts}
    }
  });
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
function syncChartZoom(sourceChart) {
  const target = sourceChart === portfolioChart ? benchmarkChart : portfolioChart;
  if (!target) return;
  const scale = sourceChart.scales.x;
  target.options.scales.x.min = scale.min;
  target.options.scales.x.max = scale.max;
  target.update('none');
}

// --- Reset zoom ---
function clearScaleLimits(chart) {
  delete chart.options.scales.x.min;
  delete chart.options.scales.x.max;
  chart.resetZoom();
  chart.update();
}
window.resetZoom = function() {
  selStart = 0; selEnd = N - 1; isZoomed = false;
  clearScaleLimits(portfolioChart);
  if (benchmarkChart) clearScaleLimits(benchmarkChart);
  updateAll();
};
