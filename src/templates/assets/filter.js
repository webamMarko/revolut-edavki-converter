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
  if (activeClasses.size === 0) return {portfolio_value_eur:0, total_invested_eur:0, absolute_gain_eur:0, total_return_pct:0, cagr_pct:null, twr_pct:null, max_drawdown_pct:0, max_drawdown_peak_date:'', max_drawdown_trough_date:'', risk_metrics:{}};
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
  const rm = computeClientRiskMetrics(cs);
  return {portfolio_value_eur:pv, total_invested_eur:ti, absolute_gain_eur:ag, total_return_pct:ret, cagr_pct:cagr, twr_pct:null, max_drawdown_pct:maxDD, max_drawdown_peak_date:peakDate, max_drawdown_trough_date:troughDate, risk_metrics:rm};
}

function computeClientRiskMetrics(cs) {
  const pi = cs.perf_index;
  if (!pi || pi.length < 30) return {};
  // Filter to positive values
  let startIdx = 0;
  while (startIdx < pi.length && pi[startIdx] <= 0) startIdx++;
  if (pi.length - startIdx < 30) return {};

  const vals = pi.slice(startIdx);
  const dates = cs.dates.slice(startIdx);
  const n = vals.length;

  // Daily returns
  const returns = [];
  for (let i = 1; i < n; i++) {
    if (vals[i-1] > 0) returns.push(vals[i] / vals[i-1] - 1);
  }
  if (returns.length < 20) return {};

  const mean = returns.reduce((a,b) => a+b, 0) / returns.length;
  const variance = returns.reduce((a,r) => a + (r-mean)*(r-mean), 0) / (returns.length - 1);
  const volDaily = Math.sqrt(variance);
  const volAnnual = volDaily * Math.sqrt(252) * 100;
  const meanAnnual = mean * 252;
  const rfAnnual = 0.03, rfDaily = rfAnnual / 252;

  const sharpe = volDaily > 1e-10 ? Math.round((meanAnnual - rfAnnual) / (volDaily * Math.sqrt(252)) * 100) / 100 : null;

  const downside = returns.filter(r => r < rfDaily);
  let sortino = null;
  if (downside.length > 5) {
    const dsMean = downside.reduce((a,b) => a+b,0)/downside.length;
    const dsVar = downside.reduce((a,r) => a+(r-dsMean)*(r-dsMean),0)/(downside.length-1);
    const dsStd = Math.sqrt(dsVar);
    if (dsStd > 1e-10) sortino = Math.round((meanAnnual - rfAnnual) / (dsStd * Math.sqrt(252)) * 100) / 100;
  }

  const bestDay = Math.max(...returns) * 100;
  const worstDay = Math.min(...returns) * 100;

  // Monthly returns
  const monthlyReturns = [];
  let monthStartVal = vals[0], curMonth = dates[0].slice(0,7);
  for (let i = 1; i < n; i++) {
    const m = dates[i].slice(0,7);
    if (m !== curMonth) {
      if (monthStartVal > 0) monthlyReturns.push((vals[i-1]/monthStartVal - 1) * 100);
      monthStartVal = vals[i-1]; curMonth = m;
    }
  }
  if (monthStartVal > 0 && n > 1) monthlyReturns.push((vals[n-1]/monthStartVal - 1) * 100);

  const bestMonth = monthlyReturns.length > 0 ? Math.max(...monthlyReturns) : null;
  const worstMonth = monthlyReturns.length > 0 ? Math.min(...monthlyReturns) : null;
  const posDays = returns.filter(r => r > 0).length / returns.length * 100;

  let calmar = null;
  let ddPeak = vals[0], maxDDRatio = 0;
  for (let i = 1; i < n; i++) {
    if (vals[i] > ddPeak) ddPeak = vals[i];
    const dd = (vals[i] - ddPeak) / ddPeak;
    if (dd < maxDDRatio) maxDDRatio = dd;
  }
  if (Math.abs(maxDDRatio) > 1e-10) calmar = Math.round(meanAnnual / Math.abs(maxDDRatio) * 100) / 100;

  return {
    volatility_pct: Math.round(volAnnual * 100) / 100,
    sharpe_ratio: sharpe,
    sortino_ratio: sortino,
    best_day_pct: Math.round(bestDay * 100) / 100,
    worst_day_pct: Math.round(worstDay * 100) / 100,
    best_month_pct: bestMonth != null ? Math.round(bestMonth * 100) / 100 : null,
    worst_month_pct: worstMonth != null ? Math.round(worstMonth * 100) / 100 : null,
    positive_days_pct: Math.round(posDays * 10) / 10,
    calmar_ratio: calmar,
  };
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

function getActiveClosedPositions() {
  if (isDefaultSelection()) return D.closed_positions || [];
  let all = [];
  activeClasses.forEach(ac => { all = all.concat((perClass[ac].closed_positions || [])); });
  return all.sort((a, b) => Math.abs(b.realized_gain_eur) - Math.abs(a.realized_gain_eur));
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

// --- FIRE toggle + settings ---
let fireInflationOverride = null;   // null = use D.fire.inflation_rate
let fireMonthlyContribOverride = null; // null = use computed avg

function getFireInflation() {
  return fireInflationOverride != null ? fireInflationOverride : (D.fire ? D.fire.inflation_rate : 2.5);
}
function getFireMonthlyContrib() {
  if (fireMonthlyContribOverride != null) return fireMonthlyContribOverride;
  const yearly = computeYearlyAverages();
  return yearly ? yearly.avgCashAdded / 12 : 0;
}

if (D.fire != null) {
  document.getElementById('fireFilter').style.display = '';
  const fireBtn = document.getElementById('fireToggleBtn');
  const fireInputsEl = document.getElementById('fireInputs');
  const mobileFireRow = document.getElementById('mobileFireRow');
  const mobileFireBtn = document.getElementById('mobileFireToggleBtn');
  const mobileFireInputsEl = document.getElementById('mobileFireInputs');
  const mobileFiltersContainer = document.getElementById('mobileFilters');
  if (mobileFireRow) mobileFireRow.style.display = '';
  if (mobileFiltersContainer && !hasFilter) mobileFiltersContainer.style.display = '';

  // Input elements
  const inflInput = document.getElementById('fireInflationInput');
  const contribInput = document.getElementById('fireContribInput');
  const mInflInput = document.getElementById('mobileFireInflationInput');
  const mContribInput = document.getElementById('mobileFireContribInput');

  // Set defaults
  const defaultInflation = D.fire.inflation_rate;
  const yearly0 = computeYearlyAverages();
  const defaultMonthly = yearly0 ? Math.round(yearly0.avgCashAdded / 12) : 0;
  [inflInput, mInflInput].forEach(el => { if (el) el.value = defaultInflation; });
  [contribInput, mContribInput].forEach(el => { if (el) el.value = defaultMonthly; });

  function showFireInputs(visible) {
    if (fireInputsEl) fireInputsEl.style.display = visible ? '' : 'none';
    if (mobileFireInputsEl) mobileFireInputsEl.style.display = visible ? '' : 'none';
  }

  function onFireInputChange() {
    fireInflationOverride = parseFloat(inflInput.value);
    if (isNaN(fireInflationOverride)) fireInflationOverride = null;
    fireMonthlyContribOverride = parseFloat(contribInput.value);
    if (isNaN(fireMonthlyContribOverride)) fireMonthlyContribOverride = null;
    // Sync mobile inputs
    if (mInflInput) mInflInput.value = inflInput.value;
    if (mContribInput) mContribInput.value = contribInput.value;
    rebuildCharts();
    updateAll();
  }
  function onMobileFireInputChange() {
    fireInflationOverride = parseFloat(mInflInput.value);
    if (isNaN(fireInflationOverride)) fireInflationOverride = null;
    fireMonthlyContribOverride = parseFloat(mContribInput.value);
    if (isNaN(fireMonthlyContribOverride)) fireMonthlyContribOverride = null;
    // Sync sidebar inputs
    inflInput.value = mInflInput.value;
    contribInput.value = mContribInput.value;
    rebuildCharts();
    updateAll();
  }
  inflInput.addEventListener('change', onFireInputChange);
  contribInput.addEventListener('change', onFireInputChange);
  if (mInflInput) mInflInput.addEventListener('change', onMobileFireInputChange);
  if (mContribInput) mContribInput.addEventListener('change', onMobileFireInputChange);

  function toggleFire() {
    showFire = !showFire;
    fireBtn.classList.toggle('active', showFire);
    if (mobileFireBtn) mobileFireBtn.classList.toggle('active', showFire);
    showFireInputs(showFire);
    rebuildCharts();
    updateAll();
  }
  fireBtn.addEventListener('click', toggleFire);
  if (mobileFireBtn) mobileFireBtn.addEventListener('click', toggleFire);
}

function onFilterChange() {
  ds = buildCombinedSeries();
  allDates = ds.dates;
  N = allDates.length;
  selStart = 0; selEnd = N - 1; isZoomed = false;
  rebuildCharts();
  updateAll();
  buildHeatmap();
  buildDrawdownChart();
  buildYearlyHeatmap();
  buildYearlyTable();
  buildRollingReturns();
  document.querySelectorAll('.range-btn').forEach(function(b) {
    b.classList.toggle('active', b.dataset.days === '-1' && !b.dataset.ytd);
  });
}
