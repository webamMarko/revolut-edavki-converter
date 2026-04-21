// --- Monthly heatmap ---
function buildHeatmap() {
  const el = document.getElementById('heatmap');
  if (!el || ds.dates.length === 0) return;
  const dates = ds.dates;
  const hasPerfIdx = ds.perf_index && ds.perf_index.length === dates.length;
  const values = hasPerfIdx ? ds.perf_index : ds.value_eur;
  const monthMap = {};
  for (let i = 0; i < dates.length; i++) {
    const ym = dates[i].substring(0, 7);
    if (!monthMap[ym]) monthMap[ym] = {si: i, ei: i};
    else monthMap[ym].ei = i;
  }
  const yrSet = new Set();
  const years = [];
  Object.keys(monthMap).sort().forEach(function(k) {
    const y = k.substring(0, 4);
    if (!yrSet.has(y)) { yrSet.add(y); years.push(y); }
  });
  const mNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  let maxAbs = 5;
  Object.keys(monthMap).forEach(function(ym) {
    const d = monthMap[ym];
    if (values[d.si] > 0) { const r = Math.abs((values[d.ei]/values[d.si]-1)*100); if (r > maxAbs) maxAbs = r; }
  });
  maxAbs = Math.min(maxAbs, 20);
  function cellBg(ret) {
    const intensity = Math.min(Math.abs(ret)/maxAbs, 1);
    const alpha = (0.12 + 0.78*intensity).toFixed(2);
    return ret >= 0 ? 'rgba(52,211,153,'+alpha+')' : 'rgba(248,113,113,'+alpha+')';
  }
  function cellFg(ret) {
    return Math.min(Math.abs(ret)/maxAbs, 1) > 0.5 ? '#fff' : 'var(--text)';
  }
  let h = '<table class="heatmap-table"><thead><tr><th></th>';
  mNames.forEach(function(m) { h += '<th>' + m + '</th>'; });
  h += '<th class="heatmap-year-col">Year</th></tr></thead><tbody>';
  years.forEach(function(year) {
    h += '<tr><td class="heatmap-year-label">' + year + '</td>';
    let ySi = null, yEi = null;
    for (let m = 1; m <= 12; m++) {
      const ym = year + '-' + (m < 10 ? '0' : '') + m;
      const d = monthMap[ym];
      if (!d || values[d.si] <= 0) { h += '<td class="heatmap-empty"></td>'; continue; }
      const ret = (values[d.ei]/values[d.si]-1)*100;
      const s = ret >= 0 ? '+' : '';
      h += '<td class="heatmap-cell" style="background:'+cellBg(ret)+';color:'+cellFg(ret)+'" title="'+ym+': '+s+ret.toFixed(2)+'%">'+s+ret.toFixed(1)+'%</td>';
      if (ySi === null) ySi = d.si;
      yEi = d.ei;
    }
    if (ySi !== null && values[ySi] > 0) {
      const ret = (values[yEi]/values[ySi]-1)*100;
      const s = ret >= 0 ? '+' : '';
      h += '<td class="heatmap-cell heatmap-year-cell" style="background:'+cellBg(ret)+';color:'+cellFg(ret)+'"><strong>'+s+ret.toFixed(1)+'%</strong></td>';
    } else { h += '<td></td>'; }
    h += '</tr>';
  });
  h += '</tbody></table>';
  el.innerHTML = h;
}

// --- Drawdown chart ---
let _drawdownChart = null;

function buildDrawdownChart() {
  if (_drawdownChart) { _drawdownChart.destroy(); _drawdownChart = null; }

  const section = document.getElementById('drawdownSection');
  const canvas = document.getElementById('drawdownChart');
  if (!canvas || !ds.dates || ds.dates.length < 10) { section.style.display = 'none'; return; }

  const pi = (ds.perf_index && ds.perf_index.length === ds.dates.length) ? ds.perf_index : ds.value_eur;
  // Skip leading zeros
  var startIdx = 0;
  while (startIdx < pi.length && pi[startIdx] <= 0) startIdx++;
  if (pi.length - startIdx < 10) { section.style.display = 'none'; return; }
  section.style.display = '';

  var peak = pi[startIdx];
  const ddData = [];
  const labels = [];
  for (var i = startIdx; i < pi.length; i++) {
    if (pi[i] > peak) peak = pi[i];
    const dd = peak > 0 ? (pi[i] - peak) / peak * 100 : 0;
    ddData.push(dd);
    labels.push(ds.dates[i]);
  }

  _drawdownChart = new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: {
      labels: labels,
      datasets: [{
        label: 'Drawdown',
        data: ddData,
        borderColor: '#f87171',
        backgroundColor: 'rgba(248,113,113,0.15)',
        fill: true,
        tension: 0.15,
        pointRadius: 0,
        borderWidth: 1.5,
      }],
    },
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
          ticks: { color: '#556075', font: { size: 10 }, maxTicksLimit: 8 },
        },
        y: {
          max: 0,
          grid: { color: 'rgba(30,42,58,0.8)' },
          ticks: {
            color: '#556075',
            font: { size: 10 },
            callback: function(v) { return v.toFixed(0) + '%'; },
          },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function(c) { return 'Drawdown: ' + fmt(c.parsed.y) + '%'; },
          },
        },
      },
    },
  });
}

