// --- Formatters ---
const fmt    = (v, d=2) => v == null ? '—' : v.toLocaleString('en-US', {minimumFractionDigits:d, maximumFractionDigits:d});
const fmtEur = v => v == null ? '—' : fmt(v) + ' EUR';
const cls    = v => v == null ? '' : v >= 0 ? 'pos' : 'neg';
const pct    = v => v == null ? '—' : fmt(v) + '%';
const sign   = v => v == null ? '—' : (v >= 0 ? '+' : '') + fmt(v);

// --- Years to FIRE with annual contributions ---
// Solves: PV*(1+r)^t + C*((1+r)^t - 1)/r = target  for t
// No closed form, so use bisection.
function yearsToFireWithContrib(pv, target, r, annualContrib) {
  if (pv >= target) return 0;
  function fv(t) {
    const g = Math.pow(1 + r, t);
    return pv * g + annualContrib * (g - 1) / r;
  }
  let lo = 0, hi = 100;
  if (fv(hi) < target) return null;
  for (let i = 0; i < 60; i++) {
    const mid = (lo + hi) / 2;
    if (fv(mid) < target) lo = mid;
    else hi = mid;
  }
  return (lo + hi) / 2;
}

// --- Yearly averages (arithmetic mean across calendar years) ---
function computeYearlyAverages() {
  if (!allDates || allDates.length < 2) return null;
  const yearMap = {};
  for (let i = 0; i < allDates.length; i++) {
    const y = allDates[i].slice(0, 4);
    if (!yearMap[y]) yearMap[y] = { first: i, last: i };
    else yearMap[y].last = i;
  }
  const years = Object.keys(yearMap).sort();
  if (years.length === 0) return null;
  const valueGrowths = [], cashAdded = [];
  for (const y of years) {
    const { first, last } = yearMap[y];
    valueGrowths.push(ds.value_eur[last] - ds.value_eur[first]);
    cashAdded.push(ds.invested_eur[last] - ds.invested_eur[first]);
  }
  const avg = arr => arr.reduce((a, b) => a + b, 0) / arr.length;
  return {
    avgValueGrowth: avg(valueGrowths),
    avgCashAdded:   avg(cashAdded),
    numYears:       years.length,
  };
}

// --- Update all sections ---
function updateAll() {
  const banner = document.getElementById('selectionBanner');
  const hint = document.querySelector('.chart-hint');
  if (isZoomed) {
    banner.style.display = '';
    document.getElementById('selectionLabel').textContent =
      'Selected period: ' + allDates[selStart] + ' to ' + allDates[selEnd];
    if (hint) hint.textContent = 'Drag to refine, or reset';
  } else {
    banner.style.display = 'none';
    if (hint) hint.textContent = 'Drag to select a period';
  }
  updateSummary();
  updateRiskMetrics();
  updateTopMovers();
  updateGains();
  updateAllocation();
  updateCurrencyExposure();
  updatePositions();
  updateClosedPositions();
  updateDividends();
  updateBenchmarkChart();
  updateBenchmarkTable();
  updateTransactions();
  if (typeof updateTaxTable === 'function') updateTaxTable();
}
