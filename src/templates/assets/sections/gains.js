// --- Gains breakdown ---
function updateGains() {
  const gt = document.getElementById('gainsTable');
  if (isZoomed) {
    const m = computePeriodMetrics(selStart, selEnd);
    const unrealized = m.endVal - m.endInv - ds.realized_gain_eur[selEnd];
    gt.innerHTML='<tbody>'+[
      ['Period Realized Gains', m.periodRealized],
      ['Unrealized (at end)', unrealized],
      ['Period Dividends', m.periodDividends],
    ].map(([l,v])=>`<tr><td>${l}</td><td class="${cls(v)}">${sign(v)} EUR</td></tr>`).join('')+'</tbody>';
  } else {
    const g = getActiveGains();
    gt.innerHTML='<tbody>'+[
      ['Realized Gains',g.realized_eur],['Unrealized Gains',g.unrealized_eur],
      ['Dividends',g.dividends_eur],['Fees',g.fees_eur],
    ].map(([l,v])=>`<tr><td>${l}</td><td class="${cls(v)}">${sign(v)} EUR</td></tr>`).join('')+'</tbody>';
  }
}
