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

// --- Summary cards ---
function updateSummary() {
  const el = document.getElementById('summary');
  if (isZoomed) {
    const m = computePeriodMetrics(selStart, selEnd);
    const cards = [
      [t('period.start_value'), fmtCcy(m.startVal), '', allDates[selStart]],
      [t('period.end_value'), fmtCcy(m.endVal), '', allDates[selEnd]],
      [t('period.change'), signCcy(m.change), cls(m.change)],
      [t('period.return'), sign(m.returnPct)+'%', cls(m.returnPct)],
      [t('summary.cagr'), m.cagr!=null?sign(m.cagr)+'%':'—', cls(m.cagr)],
      [t('summary.max_drawdown'), pct(m.maxDD), 'neg', m.peakDate+' → '+m.troughDate],
    ];
    el.innerHTML = cards.map(([l,v,c,sub])=>
      `<div class="metric-card"><div class="label">${l}</div><div class="value ${c||''}">${v}</div>${sub?`<div class="sub">${sub}</div>`:''}</div>`
    ).join('');
  } else {
    const s = getActiveSummary();
    const cards = [
      [t('summary.portfolio_value'), fmtCcy(s.portfolio_value_eur)],
      [t('summary.total_invested'), fmtCcy(s.total_invested_eur)],
      [t('summary.absolute_gain'), signCcy(s.absolute_gain_eur), cls(s.absolute_gain_eur)],
      [t('summary.total_return'), sign(s.total_return_pct)+'%', cls(s.total_return_pct)],
      [t('summary.cagr'), s.cagr_pct!=null?sign(s.cagr_pct)+'%':'—', cls(s.cagr_pct)],
      [t('summary.twr'), s.twr_pct!=null?sign(s.twr_pct)+'%':'—', cls(s.twr_pct)],
      [t('summary.max_drawdown'), pct(s.max_drawdown_pct), 'neg', s.max_drawdown_peak_date+' → '+s.max_drawdown_trough_date],
    ];
    const yearly = computeYearlyAverages();
    if (yearly) {
      const totalYears = allDates.length > 1
        ? (new Date(allDates[allDates.length-1]) - new Date(allDates[0])) / (365.25 * 86400000)
        : 1;
      const sub = yearly.numYears + ' ' + t('summary.yr_avg');
      cards.push([t('summary.avg_yearly_growth'),   signCcy(yearly.avgValueGrowth),              cls(yearly.avgValueGrowth), sub]);
      if (s.total_return_pct != null && totalYears > 0)
        cards.push([t('summary.avg_yearly_return'), sign(s.total_return_pct / totalYears)+'%',       cls(s.total_return_pct),    sub]);
      cards.push([t('summary.avg_yearly_invested'), signCcy(yearly.avgCashAdded),                cls(yearly.avgCashAdded),   sub]);
    }
    if (D.fire != null) {
      const fire = D.fire;
      const fireTarget = fire.target;
      const progress = s.portfolio_value_eur / fireTarget * 100;
      const remaining = fireTarget - s.portfolio_value_eur;
      let fireSub = remaining > 0 ? '−'+fmtCcy(remaining)+' '+t('summary.fire_to_go') : t('summary.fire_achieved');
      if (remaining > 0 && s.cagr_pct != null && s.cagr_pct > 0) {
        const nominalCAGR = s.cagr_pct / 100;
        const inflation = getFireInflation() / 100;
        const realReturn = (1 + nominalCAGR) / (1 + inflation) - 1;
        if (realReturn > 0) {
          const monthlyContrib = getFireMonthlyContrib();
          const annualContrib = monthlyContrib * 12;
          const yearsToFire = annualContrib > 0
            ? yearsToFireWithContrib(s.portfolio_value_eur, fireTarget, realReturn, annualContrib)
            : Math.log(fireTarget / s.portfolio_value_eur) / Math.log(1 + realReturn);
          if (yearsToFire != null) {
            const fireYear = new Date().getFullYear() + Math.ceil(yearsToFire);
            fireSub = '~' + fmt(yearsToFire, 1) + ' ' + t('summary.fire_years') + ' · ' + t('summary.fire_est') + ' ' + fireYear;
          }
        }
      }
      cards.push([t('summary.fire_progress'), fmt(progress, 1)+'%', progress >= 100 ? 'pos' : '', fireSub]);
    }
    el.innerHTML = cards.map(([l,v,c,sub])=>
      `<div class="metric-card"><div class="label">${l}</div><div class="value ${c||''}">${v}</div>${sub?`<div class="sub">${sub}</div>`:''}</div>`
    ).join('');
  }
}

function updateRiskMetrics() {
  const section = document.getElementById('riskMetricsSection');
  if (isZoomed) { section.style.display = 'none'; return; }
  const s = getActiveSummary();
  const rm = s.risk_metrics;
  if (!rm || rm.volatility_pct == null) { section.style.display = 'none'; return; }
  section.style.display = '';

  const el = document.getElementById('riskMetrics');
  const cards = [
    [t('risk.volatility'), pct(rm.volatility_pct), '', t('risk.volatility_sub')],
    [t('risk.sharpe'), rm.sharpe_ratio != null ? fmt(rm.sharpe_ratio) : '—', rm.sharpe_ratio != null ? cls(rm.sharpe_ratio) : '', t('risk.sharpe_sub')],
    [t('risk.sortino'), rm.sortino_ratio != null ? fmt(rm.sortino_ratio) : '—', rm.sortino_ratio != null ? cls(rm.sortino_ratio) : '', t('risk.sortino_sub')],
    [t('risk.calmar'), rm.calmar_ratio != null ? fmt(rm.calmar_ratio) : '—', rm.calmar_ratio != null ? cls(rm.calmar_ratio) : '', t('risk.calmar_sub')],
    [t('risk.best_day'), rm.best_day_pct != null ? sign(rm.best_day_pct) + '%' : '—', 'pos'],
    [t('risk.worst_day'), rm.worst_day_pct != null ? sign(rm.worst_day_pct) + '%' : '—', 'neg'],
    [t('risk.best_month'), rm.best_month_pct != null ? sign(rm.best_month_pct) + '%' : '—', 'pos'],
    [t('risk.worst_month'), rm.worst_month_pct != null ? sign(rm.worst_month_pct) + '%' : '—', 'neg'],
    [t('risk.positive_days'), rm.positive_days_pct != null ? fmt(rm.positive_days_pct, 1) + '%' : '—', ''],
  ];
  el.innerHTML = cards.map(([l, v, c, sub]) =>
    `<div class="metric-card"><div class="label">${l}</div><div class="value ${c || ''}">${v}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`
  ).join('');
}

function updateTopMovers() {
  const positions = getActivePositions();
  const section = document.getElementById('topMoversSection');
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

  renderList(gainers, document.getElementById('topGainers'));
  renderList(losers, document.getElementById('topLosers'));
}

function updateMilestones() {
  const section = document.getElementById('milestonesSection');
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

  if (events.length < 3) { section.style.display = 'none'; return; }
  section.style.display = '';

  // Sort by date
  events.sort((a, b) => a.date.localeCompare(b.date));

  const el = document.getElementById('milestonesList');
  el.innerHTML = events.map(e =>
    `<div class="milestone-item">`
    + `<div class="milestone-icon">${e.icon}</div>`
    + `<div class="milestone-body">`
    + `<div class="milestone-date">${e.date}</div>`
    + `<div class="milestone-text">${e.text}</div>`
    + `<div class="milestone-detail">${e.detail}</div>`
    + `</div></div>`
  ).join('');
}
