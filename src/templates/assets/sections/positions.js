// --- Positions table ---
function updatePositions() {
  const positions = getActivePositions();
  const section = document.getElementById('positionsSection');
  if (positions.length === 0) { section.style.display = 'none'; return; }
  section.style.display = '';
  const pt = document.getElementById('positionsTable');
  pt.innerHTML='<thead><tr><th>Ticker</th><th>Qty</th><th>Cost Basis</th><th>Market Value</th><th>Unrealized</th><th>Return %</th><th>Weight</th></tr></thead><tbody>'+
    positions.map(p=>`<tr><td><strong>${p.ticker}</strong></td><td>${fmt(p.quantity,4)}</td><td>${fmtEur(p.cost_basis_eur)}</td><td>${fmtEur(p.market_value_eur)}</td><td class="${cls(p.unrealized_gain_eur)}">${sign(p.unrealized_gain_eur)} EUR</td><td class="${cls(p.unrealized_gain_pct)}">${sign(p.unrealized_gain_pct)}%</td><td>${fmt(p.weight_pct,1)}%</td></tr>`).join('')+'</tbody>';
  makeSortable(pt);
}
