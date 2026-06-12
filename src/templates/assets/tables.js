// --- Sortable tables ---
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
        let av = a.cells[idx].textContent.replace(/[^\d.\-]/g, '');
        let bv = b.cells[idx].textContent.replace(/[^\d.\-]/g, '');
        const an = parseFloat(av), bn = parseFloat(bv);
        if (!isNaN(an) && !isNaN(bn)) return dir === 'asc' ? an - bn : bn - an;
        av = a.cells[idx].textContent; bv = b.cells[idx].textContent;
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
