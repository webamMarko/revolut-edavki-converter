// --- Sortable tables ---
function _parseSortNum(text) {
  let n = text.trim().replace(/[€$£¥%\s]/g, '');
  if (!n || n === '—') return NaN;
  const dots = (n.match(/\./g) || []).length;
  const commas = (n.match(/,/g) || []).length;
  if (dots > 1) {
    // e.g. 1.234.567 or 1.234.567,89 — dot is thousands separator
    n = n.replace(/\./g, '');
    if (commas === 1) n = n.replace(',', '.');
  } else if (commas > 1) {
    // e.g. 1,234,567 or 1,234,567.89 — comma is thousands separator
    n = n.replace(/,/g, '');
  } else if (dots === 1 && commas === 1) {
    // both present — last one is the decimal separator
    const di = n.lastIndexOf('.'), ci = n.lastIndexOf(',');
    if (ci > di) { n = n.replace('.', '').replace(',', '.'); } // European 1.234,56
    else         { n = n.replace(',', ''); }                   // US 1,234.56
  } else if (commas === 1 && dots === 0) {
    // single comma only — treat as decimal (European)
    n = n.replace(',', '.');
  }
  return parseFloat(n);
}

function makeSortable(table) {
  const ths = table.querySelectorAll('th');
  ths.forEach((th, idx) => {
    const arrow = document.createElement('span');
    arrow.className = 'arrow';
    th.appendChild(arrow);
    th.addEventListener('click', function() {
      const tbody = table.querySelector('tbody');
      if (!tbody) return;
      const rows = Array.from(tbody.rows);
      const dir = th.dataset.dir === 'asc' ? 'desc' : 'asc';
      ths.forEach(h => { h.dataset.dir = ''; h.querySelector('.arrow').textContent = ''; });
      th.dataset.dir = dir;
      th.querySelector('.arrow').textContent = dir === 'asc' ? '▲' : '▼';
      rows.sort((a, b) => {
        const an = _parseSortNum(a.cells[idx].textContent);
        const bn = _parseSortNum(b.cells[idx].textContent);
        if (!isNaN(an) && !isNaN(bn)) return dir === 'asc' ? an - bn : bn - an;
        const av = a.cells[idx].textContent, bv = b.cells[idx].textContent;
        return dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
      });
      rows.forEach(r => tbody.appendChild(r));
    });
  });
}

// --- Range buttons ---
(function() {
  const bar = scopedFind(null, 'rangeBar');
  if (!bar) return;
  bar.addEventListener('click', function(e) {
    const btn = e.target.closest('.range-btn');
    if (!btn) return;
    bar.querySelectorAll('.range-btn').forEach(function(b) { b.classList.remove('active'); });
    btn.classList.add('active');
    const days = parseInt(btn.dataset.days);
    const ytd = btn.dataset.ytd === '1';
    if (days === -1) {
      applyAllRange();
      return;
    }
    let targetStart;
    if (ytd) {
      const lastDate = new Date(allDates[N-1]);
      targetStart = new Date(lastDate.getFullYear(), 0, 1);
    } else {
      const endDate = new Date(allDates[N-1]);
      targetStart = new Date(endDate.getTime() - days * 86400000);
    }
    let si = 0;
    for (let i = 0; i < N; i++) { if (new Date(allDates[i]) >= targetStart) { si = i; break; } }
    selStart = si; selEnd = N - 1; isZoomed = true;
    const startMs = new Date(allDates[si]).getTime();
    const endMs   = new Date(allDates[N-1]).getTime();
    if (portfolioChart) {
      portfolioChart.options.scales.x.min = startMs;
      portfolioChart.options.scales.x.max = endMs;
      portfolioChart.update('none');
    }
    updateAll();
  });
})();
