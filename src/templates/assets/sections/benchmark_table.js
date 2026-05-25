// --- Benchmark table ---
function _fmtMetric(v) { return v != null ? v.toFixed(2) : '—'; }

function updateBenchmarkTable() {
  if (bKeys.length === 0) return;
  const bt = scopedFind(null, 'benchmarkTable');
  const portSharpe = D.summary && D.summary.risk_metrics ? D.summary.risk_metrics.sharpe_ratio : null;
  const portDD = D.summary ? D.summary.max_drawdown_pct : null;
  const hdr = '<thead><tr><th>Benchmark</th><th>Return</th><th>Portfolio</th><th>Alpha</th><th>Sharpe</th><th>Port. Sharpe</th><th>Max DD</th><th>Port. DD</th></tr></thead>';
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
      const bm = D.benchmarks.find(x => x.name === b.name);
      rows.push({name: b.name, benchRet, portfolioRet, alpha,
        sharpe: bm ? bm.sharpe_ratio : null, maxDD: bm ? bm.max_drawdown_pct : null});
    });
    bt.innerHTML = hdr + '<tbody>' +
      rows.map(r => `<tr><td>${r.name}</td><td>${sign(r.benchRet)}%</td><td>${sign(r.portfolioRet)}%</td><td class="${cls(r.alpha)}">${sign(r.alpha)}%</td><td>${_fmtMetric(r.sharpe)}</td><td>${_fmtMetric(portSharpe)}</td><td>${_fmtMetric(r.maxDD)}%</td><td>${_fmtMetric(portDD)}%</td></tr>`).join('') + '</tbody>';
  } else {
    bt.innerHTML = hdr + '<tbody>' +
      D.benchmarks.map(b => `<tr><td>${b.name}</td><td>${pct(b.return_pct)}</td><td>${pct(b.portfolio_return_pct)}</td><td class="${cls(b.alpha_pct)}">${sign(b.alpha_pct)}%</td><td>${_fmtMetric(b.sharpe_ratio)}</td><td>${_fmtMetric(portSharpe)}</td><td>${_fmtMetric(b.max_drawdown_pct)}%</td><td>${_fmtMetric(portDD)}%</td></tr>`).join('') + '</tbody>';
  }
}
