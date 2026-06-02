// --- Compute period metrics ---
function computePeriodMetrics(si, ei) {
  const startVal = ds.value_eur[si];
  const endVal = ds.value_eur[ei];
  const startInv = ds.invested_eur[si];
  const endInv = ds.invested_eur[ei];
  const change = endVal - startVal;
  const returnPct = startVal > 0 ? (endVal / startVal - 1) * 100 : 0;
  const periodRealized = ds.realized_gain_eur[ei] - (si > 0 ? ds.realized_gain_eur[si - 1] : 0);
  const periodDividends = ds.dividends_eur[ei] - (si > 0 ? ds.dividends_eur[si - 1] : 0);

  // Use perf_index for drawdown so cash withdrawals don't register as drawdowns
  const ddSeries = (ds.perf_index && ds.perf_index.length === ds.value_eur.length)
    ? ds.perf_index : ds.value_eur;
  let peak = ddSeries[si], maxDD = 0, peakDate = allDates[si], troughDate = allDates[si];
  let curPeakDate = allDates[si];
  for (let i = si; i <= ei; i++) {
    const v = ddSeries[i];
    if (v > peak) { peak = v; curPeakDate = allDates[i]; }
    const dd = peak > 0 ? (v - peak) / peak * 100 : 0;
    if (dd < maxDD) { maxDD = dd; peakDate = curPeakDate; troughDate = allDates[i]; }
  }
  const days = (new Date(allDates[ei]) - new Date(allDates[si])) / 86400000;
  const years = days / 365.25;
  let cagr = null;
  if (years >= 0.1) {
    const piStart = ddSeries[si], piEnd = ddSeries[ei];
    if (piStart > 0 && piEnd > 0) {
      cagr = (Math.pow(piEnd / piStart, 1 / years) - 1) * 100;
    }
  }
  return {
    startVal, endVal, startInv, endInv, change, returnPct,
    periodRealized, periodDividends, maxDD, peakDate, troughDate, cagr,
    startDate: allDates[si], endDate: allDates[ei], days
  };
}

// --- Metrics config: classifies all 10 overview metrics by tier ---
var METRICS_CONFIG = [
  { key: 'summary.portfolio_value', tier: 'primary' },
  { key: 'summary.total_return',    tier: 'primary' },
  { key: 'summary.daily_change',    tier: 'primary' },
  { key: 'summary.dividend_yield',  tier: 'primary' },
  { key: 'summary.cagr',            tier: 'secondary' },
  { key: 'summary.sharpe',          tier: 'secondary' },
  { key: 'summary.max_drawdown',    tier: 'secondary' },
  { key: 'summary.unrealized_pnl',  tier: 'secondary' },
  { key: 'summary.absolute_gain',   tier: 'secondary' },
  { key: 'summary.twr',             tier: 'secondary' },
];

// --- Summary cards ---
function _renderCard(key, l, v, c, sub, isCustomize, isHidden, rawValue) {
  var hideStyle = isHidden ? ' style="opacity:0.35"' : '';
  var drag = isCustomize ? ' draggable="true"' : '';
  var hideBtn = '<button class="card-hide-btn" style="display:' + (isCustomize ? '' : 'none')
    + '" onclick="_layoutToggleCardVisibility(\'' + key + '\')" title="' + (isHidden ? 'Show' : 'Hide') + '">'
    + (isHidden ? '+' : '&times;') + '</button>';
  var handle = isCustomize ? '<span class="drag-handle">&#x2630;</span>' : '';
  var ttIcon = '';
  if (typeof METRIC_TOOLTIPS !== 'undefined' && METRIC_TOOLTIPS[key]) {
    var rv = rawValue != null ? rawValue : '';
    ttIcon = ' <span class="tt-icon" data-tt-key="' + key + '" data-tt-val="' + rv + '" tabindex="0" aria-label="Info">&#9432;</span>';
  }
  return '<div class="metric-card" data-card-key="' + key + '"' + drag + hideStyle + '>'
    + handle + hideBtn
    + '<div class="label">' + l + ttIcon + '</div><div class="value ' + (c||'') + '">' + v + '</div>'
    + (sub ? '<div class="sub">' + sub + '</div>' : '')
    + '</div>';
}

