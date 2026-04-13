// --- Monthly heatmap ---
function buildHeatmap() {
  const el = document.getElementById('heatmap');
  if (!el || ds.dates.length === 0) return;
  const dates = ds.dates;
  const hasPerfIdx = ds.perf_index && ds.perf_index.length === dates.length;
  const values = hasPerfIdx ? ds.perf_index : ds.value_eur;
  const monthMap = {};
  for (let i = 0; i < dates.length; i++) {
    const ym = dates[i].substring(0, 7);
    if (!monthMap[ym]) monthMap[ym] = {si: i, ei: i};
    else monthMap[ym].ei = i;
  }
  const yrSet = new Set();
  const years = [];
  Object.keys(monthMap).sort().forEach(function(k) {
    const y = k.substring(0, 4);
    if (!yrSet.has(y)) { yrSet.add(y); years.push(y); }
  });
  const mNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  let maxAbs = 5;
  Object.keys(monthMap).forEach(function(ym) {
    const d = monthMap[ym];
    if (values[d.si] > 0) { const r = Math.abs((values[d.ei]/values[d.si]-1)*100); if (r > maxAbs) maxAbs = r; }
  });
  maxAbs = Math.min(maxAbs, 20);
  function cellBg(ret) {
    const intensity = Math.min(Math.abs(ret)/maxAbs, 1);
    const alpha = (0.12 + 0.78*intensity).toFixed(2);
    return ret >= 0 ? 'rgba(52,211,153,'+alpha+')' : 'rgba(248,113,113,'+alpha+')';
  }
  function cellFg(ret) {
    return Math.min(Math.abs(ret)/maxAbs, 1) > 0.5 ? '#fff' : 'var(--text)';
  }
  let h = '<div class="heatmap-wrap"><table class="heatmap-table"><thead><tr><th></th>';
  mNames.forEach(function(m) { h += '<th>' + m + '</th>'; });
  h += '<th class="heatmap-year-col">Year</th></tr></thead><tbody>';
  years.forEach(function(year) {
    h += '<tr><td class="heatmap-year-label">' + year + '</td>';
    let ySi = null, yEi = null;
    for (let m = 1; m <= 12; m++) {
      const ym = year + '-' + (m < 10 ? '0' : '') + m;
      const d = monthMap[ym];
      if (!d || values[d.si] <= 0) { h += '<td class="heatmap-empty"></td>'; continue; }
      const ret = (values[d.ei]/values[d.si]-1)*100;
      const s = ret >= 0 ? '+' : '';
      h += '<td class="heatmap-cell" style="background:'+cellBg(ret)+';color:'+cellFg(ret)+'" title="'+ym+': '+s+ret.toFixed(2)+'%">'+s+ret.toFixed(1)+'%</td>';
      if (ySi === null) ySi = d.si;
      yEi = d.ei;
    }
    if (ySi !== null && values[ySi] > 0) {
      const ret = (values[yEi]/values[ySi]-1)*100;
      const s = ret >= 0 ? '+' : '';
      h += '<td class="heatmap-cell heatmap-year-cell" style="background:'+cellBg(ret)+';color:'+cellFg(ret)+'"><strong>'+s+ret.toFixed(1)+'%</strong></td>';
    } else { h += '<td></td>'; }
    h += '</tr>';
  });
  h += '</tbody></table></div>';
  el.innerHTML = h;
}
