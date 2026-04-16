// --- Asset class filter state ---
const perClass = D.per_class || {};
const classKeys = Object.keys(perClass);
const hasFilter = classKeys.length > 1;
// These classes start inactive by default (different time horizon / skews the main chart)
const defaultInactive = new Set(['realestate', 'savings']);
let activeClasses = new Set(classKeys.filter(k => !defaultInactive.has(k)));
const classLabels = {stock:'Stocks', cfd:'CFD', crypto:'Crypto', savings:'Savings', realestate:'Real Estate'};

// FIRE projection lines: off by default
let showFire = false;

// Keys included in the pre-computed "all" daily series (everything except realestate)
const allSeriesKeys = new Set(classKeys.filter(k => k !== 'realestate'));

function buildCombinedSeries() {
  const nonReActive = [...activeClasses].filter(k => k !== 'realestate');
  if (!hasFilter || (nonReActive.length === allSeriesKeys.size && !activeClasses.has('realestate'))) {
    return {
      dates: D.daily_series.dates,
      value_eur: D.daily_series.value_eur.slice(),
      invested_eur: D.daily_series.invested_eur.slice(),
      dividends_eur: D.daily_series.dividends_eur.slice(),
      realized_gain_eur: D.daily_series.realized_gain_eur.slice(),
      perf_index: (D.daily_series.perf_index || []).slice(),
    };
  }
  if (activeClasses.size === 0) {
    return {dates:[], value_eur:[], invested_eur:[], dividends_eur:[], realized_gain_eur:[], perf_index:[]};
  }
  if (activeClasses.size === 1) {
    const ac = [...activeClasses][0];
    const s = perClass[ac];
    return {
      dates: s.dates.slice(),
      value_eur: s.value_eur.slice(),
      invested_eur: s.invested_eur.slice(),
      dividends_eur: s.dividends_eur.slice(),
      realized_gain_eur: s.realized_gain_eur.slice(),
      perf_index: (s.perf_index || []).slice(),
    };
  }
  // Multiple but not all: collect all unique dates, then sum with forward-fill
  const dateSet = new Set();
  activeClasses.forEach(ac => { perClass[ac].dates.forEach(d => dateSet.add(d)); });
  const dates = [...dateSet].sort();
  // Pre-build sorted date arrays and pointer maps for O(n) forward-fill
  const sortedDates = {};
  activeClasses.forEach(ac => { sortedDates[ac] = perClass[ac].dates; });
  const N2 = dates.length;
  const value_eur        = new Array(N2).fill(0);
  const invested_eur     = new Array(N2).fill(0);
  const dividends_eur    = new Array(N2).fill(0);
  const realized_gain_eur = new Array(N2).fill(0);
  for (let i = 0; i < N2; i++) {
    const d = dates[i];
    activeClasses.forEach(ac => {
      const s = perClass[ac];
      const sd = sortedDates[ac];
      // Binary search for last date <= d
      let lo = 0, hi = sd.length - 1, idx = -1;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (sd[mid] <= d) { idx = mid; lo = mid + 1; }
        else { hi = mid - 1; }
      }
      if (idx >= 0) {
        value_eur[i]         += s.value_eur[idx];
        invested_eur[i]      += s.invested_eur[idx];
        dividends_eur[i]     += s.dividends_eur[idx];
        realized_gain_eur[i] += s.realized_gain_eur[idx];
      }
    });
  }
  const perf_index = computePerfIndex(value_eur, invested_eur);
  return {dates, value_eur, invested_eur, dividends_eur, realized_gain_eur, perf_index};
}

function computePerfIndex(values, invested) {
  const n = values.length;
  const pi = new Array(n);
  let idx = 100.0;
  for (let i = 0; i < n; i++) {
    if (i === 0) { pi[i] = values[0] > 0 ? 100.0 : 0; continue; }
    const prev = values[i-1];
    if (prev > 1e-6) {
      const cashflow = invested[i] - invested[i-1];
      const ret = (values[i] - cashflow) / prev - 1;
      idx *= (1 + ret);
    }
    pi[i] = idx;
  }
  return pi;
}

function isDefaultSelection() {
  const financialActive = [...activeClasses].filter(k => k !== 'realestate');
  return !hasFilter || (financialActive.length === allSeriesKeys.size && !activeClasses.has('realestate'));
}

