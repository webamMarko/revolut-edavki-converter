// --- Sortable tables ---
function makeSortable(table) {
  const ths = table.querySelectorAll('th');
  ths.forEach((th, idx) => {
    th.innerHTML = th.textContent + ' <span class="arrow"></span>';
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
  const bar = document.getElementById('rangeBar');
  if (!bar) return;
  bar.addEventListener('click', function(e) {
    const btn = e.target.closest('.range-btn');
    if (!btn) return;
    bar.querySelectorAll('.range-btn').forEach(function(b) { b.classList.remove('active'); });
    btn.classList.add('active');
    const days = parseInt(btn.dataset.days);
    const ytd = btn.dataset.ytd === '1';
    if (days === -1) {
      selStart = 0; selEnd = N - 1; isZoomed = false;
      [portfolioChart, benchmarkChart].forEach(function(c) {
        if (!c) return;
        delete c.options.scales.x.min;
        delete c.options.scales.x.max;
        c.update();
      });
      updateAll();
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
    [portfolioChart, benchmarkChart].forEach(function(c) {
      if (!c) return;
      c.options.scales.x.min = startMs;
      c.options.scales.x.max = endMs;
      c.update('none');
    });
    updateAll();
  });
})();