function updateSummary() {
  const el = scopedFind(null, 'summary');
  const elSec = scopedFind(null, 'summarySecondary');
  var isCustomize = window._layoutIsCustomizeMode ? _layoutIsCustomizeMode() : false;
  var layoutCfg = window._layoutGetCardOrder ? _layoutGetCardOrder() : { order: [], hidden: [] };
  var hiddenCards = layoutCfg.hidden || [];

  if (isZoomed) {
    const m = computePeriodMetrics(selStart, selEnd);
    const cards = [
      ['period.start_value', t('period.start_value'), fmtCcy(m.startVal), '', allDates[selStart], m.startVal],
      ['period.end_value', t('period.end_value'), fmtCcy(m.endVal), '', allDates[selEnd], m.endVal],
      ['period.change', t('period.change'), signCcy(m.change), cls(m.change), '', m.change],
      ['period.return', t('period.return'), sign(m.returnPct)+'%', cls(m.returnPct), '', m.returnPct],
      ['summary.cagr', t('summary.cagr'), m.cagr!=null?sign(m.cagr)+'%':'—', cls(m.cagr), '', m.cagr],
      ['summary.max_drawdown', t('summary.max_drawdown'), pct(m.maxDD), 'neg', m.peakDate+' → '+m.troughDate, m.maxDD],
    ];
    el.innerHTML = cards.map(([key,l,v,c,sub,raw])=>
      _renderCard(key, l, v, c, sub, isCustomize, hiddenCards.indexOf(key) >= 0, raw)
    ).join('');
    if (elSec) elSec.innerHTML = '';
    return;
  }

  const s = getActiveSummary();
  const rm = (s.risk_metrics) || {};
  const gains = D.gains || {};

  // Compute daily change from last two values in the daily series
  var dailyChange = null;
  if (ds.value_eur && ds.value_eur.length >= 2) {
    dailyChange = ds.value_eur[ds.value_eur.length - 1] - ds.value_eur[ds.value_eur.length - 2];
  }

  // Compute dividend yield (cumulative dividends / current portfolio value * 100)
  var dividendYield = null;
  if (gains.dividends_eur != null && s.portfolio_value_eur > 0) {
    dividendYield = gains.dividends_eur / s.portfolio_value_eur * 100;
  }

  // Build card data keyed by metric key — drives the config-based split
  var allCardData = {
    'summary.portfolio_value': ['summary.portfolio_value', t('summary.portfolio_value'), fmtCcy(s.portfolio_value_eur), '', '', s.portfolio_value_eur],
    'summary.total_return':    ['summary.total_return',    t('summary.total_return'),    sign(s.total_return_pct)+'%', cls(s.total_return_pct), '', s.total_return_pct],
    'summary.daily_change':    ['summary.daily_change',    t('summary.daily_change'),    dailyChange != null ? signCcy(dailyChange) : '—', dailyChange != null ? cls(dailyChange) : '', '', dailyChange],
    'summary.dividend_yield':  ['summary.dividend_yield',  t('summary.dividend_yield'),  dividendYield != null ? sign(dividendYield)+'%' : '—', '', '', dividendYield],
    'summary.cagr':            ['summary.cagr',            t('summary.cagr'),            s.cagr_pct!=null?sign(s.cagr_pct)+'%':'—', cls(s.cagr_pct), '', s.cagr_pct],
    'summary.sharpe':          ['summary.sharpe',          t('risk.sharpe'),             rm.sharpe_ratio!=null?fmt(rm.sharpe_ratio):'—', rm.sharpe_ratio!=null?cls(rm.sharpe_ratio):'', '', rm.sharpe_ratio],
    'summary.max_drawdown':    ['summary.max_drawdown',    t('summary.max_drawdown'),    pct(s.max_drawdown_pct), 'neg', s.max_drawdown_peak_date+' → '+s.max_drawdown_trough_date, s.max_drawdown_pct],
    'summary.unrealized_pnl':  ['summary.unrealized_pnl',  t('summary.unrealized_pnl'),  gains.unrealized_eur != null ? signCcy(gains.unrealized_eur) : '—', gains.unrealized_eur != null ? cls(gains.unrealized_eur) : '', '', gains.unrealized_eur],
    'summary.absolute_gain':   ['summary.absolute_gain',   t('summary.absolute_gain'),   signCcy(s.absolute_gain_eur), cls(s.absolute_gain_eur), '', s.absolute_gain_eur],
    'summary.twr':             ['summary.twr',             t('summary.twr'),             s.twr_pct!=null?sign(s.twr_pct)+'%':'—', cls(s.twr_pct), '', s.twr_pct],
  };

  // Split into primary/secondary using METRICS_CONFIG — no hardcoded filtering
  var primaryCards = METRICS_CONFIG.filter(function(m) { return m.tier === 'primary'; })
    .map(function(m) { return allCardData[m.key]; }).filter(Boolean);
  var secondaryCards = METRICS_CONFIG.filter(function(m) { return m.tier === 'secondary'; })
    .map(function(m) { return allCardData[m.key]; }).filter(Boolean);

  // Apply layout ordering/hiding to primary cards
  var cardOrder = layoutCfg.order;
  if (cardOrder && cardOrder.length > 0) {
    var primaryMap = {};
    primaryCards.forEach(function(c) { primaryMap[c[0]] = c; });
    var orderedPrimary = [];
    cardOrder.forEach(function(key) { if (primaryMap[key]) orderedPrimary.push(primaryMap[key]); });
    primaryCards.forEach(function(c) { if (cardOrder.indexOf(c[0]) < 0) orderedPrimary.push(c); });
    primaryCards = orderedPrimary;
  }
  var visiblePrimary = isCustomize ? primaryCards : primaryCards.filter(function(c) {
    return hiddenCards.indexOf(c[0]) < 0;
  });

  el.innerHTML = visiblePrimary.map(function(c) {
    return _renderCard(c[0], c[1], c[2], c[3], c[4], isCustomize, hiddenCards.indexOf(c[0]) >= 0, c[5]);
  }).join('');

  if (elSec) {
    elSec.innerHTML = secondaryCards.map(function(c) {
      return _renderCard(c[0], c[1], c[2], c[3], c[4], false, false, c[5]);
    }).join('');
  }
}

