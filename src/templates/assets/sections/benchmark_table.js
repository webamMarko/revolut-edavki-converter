// --- Benchmark table ---
function updateBenchmarkTable() {
  if (bKeys.length === 0) return;
  const bt = document.getElementById('benchmarkTable');
  if (isZoomed) {
    const startDate = new Date(allDates[selStart]);
    const endDate = new Date(allDates[selEnd]);
    const startVal = ds.value_eur[selStart], endVal = ds.value_eur[selEnd];
    const portfolioRet = startVal > 0 ? (endVal / startVal - 1) * 100 : 0;
    const rows = [];
    bKeys.forEach(tk => {
      const b = D.benchmark_series[tk];
      let bsi = 0, bei = b.dates.length - 1;
      for (let i = 0; i < b.dates.length; i++) { if (new Date(b.dates[i]) >= startDate) { bsi = i; break; } }
      for (let i = b.dates.length - 1; i >= 0; i--) { if (new Date(b.dates[i]) <= endDate) { bei = i; break; } }
      const bStart = b.values[bsi], bEnd = b.values[bei];
      const benchRet = bStart > 0 ? (bEnd / bStart - 1) * 100 : 0;
      const alpha = portfolioRet - benchRet;
      rows.push({name: b.name, benchRet, portfolioRet, alpha});
    });
    bt.innerHTML='<thead><tr><th>Benchmark</th><th>Return</th><th>Portfolio</th><th>Alpha</th></tr></thead><tbody>'+
      rows.map(r=>`<tr><td>${r.name}</td><td>${sign(r.benchRet)}%</td><td>${sign(r.portfolioRet)}%</td><td class="${cls(r.alpha)}">${sign(r.alpha)}%</td></tr>`).join('')+'</tbody>';
  } else {
    bt.innerHTML='<thead><tr><th>Benchmark</th><th>Return</th><th>Portfolio</th><th>Alpha</th></tr></thead><tbody>'+
      D.benchmarks.map(b=>`<tr><td>${b.name}</td><td>${pct(b.return_pct)}</td><td>${pct(b.portfolio_return_pct)}</td><td class="${cls(b.alpha_pct)}">${sign(b.alpha_pct)}%</td></tr>`).join('')+'</tbody>';
  }
}