function getActiveSummary() {
  if (isDefaultSelection()) return D.summary;
  if (activeClasses.size === 0) return {portfolio_value_eur:0, total_invested_eur:0, absolute_gain_eur:0, total_return_pct:0, cagr_pct:null, twr_pct:null, max_drawdown_pct:0, max_drawdown_peak_date:'', max_drawdown_trough_date:''};
  if (activeClasses.size === 1) return perClass[[...activeClasses][0]].summary;
  let pv = 0, ti = 0, ag = 0;
  activeClasses.forEach(ac => {
    const s = perClass[ac].summary;
    pv += s.portfolio_value_eur; ti += s.total_invested_eur; ag += s.absolute_gain_eur;
  });
  const ret = ti > 0 ? (ag / ti * 100) : 0;
  const cs = buildCombinedSeries();
  // CAGR: annualised TWR from combined perf_index (DCA-aware).
  // Guard against haywire perf_index (e.g. when CFD is included in combination).
  let cagr = null;
  if (cs.perf_index && cs.perf_index.length > 1 && cs.dates.length > 1) {
    const pi = cs.perf_index;
    const firstNZ = pi.find(v => v > 0);
    const years = (new Date(cs.dates[cs.dates.length-1]) - new Date(cs.dates[0])) / (365.25 * 86400000);
    if (firstNZ && years >= 0.1 && pi[pi.length-1] > 0) {
      const ratio = pi[pi.length-1] / firstNZ;
      if (ratio < 1e5) cagr = (ratio ** (1 / years) - 1) * 100;
    }
  }
  let peak = cs.value_eur[0]||0, maxDD = 0, peakDate = cs.dates[0]||'', troughDate = cs.dates[0]||'', curPeakDate = cs.dates[0]||'';
  for (let i = 0; i < cs.dates.length; i++) {
    const v = cs.value_eur[i];
    if (v > peak) { peak = v; curPeakDate = cs.dates[i]; }
    const dd = peak > 0 ? (v - peak) / peak * 100 : 0;
    if (dd < maxDD) { maxDD = dd; peakDate = curPeakDate; troughDate = cs.dates[i]; }
  }
  return {portfolio_value_eur:pv, total_invested_eur:ti, absolute_gain_eur:ag, total_return_pct:ret, cagr_pct:cagr, twr_pct:null, max_drawdown_pct:maxDD, max_drawdown_peak_date:peakDate, max_drawdown_trough_date:troughDate};
}

function getActiveGains() {
  if (isDefaultSelection()) return D.gains;
  if (activeClasses.size === 0) return {realized_eur:0, unrealized_eur:0, dividends_eur:0, fees_eur:0};
  if (activeClasses.size === 1) return perClass[[...activeClasses][0]].gains;
  let r = 0, u = 0, d = 0, f = 0;
  activeClasses.forEach(ac => { const g = perClass[ac].gains; r += g.realized_eur; u += g.unrealized_eur; d += g.dividends_eur; f += g.fees_eur; });
  return {realized_eur:r, unrealized_eur:u, dividends_eur:d, fees_eur:f};
}

function getActivePositions() {
  if (isDefaultSelection()) return D.positions;
  let all = [];
  activeClasses.forEach(ac => { all = all.concat(perClass[ac].positions); });
  const totalMV = all.reduce((a, p) => a + p.market_value_eur, 0) || 1;
  return all.map(p => ({...p, weight_pct: p.market_value_eur / totalMV * 100})).sort((a, b) => b.market_value_eur - a.market_value_eur);
}

// --- Active series (initialised at load time) ---
let ds = buildCombinedSeries();
let allDates = ds.dates;
let N = allDates.length;

// --- Current selection state ---
let selStart = 0, selEnd = N - 1;
let isZoomed = false;

// --- Asset filter UI ---
if (hasFilter) {
  const filterEl = document.getElementById('assetFilter');
  filterEl.style.display = '';
  const togglesEl = document.getElementById('assetToggles');
  const mobileFiltersEl = document.getElementById('mobileFilters');
  const mobileTogglesEl = document.getElementById('mobileAssetToggles');
  if (mobileFiltersEl) mobileFiltersEl.style.display = '';

  classKeys.forEach(ac => {
    const isActive = activeClasses.has(ac);
    const cls = 'toggle-btn toggle-' + ac + (isActive ? ' active' : '');

    function makeBtn(container) {
      const btn = document.createElement('div');
      btn.className = cls;
      btn.textContent = classLabels[ac] || ac;
      btn.dataset.ac = ac;
      container.appendChild(btn);
      return btn;
    }

    const sidebarBtn = makeBtn(togglesEl);
    const mobileBtn  = mobileTogglesEl ? makeBtn(mobileTogglesEl) : null;

    function syncBtns(active) {
      sidebarBtn.classList.toggle('active', active);
      if (mobileBtn) mobileBtn.classList.toggle('active', active);
    }

    function handleClick() {
      if (activeClasses.has(ac)) {
        if (activeClasses.size <= 1) return;
        activeClasses.delete(ac);
        syncBtns(false);
      } else {
        activeClasses.add(ac);
        syncBtns(true);
      }
      onFilterChange();
    }

    sidebarBtn.addEventListener('click', handleClick);
    if (mobileBtn) mobileBtn.addEventListener('click', handleClick);
  });
}

// --- FIRE toggle ---
if (D.fire != null) {
  document.getElementById('fireFilter').style.display = '';
  const fireBtn = document.getElementById('fireToggleBtn');
  fireBtn.addEventListener('click', function() {
    showFire = !showFire;
    fireBtn.classList.toggle('active', showFire);
    rebuildCharts();
    updateAll();
  });
}

function onFilterChange() {
  ds = buildCombinedSeries();
  allDates = ds.dates;
  N = allDates.length;
  selStart = 0; selEnd = N - 1; isZoomed = false;
  rebuildCharts();
  updateAll();
  buildHeatmap();
  buildYearlyHeatmap();
  document.querySelectorAll('.range-btn').forEach(function(b) {
    b.classList.toggle('active', b.dataset.days === '-1' && !b.dataset.ytd);
  });
}
