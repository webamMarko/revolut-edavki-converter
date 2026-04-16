// --- Formatters ---
const fmt    = (v, d=2) => v == null ? '—' : v.toLocaleString('en-US', {minimumFractionDigits:d, maximumFractionDigits:d});
const fmtEur = v => v == null ? '—' : fmt(v) + ' EUR';
const cls    = v => v == null ? '' : v >= 0 ? 'pos' : 'neg';
const pct    = v => v == null ? '—' : fmt(v) + '%';
const sign   = v => v == null ? '—' : (v >= 0 ? '+' : '') + fmt(v);

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
  updateGains();
  updatePositions();
  updateBenchmarkChart();
  updateBenchmarkTable();
  updateTransactions();
  updateTaxTable();
}
