// --- Scoped element finder ---
// Finds an element by its data-role attribute within an optional container scope.
// Key behaviour: when container is null/undefined, skips elements inside #widgetTemplates
// (the hidden GridStack template pool) to avoid binding charts/tables to invisible clones.
// Final fallback: document.getElementById for global elements (header, nav) that use plain IDs.
function scopedFind(container, role) {
  if (container) {
    var el = container.querySelector('[data-role="' + role + '"]');
    if (el) return el;
    return null;
  }
  // Walk all matching elements, return the first NOT inside #widgetTemplates
  var candidates = document.querySelectorAll('[data-role="' + role + '"]');
  for (var i = 0; i < candidates.length; i++) {
    if (!candidates[i].closest('#widgetTemplates')) {
      return candidates[i];
    }
  }
  // Nothing found by data-role — fallback to plain id (header/nav/global elements)
  return document.getElementById(role);
}

// --- i18n translation helper ---
const _i18n = D.i18n || {};
function t(key, params) {
  let s = _i18n[key] || key;
  if (params) { for (const [k, v] of Object.entries(params)) s = s.replace('{' + k + '}', v); }
  return s;
}
const _locale = D.locale || 'en-US';
const _currency = D.currency || 'EUR';
const _fx = D.fx_display_rate || 1; // EUR → display currency

// --- Formatters ---
const fmt    = (v, d=2) => v == null ? '—' : v.toLocaleString(_locale, {minimumFractionDigits:d, maximumFractionDigits:d});
const fmtCcy = v => v == null ? '—' : fmt(v * _fx) + ' ' + _currency;
const fmtEur = fmtCcy; // backwards compat alias
const cls    = v => v == null ? '' : v >= 0 ? 'pos' : 'neg';
const pct    = v => v == null ? '—' : fmt(v) + '%';
const sign   = v => v == null ? '—' : (v >= 0 ? '+' : '') + fmt(v);
const signCcy = v => v == null ? '—' : (v >= 0 ? '+' : '') + fmt(v * _fx) + ' ' + _currency;

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

// --- Regime selector ---
(function() {
  const sel = scopedFind(null, 'regimeSelect');
  const regimes = D.available_regimes || [];
  if (!sel || regimes.length === 0) return;
  const current = D.country || 'SI';
  const mobileSel = scopedFind(null, 'mobileRegimeSelect');
  [sel, mobileSel].forEach(function(s) {
    if (!s) return;
    regimes.forEach(function(r) {
      const opt = document.createElement('option');
      opt.value = r.code;
      opt.textContent = r.name + ' (' + r.currency + ')';
      if (r.code === current) opt.selected = true;
      s.appendChild(opt);
    });
  });
  // Localize labels
  const lbl = scopedFind(null, 'regimeFilterLabel');
  if (lbl) lbl.textContent = t('regime.title');
  const albl = scopedFind(null, 'assetFilterLabel');
  if (albl) albl.textContent = t('filter.assets');

  function onRegimeChange(newCountry) {
    if (newCountry === current) return;
    if (window.location.pathname.includes('/report')) {
      const url = new URL(window.location);
      url.searchParams.set('country', newCountry);
      window.location.href = url.toString();
    } else {
      [sel, mobileSel].forEach(function(s) { if (s) s.value = current; });
      alert('To change tax country in standalone reports, regenerate with --country ' + newCountry);
    }
  }
  sel.addEventListener('change', function() { onRegimeChange(sel.value); });
  if (mobileSel) mobileSel.addEventListener('change', function() { onRegimeChange(mobileSel.value); });
  // Show page-filters if we have regimes (even without asset filter)
  const pageFiltersEl = scopedFind(null, 'pageFilters');
  if (pageFiltersEl && regimes.length > 1) pageFiltersEl.style.display = '';
})();

// --- Update all sections ---
function updateAll() {
  const banner = scopedFind(null, 'selectionBanner');
  const hint = document.querySelector('.chart-hint');
  if (isZoomed) {
    banner.style.display = '';
    scopedFind(null, 'selectionLabel').textContent =
      t('period.selected') + ': ' + allDates[selStart] + ' — ' + allDates[selEnd];
    if (hint) hint.textContent = t('period.drag_refine');
  } else {
    banner.style.display = 'none';
    if (hint) hint.textContent = t('period.drag_hint');
  }
  updateSummary();
  updateRiskMetrics();
  updateTopMovers();
  updateMilestones();
  updateGains();
  if (typeof updateRiskPage === 'function') updateRiskPage();
  updateAttribution();
  updatePositions();
  updateClosedPositions();
  updateDividends();
  updateBenchmarkChart();
  updateBenchmarkTable();
  updateTransactions();
  if (typeof updateTaxTable === 'function') updateTaxTable();
  if (typeof updateTaxTimeline === 'function') updateTaxTimeline();
  if (typeof updateTaxPreview === 'function') updateTaxPreview();
  if (typeof updateHoldingCountdown === 'function') updateHoldingCountdown();
  if (typeof updateSmartSell === 'function') updateSmartSell();
  if (typeof updateFire === 'function') updateFire();
  if (typeof updateWhatIf === 'function') updateWhatIf();
  if (typeof updateAchievements === 'function') updateAchievements();
  if (typeof updateDCAStrategy === 'function') updateDCAStrategy();
  if (typeof updateWaterfall === 'function') updateWaterfall();
}