function updateRiskMetrics() {
  const section = scopedFind(null, 'chartsRiskMetricsSection');
  if (isZoomed) { section.style.display = 'none'; return; }
  const s = getActiveSummary();
  const rm = s.risk_metrics;
  if (!rm || rm.volatility_pct == null) { section.style.display = 'none'; return; }
  section.style.display = '';

  const el = scopedFind(null, 'riskMetrics');
  const cards = [
    ['risk.volatility', t('risk.volatility'), pct(rm.volatility_pct), '', t('risk.volatility_sub'), rm.volatility_pct],
    ['risk.sharpe', t('risk.sharpe'), rm.sharpe_ratio != null ? fmt(rm.sharpe_ratio) : '—', rm.sharpe_ratio != null ? cls(rm.sharpe_ratio) : '', t('risk.sharpe_sub'), rm.sharpe_ratio],
    ['risk.sortino', t('risk.sortino'), rm.sortino_ratio != null ? fmt(rm.sortino_ratio) : '—', rm.sortino_ratio != null ? cls(rm.sortino_ratio) : '', t('risk.sortino_sub'), rm.sortino_ratio],
    ['risk.calmar', t('risk.calmar'), rm.calmar_ratio != null ? fmt(rm.calmar_ratio) : '—', rm.calmar_ratio != null ? cls(rm.calmar_ratio) : '', t('risk.calmar_sub'), rm.calmar_ratio],
    ['risk.best_day', t('risk.best_day'), rm.best_day_pct != null ? sign(rm.best_day_pct) + '%' : '—', 'pos', '', rm.best_day_pct],
    ['risk.worst_day', t('risk.worst_day'), rm.worst_day_pct != null ? sign(rm.worst_day_pct) + '%' : '—', 'neg', '', rm.worst_day_pct],
    ['risk.best_month', t('risk.best_month'), rm.best_month_pct != null ? sign(rm.best_month_pct) + '%' : '—', 'pos', '', rm.best_month_pct],
    ['risk.worst_month', t('risk.worst_month'), rm.worst_month_pct != null ? sign(rm.worst_month_pct) + '%' : '—', 'neg', '', rm.worst_month_pct],
    ['risk.positive_days', t('risk.positive_days'), rm.positive_days_pct != null ? fmt(rm.positive_days_pct, 1) + '%' : '—', '', '', rm.positive_days_pct],
  ];
  el.innerHTML = cards.map(([key, l, v, c, sub, raw]) => {
    var ttIcon = '';
    if (typeof METRIC_TOOLTIPS !== 'undefined' && METRIC_TOOLTIPS[key]) {
      var rv = raw != null ? raw : '';
      ttIcon = ' <span class="tt-icon" data-tt-key="' + key + '" data-tt-val="' + rv + '" tabindex="0" aria-label="Info">&#9432;</span>';
    }
    return `<div class="metric-card"><div class="label">${l}${ttIcon}</div><div class="value ${c || ''}">${v}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`;
  }).join('');
}

