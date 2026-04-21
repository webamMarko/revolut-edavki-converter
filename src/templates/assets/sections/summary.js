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
      ['Start Value', fmtEur(m.startVal), '', allDates[selStart]],
      ['End Value', fmtEur(m.endVal), '', allDates[selEnd]],
      ['Period Change', sign(m.change)+' EUR', cls(m.change)],
      ['Period Return', sign(m.returnPct)+'%', cls(m.returnPct)],
      ['CAGR', m.cagr!=null?sign(m.cagr)+'%':'—', cls(m.cagr)],
      ['Max Drawdown', pct(m.maxDD), 'neg', m.peakDate+' → '+m.troughDate],
    ];
    el.innerHTML = cards.map(([l,v,c,sub])=>
      `<div class="metric-card"><div class="label">${l}</div><div class="value ${c||''}">${v}</div>${sub?`<div class="sub">${sub}</div>`:''}</div>`
    ).join('');
  } else {
    const s = getActiveSummary();
    const cards = [
      ['Portfolio Value', fmtEur(s.portfolio_value_eur)],
      ['Total Invested', fmtEur(s.total_invested_eur)],
      ['Absolute Gain', sign(s.absolute_gain_eur)+' EUR', cls(s.absolute_gain_eur)],
      ['Total Return', sign(s.total_return_pct)+'%', cls(s.total_return_pct)],
      ['CAGR', s.cagr_pct!=null?sign(s.cagr_pct)+'%':'—', cls(s.cagr_pct)],
      ['TWR', s.twr_pct!=null?sign(s.twr_pct)+'%':'—', cls(s.twr_pct)],
      ['Max Drawdown', pct(s.max_drawdown_pct), 'neg', s.max_drawdown_peak_date+' → '+s.max_drawdown_trough_date],
    ];
    const yearly = computeYearlyAverages();
    if (yearly) {
      const totalYears = allDates.length > 1
        ? (new Date(allDates[allDates.length-1]) - new Date(allDates[0])) / (365.25 * 86400000)
        : 1;
      const sub = yearly.numYears + ' yr avg';
      cards.push(['Avg Yearly Growth',   sign(yearly.avgValueGrowth)+' EUR',              cls(yearly.avgValueGrowth), sub]);
      if (s.total_return_pct != null && totalYears > 0)
        cards.push(['Avg Yearly Return', sign(s.total_return_pct / totalYears)+'%',       cls(s.total_return_pct),    sub]);
      cards.push(['Avg Yearly Invested', sign(yearly.avgCashAdded)+' EUR',                cls(yearly.avgCashAdded),   sub]);
    }
    if (D.fire != null) {
      const fire = D.fire;
      const fireTarget = fire.target;
      const progress = s.portfolio_value_eur / fireTarget * 100;
      const remaining = fireTarget - s.portfolio_value_eur;
      let fireSub = remaining > 0 ? '−'+fmtEur(remaining)+' to go' : '🎉 Achieved!';
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
            fireSub = '~' + fmt(yearsToFire, 1) + ' yrs · est. ' + fireYear;
          }
        }
      }
      cards.push(['FIRE Progress', fmt(progress, 1)+'%', progress >= 100 ? 'pos' : '', fireSub]);
    }
    el.innerHTML = cards.map(([l,v,c,sub])=>
      `<div class="metric-card"><div class="label">${l}</div><div class="value ${c||''}">${v}</div>${sub?`<div class="sub">${sub}</div>`:''}</div>`
    ).join('');
  }
}