// --- Yearly heatmap ---
function buildYearlyHeatmap() {
  const el = document.getElementById('yearly-heatmap');
  if (!el || ds.dates.length === 0) return;
  const dates = ds.dates;
  const hasPerfIdx = ds.perf_index && ds.perf_index.length === dates.length;
  const perfVals = hasPerfIdx ? ds.perf_index : ds.value_eur;
  const hasInvested = ds.invested_eur && ds.invested_eur.length === dates.length;

  // Build year index map
  const yearMap = {};
  for (let i = 0; i < dates.length; i++) {
    const y = dates[i].substring(0, 4);
    if (!yearMap[y]) yearMap[y] = {si: i, ei: i};
    else yearMap[y].ei = i;
  }
  const years = Object.keys(yearMap).sort();

  // Color scale based on annual returns
  let maxAbs = 10;
  years.forEach(function(y) {
    const d = yearMap[y];
    if (perfVals[d.si] > 0) {
      const r = Math.abs((perfVals[d.ei] / perfVals[d.si] - 1) * 100);
      if (r > maxAbs) maxAbs = r;
    }
  });
  maxAbs = Math.min(maxAbs, 60);

  function cellBg(ret) {
    const intensity = Math.min(Math.abs(ret) / maxAbs, 1);
    const alpha = (0.15 + 0.75 * intensity).toFixed(2);
    return ret >= 0 ? 'rgba(52,211,153,' + alpha + ')' : 'rgba(248,113,113,' + alpha + ')';
  }
  function cellFg(ret) {
    return Math.min(Math.abs(ret) / maxAbs, 1) > 0.5 ? '#fff' : 'var(--text)';
  }

  let h = '<table class="heatmap-table yearly-heatmap-table">';
  h += '<thead><tr><th>Year</th><th>Annual Return</th><th>Gain / Loss</th><th>Year-end Value</th>';
  if (hasInvested) h += '<th>Cash Invested</th>';
  h += '</tr></thead><tbody>';

  years.forEach(function(year) {
    const d = yearMap[year];
    const startEur = ds.value_eur[d.si];
    const endEur = ds.value_eur[d.ei];
    const gainEur = endEur - startEur;

    let ret = null;
    if (perfVals[d.si] > 0) ret = (perfVals[d.ei] / perfVals[d.si] - 1) * 100;

    let investedYr = null;
    if (hasInvested) investedYr = ds.invested_eur[d.ei] - ds.invested_eur[d.si];

    const s = ret !== null && ret >= 0 ? '+' : '';
    const gs = gainEur >= 0 ? '+' : '';

    h += '<tr>';
    h += '<td class="heatmap-year-label">' + year + '</td>';
    if (ret !== null) {
      h += '<td class="heatmap-cell yearly-ret-cell" style="background:' + cellBg(ret) + ';color:' + cellFg(ret) + '">' +
           '<strong>' + s + ret.toFixed(2) + '%</strong></td>';
    } else {
      h += '<td class="heatmap-empty">—</td>';
    }
    h += '<td class="' + (gainEur >= 0 ? 'pos' : 'neg') + '">' + gs + fmt(gainEur) + ' EUR</td>';
    h += '<td>' + fmt(endEur) + ' EUR</td>';
    if (hasInvested) {
      const is = investedYr >= 0 ? '+' : '';
      h += '<td style="color:var(--muted)">' + is + fmt(investedYr) + ' EUR</td>';
    }
    h += '</tr>';
  });

  h += '</tbody></table>';
  el.innerHTML = h;
}