function updateTopMovers() {
  const positions = getActivePositions();
  const section = scopedFind(null, 'topMoversSection');
  if (positions.length < 2) { section.style.display = 'none'; return; }
  section.style.display = '';

  const names = D.company_names || {};

  // Sort by unrealized gain % for meaningful ranking
  const sorted = [...positions].filter(p => p.cost_basis_eur > 0);
  const gainers = sorted.filter(p => p.unrealized_gain_eur > 0)
    .sort((a, b) => b.unrealized_gain_pct - a.unrealized_gain_pct).slice(0, 5);
  const losers = sorted.filter(p => p.unrealized_gain_eur < 0)
    .sort((a, b) => a.unrealized_gain_pct - b.unrealized_gain_pct).slice(0, 5);

  function renderList(items, el) {
    if (items.length === 0) { el.innerHTML = '<div style="color:var(--muted);font-size:0.8rem;padding:0.5rem">' + t('movers.none') + '</div>'; return; }
    el.innerHTML = items.map(p => {
      const name = names[p.ticker] || '';
      return `<div class="mover-row">
        <div>
          <div class="mover-ticker">${p.ticker}</div>
          ${name ? `<div class="mover-name">${name}</div>` : ''}
        </div>
        <div class="mover-right">
          <div class="mover-gain ${cls(p.unrealized_gain_eur)}">${signCcy(p.unrealized_gain_eur)}</div>
          <div class="mover-pct">${sign(p.unrealized_gain_pct)}%</div>
        </div>
      </div>`;
    }).join('');
  }

  renderList(gainers, scopedFind(null, 'topGainers'));
  renderList(losers, scopedFind(null, 'topLosers'));
}

