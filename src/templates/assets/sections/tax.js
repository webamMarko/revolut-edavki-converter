// --- Tax section ---
function updateTaxTable() {
  if (!D.tax) return;
  document.getElementById('taxSection').style.display = '';
  const t = D.tax;
  const sales = isZoomed
    ? t.realized_sales.filter(s => s.sell_date >= allDates[selStart] && s.sell_date <= allDates[selEnd])
    : t.realized_sales;
  const periodGain = sales.reduce((a,s) => a + s.gain_eur, 0);
  const periodTax  = sales.reduce((a,s) => a + s.tax_eur, 0);

  document.getElementById('taxCards').innerHTML = [
    ['Tax Year', t.year, ''],
    ['Realized Gain', sign(isZoomed ? periodGain : t.total_realized_gain_eur)+' EUR', cls(isZoomed ? periodGain : t.total_realized_gain_eur)],
    ['Realized Tax', fmtEur(isZoomed ? periodTax : t.total_realized_tax_eur), ''],
    ['Dividends', fmtEur(t.total_dividends_eur), ''],
    ['Fees', sign(t.total_fees_eur)+' EUR', cls(t.total_fees_eur)],
    ['Total Tax', fmtEur(isZoomed ? periodTax : t.total_tax_eur), 'neg'],
  ].map(([l,v,c])=>`<div class="metric-card"><div class="label">${l}</div><div class="value ${c}">${v}</div></div>`).join('');

  if (sales.length > 0) {
    const tt = document.getElementById('taxTable');
    tt.innerHTML = '<thead><tr><th>Ticker</th><th>Date</th><th>Qty</th><th>Proceeds</th><th>Cost Basis</th><th>Gain</th><th>Held</th><th>Rate</th><th>Tax</th></tr></thead><tbody>'+
      sales.map(s=>`<tr><td>${s.ticker}</td><td>${s.sell_date}</td><td>${fmt(s.quantity,4)}</td><td>${fmtEur(s.sell_price_eur)}</td><td>${fmtEur(s.cost_basis_eur)}</td><td class="${cls(s.gain_eur)}">${sign(s.gain_eur)} EUR</td><td>${fmt(s.holding_years,1)}y</td><td>${Math.round(s.tax_rate*100)}%</td><td>${fmtEur(s.tax_eur)}</td></tr>`).join('')+'</tbody>';
    makeSortable(tt);
  }
}