// --- Annual Summary Table ---
function buildYearlyTable() {
  const el = document.getElementById('yearlyTable');
  if (!el || ds.dates.length === 0) return;
  const section = document.getElementById('yearlyTableSection');

  const dates = ds.dates;
  const hasPerfIdx = ds.perf_index && ds.perf_index.length === dates.length;
  const perfVals = hasPerfIdx ? ds.perf_index : ds.value_eur;

  // Build year index map
  const yearMap = {};
  for (let i = 0; i < dates.length; i++) {
    const y = dates[i].substring(0, 4);
    if (!yearMap[y]) yearMap[y] = {si: i, ei: i};
    else yearMap[y].ei = i;
  }
  const years = Object.keys(yearMap).sort();
  if (years.length < 2) { section.style.display = 'none'; return; }
  section.style.display = '';

  el.innerHTML = '<thead><tr>'
    + '<th>Year</th>'
    + '<th>Start Value</th>'
    + '<th>End Value</th>'
    + '<th>Return %</th>'
    + '<th>Net Deposits</th>'
    + '<th>Dividends</th>'
    + '<th>Realized P&L</th>'
    + '<th>Max Drawdown</th>'
    + '</tr></thead><tbody>'
    + years.map(function(year) {
      const d = yearMap[year];
      const startVal = ds.value_eur[d.si];
      const endVal = ds.value_eur[d.ei];

      // TWR-based return
      var ret = null;
      if (perfVals[d.si] > 0) ret = (perfVals[d.ei] / perfVals[d.si] - 1) * 100;

      // Net deposits
      const netDeposits = ds.invested_eur[d.ei] - ds.invested_eur[d.si];

      // Dividends for the year
      const divEnd = ds.dividends_eur[d.ei];
      const divStart = d.si > 0 ? ds.dividends_eur[d.si - 1] : 0;
      const yearDivs = divEnd - divStart;

      // Realized gains for the year
      const realEnd = ds.realized_gain_eur[d.ei];
      const realStart = d.si > 0 ? ds.realized_gain_eur[d.si - 1] : 0;
      const yearRealized = realEnd - realStart;

      // Max drawdown within the year (using perf_index)
      var peak = perfVals[d.si], maxDD = 0;
      for (var i = d.si; i <= d.ei; i++) {
        if (perfVals[i] > peak) peak = perfVals[i];
        const dd = peak > 0 ? (perfVals[i] - peak) / peak * 100 : 0;
        if (dd < maxDD) maxDD = dd;
      }

      return '<tr>'
        + '<td><strong>' + year + '</strong></td>'
        + '<td>' + fmtEur(startVal) + '</td>'
        + '<td>' + fmtEur(endVal) + '</td>'
        + '<td class="' + (ret != null ? cls(ret) : '') + '">' + (ret != null ? sign(ret) + '%' : '—') + '</td>'
        + '<td class="' + cls(netDeposits) + '">' + sign(netDeposits) + ' EUR</td>'
        + '<td>' + fmtEur(yearDivs) + '</td>'
        + '<td class="' + cls(yearRealized) + '">' + sign(yearRealized) + ' EUR</td>'
        + '<td class="neg">' + pct(maxDD) + '</td>'
        + '</tr>';
    }).join('')
    + '</tbody>';

  makeSortable(el);
}

// --- Rolling 1-Year Returns Chart ---
let _rollingChart = null;

function buildRollingReturns() {
  if (_rollingChart) { _rollingChart.destroy(); _rollingChart = null; }

  const section = document.getElementById('rollingReturnsSection');
  const canvas = document.getElementById('rollingReturnsChart');
  if (!canvas || !ds.dates || ds.dates.length < 252) { section.style.display = 'none'; return; }

  const pi = (ds.perf_index && ds.perf_index.length === ds.dates.length) ? ds.perf_index : ds.value_eur;
  const lookback = 252; // ~1 year of trading days
  const data = [];
  const labels = [];
  for (var i = lookback; i < pi.length; i++) {
    if (pi[i - lookback] > 0) {
      const ret = (pi[i] / pi[i - lookback] - 1) * 100;
      data.push(ret);
      labels.push(ds.dates[i]);
    }
  }

  if (data.length < 10) { section.style.display = 'none'; return; }
  section.style.display = '';

  // Color the line based on positive/negative
  const colors = data.map(d => d >= 0 ? '#34d399' : '#f87171');

  _rollingChart = new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: {
      labels: labels,
      datasets: [{
        label: 'Rolling 1Y Return',
        data: data,
        borderColor: '#6366f1',
        backgroundColor: function(ctx) {
          const val = ctx.raw;
          return val >= 0 ? 'rgba(52,211,153,0.1)' : 'rgba(248,113,113,0.1)';
        },
        fill: true,
        tension: 0.2,
        pointRadius: 0,
        borderWidth: 1.5,
        segment: {
          borderColor: function(ctx) {
            return ctx.p1.parsed.y >= 0 ? '#34d399' : '#f87171';
          },
        },
      }],
    },
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
          ticks: { color: '#556075', font: { size: 10 }, maxTicksLimit: 8 },
        },
        y: {
          grid: { color: 'rgba(30,42,58,0.8)' },
          ticks: {
            color: '#556075',
            font: { size: 10 },
            callback: function(v) { return (v >= 0 ? '+' : '') + v.toFixed(0) + '%'; },
          },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function(c) { return 'Rolling 1Y: ' + sign(c.parsed.y) + '%'; },
          },
        },
        annotation: {
          annotations: {
            zeroLine: {
              type: 'line',
              yMin: 0, yMax: 0,
              borderColor: 'rgba(255,255,255,0.2)',
              borderWidth: 1,
              borderDash: [4, 4],
            },
          },
        },
      },
    },
  });
}