function updateMilestones() {
  const section = scopedFind(null, 'milestonesSection');
  if (isZoomed || !ds.dates || ds.dates.length < 10) { section.style.display = 'none'; return; }

  const events = [];
  const dates = ds.dates;
  const values = ds.value_eur;

  // First investment date
  for (let i = 0; i < values.length; i++) {
    if (values[i] > 0) {
      events.push({ date: dates[i], icon: '&#x1F680;', text: t('milestones.first_investment'), detail: fmtCcy(values[i]) });
      break;
    }
  }

  // Value thresholds
  const thresholds = [1000, 5000, 10000, 25000, 50000, 100000, 250000, 500000, 1000000];
  const reached = new Set();
  for (let i = 0; i < values.length; i++) {
    for (const th of thresholds) {
      if (!reached.has(th) && values[i] >= th) {
        reached.add(th);
        const label = th >= 1000000 ? (th / 1000000) + 'M' : th >= 1000 ? (th / 1000) + 'K' : th;
        events.push({ date: dates[i], icon: '&#x1F3AF;', text: t('milestones.reached') + ' ' + label + ' ' + _currency, detail: fmtCcy(values[i]) });
      }
    }
  }

  // All-time high (most recent)
  let athIdx = 0;
  for (let i = 1; i < values.length; i++) {
    if (values[i] > values[athIdx]) athIdx = i;
  }
  if (athIdx > 0) {
    events.push({ date: dates[athIdx], icon: '&#x1F451;', text: t('milestones.ath'), detail: fmtCcy(values[athIdx]) });
  }

  // Worst drawdown trough
  const s = getActiveSummary();
  if (s.max_drawdown_pct < -1) {
    events.push({ date: s.max_drawdown_trough_date, icon: '&#x1F4C9;', text: t('milestones.worst_drawdown'), detail: pct(s.max_drawdown_pct) });
  }

  // Largest single-day gain and loss (from perf_index)
  const pi = ds.perf_index;
  if (pi && pi.length > 1) {
    let bestDayIdx = 1, worstDayIdx = 1, bestRet = -Infinity, worstRet = Infinity;
    for (let i = 1; i < pi.length; i++) {
      if (pi[i - 1] > 0) {
        const ret = (pi[i] / pi[i - 1] - 1) * 100;
        if (ret > bestRet) { bestRet = ret; bestDayIdx = i; }
        if (ret < worstRet) { worstRet = ret; worstDayIdx = i; }
      }
    }
    if (bestRet > 0.5) events.push({ date: dates[bestDayIdx], icon: '&#x2B06;&#xFE0F;', text: t('milestones.best_day'), detail: sign(bestRet) + '%' });
    if (worstRet < -0.5) events.push({ date: dates[worstDayIdx], icon: '&#x2B07;&#xFE0F;', text: t('milestones.worst_day'), detail: sign(worstRet) + '%' });
  }

  // Current portfolio age
  if (dates.length > 1) {
    const days = Math.round((new Date(dates[dates.length - 1]) - new Date(dates[0])) / 86400000);
    const years = Math.floor(days / 365);
    const months = Math.floor((days % 365) / 30);
    const ageStr = years > 0 ? years + 'y ' + months + 'm' : months + ' months';
    events.push({ date: dates[dates.length - 1], icon: '&#x1F4C5;', text: t('milestones.portfolio_age') + ': ' + ageStr, detail: days + ' ' + t('milestones.days') });
  }

  if (events.length < 2) { section.style.display = 'none'; return; }
  section.style.display = '';

  // Sort by date
  events.sort((a, b) => a.date.localeCompare(b.date));

  // Format date as short "Mon 'YY"
  function shortDate(d) {
    var parts = d.split('-');
    var m = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][parseInt(parts[1],10)-1];
    return m + " '" + parts[0].slice(2);
  }

  // Compact badge strip (top 6 most interesting)
  var priority = events.filter(function(e) {
    return e.text.indexOf('ATH') >= 0 || e.text.indexOf('ath') >= 0
        || e.text.indexOf('first') >= 0 || e.text.indexOf('First') >= 0
        || e.text.indexOf('age') >= 0 || e.text.indexOf('Age') >= 0
        || e.text.indexOf('Reached') >= 0 || e.text.indexOf('reached') >= 0;
  });
  var badges = (priority.length >= 3 ? priority : events).slice(0, 6);

  var strip = scopedFind(null, 'milestonesStrip');
  strip.innerHTML = badges.map(function(e) {
    return '<span class="ms-badge">' + e.icon + ' ' + e.text + ' <span class="ms-date">' + shortDate(e.date) + '</span></span>';
  }).join('<span class="ms-sep">&middot;</span>')
    + (events.length > 6 ? ' <button class="ms-expand" id="msExpandBtn">Show all &#x25BE;</button>' : '');

  // Full expandable list
  var el = scopedFind(null, 'milestonesList');
  el.innerHTML = events.map(function(e) {
    return '<div class="milestone-item">'
      + '<div class="milestone-icon">' + e.icon + '</div>'
      + '<div class="milestone-body">'
      + '<div class="milestone-date">' + e.date + '</div>'
      + '<div class="milestone-text">' + e.text + '</div>'
      + '<div class="milestone-detail">' + e.detail + '</div>'
      + '</div></div>';
  }).join('');

  // Toggle expand
  var expandBtn = scopedFind(null, 'msExpandBtn');
  if (expandBtn) {
    expandBtn.addEventListener('click', function() {
      var list = scopedFind(null, 'milestonesList');
      var showing = list.style.display !== 'none';
      list.style.display = showing ? 'none' : '';
      expandBtn.innerHTML = showing ? 'Show all &#x25BE;' : 'Hide &#x25B4;';
    });
  }
}

// --- Metrics toggle (progressive disclosure) ---
(function() {
  var btn = scopedFind(null, 'overviewMetricsToggle');
  var panel = scopedFind(null, 'overviewMetricsPanel');
  var label = scopedFind(null, 'overviewMetricsLabel');
  if (!btn || !panel || !label) return;

  function setExpanded(val) {
    btn.setAttribute('aria-expanded', val ? 'true' : 'false');
    if (val) {
      panel.classList.add('is-expanded');
    } else {
      panel.classList.remove('is-expanded');
    }
    label.textContent = val ? 'Show fewer metrics' : 'Show more metrics';
    try {
      localStorage.setItem('overview-metrics-expanded', val ? '1' : '0');
    } catch (e) {}
  }

  var initial = false;
  try {
    var stored = localStorage.getItem('overview-metrics-expanded');
    if (stored === '1') initial = true;
  } catch (e) {}
  setExpanded(initial);

  btn.addEventListener('click', function() {
    var expanded = btn.getAttribute('aria-expanded') === 'true';
    setExpanded(!expanded);
  });
})();

// --- Tax season banner (Jan-Mar) ---
(function() {
  var banner = scopedFind(null, 'taxSeasonBanner');
  if (!banner) return;
  var month = new Date().getMonth();
  var hasTaxData = D.tax_by_year && Object.keys(D.tax_by_year).length > 0;
  if (month <= 2 && hasTaxData) {
    banner.style.display = '';
  }
})();
