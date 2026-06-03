// --- Transaction history ---
const PAGE_SIZE = 20;
let txPage = 0, txFiltered = [], txDateFiltered = [];
let txTypeFilter = new Set();
const txTable = scopedFind(null, 'txTable');
const txPag = scopedFind(null, 'txPagination');
const txCountEl = scopedFind(null, 'txCount');
const txFilterEl = scopedFind(null, 'txFilter');
const txDateFromEl = scopedFind(null, 'txDateFrom');
const txDateToEl = scopedFind(null, 'txDateTo');
const txSortEl = scopedFind(null, 'txSort');
const txTypeChipsEl = scopedFind(null, 'txTypeChips');

function getDateFilteredTx() {
  let txs = D.transactions;
  if (hasFilter && !isDefaultSelection()) {
    txs = txs.filter(t => activeClasses.has(t.asset_class));
  }
  if (!isZoomed) return txs;
  const sd = allDates[selStart], ed = allDates[selEnd];
  return txs.filter(t => t.date >= sd && t.date <= ed);
}

function sortTxArray(arr) {
  const key = txSortEl ? txSortEl.value : 'date-desc';
  const copy = arr.slice();
  if (key === 'date-asc')    return copy.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
  if (key === 'amount-desc') return copy.sort((a, b) => (b.total_amount || 0) - (a.total_amount || 0));
  if (key === 'amount-asc')  return copy.sort((a, b) => (a.total_amount || 0) - (b.total_amount || 0));
  if (key === 'type')        return copy.sort((a, b) => (a.type || '').localeCompare(b.type || ''));
  return copy.sort((a, b) => (a.date > b.date ? -1 : a.date < b.date ? 1 : 0)); // date-desc default
}

function buildTypeChips() {
  if (!txTypeChipsEl) return;
  const types = [...new Set((D.transactions || []).map(t => t.type).filter(Boolean))].sort();
  if (!types.length) { txTypeChipsEl.innerHTML = ''; return; }
  txTypeChipsEl.innerHTML = types.map(type =>
    `<button class="tx-type-chip${txTypeFilter.has(type) ? ' active' : ''}" data-type="${type}">${type}</button>`
  ).join('');
  txTypeChipsEl.querySelectorAll('.tx-type-chip').forEach(btn => {
    btn.addEventListener('click', () => {
      const type = btn.dataset.type;
      if (txTypeFilter.has(type)) txTypeFilter.delete(type); else txTypeFilter.add(type);
      btn.classList.toggle('active', txTypeFilter.has(type));
      txPage = 0;
      applyTxFilter();
      pushTxUrlState();
    });
  });
}

function applyTxFilter() {
  txDateFiltered = getDateFilteredTx();
  const q = txFilterEl.value.toUpperCase();
  const fromDate = txDateFromEl ? txDateFromEl.value : '';
  const toDate   = txDateToEl   ? txDateToEl.value   : '';
  let filtered = txDateFiltered;
  if (q)            filtered = filtered.filter(t => (t.ticker && t.ticker.toUpperCase().includes(q)) || (t.type && t.type.toUpperCase().includes(q)));
  if (fromDate)     filtered = filtered.filter(t => t.date >= fromDate);
  if (toDate)       filtered = filtered.filter(t => t.date <= toDate);
  if (txTypeFilter.size > 0) filtered = filtered.filter(t => txTypeFilter.has(t.type));
  txFiltered = sortTxArray(filtered);
  renderTxPage();
}

function updateTxStats() {
  const section = scopedFind(null, 'txStatsSection');
  const txs = getDateFilteredTx();
  section.style.display = '';

  const divTypes = new Set(['DIVIDEND', 'BOND COUPON', 'INTEREST PAID', 'STAKING REWARD', 'LEARN REWARD']);
  const dividends = txs.filter(t => divTypes.has(t.type));

  const netPnl = (D.analytics && D.analytics.total_gain_eur != null) ? D.analytics.total_gain_eur : 0;
  const pnlCls = netPnl >= 0 ? 'pos' : 'neg';

  const el = scopedFind(null, 'txStats');
  const cards = [
    [t('tx.total_transactions'), txs.length, ''],
    [t('tx.net_pnl'), fmtCcy(netPnl), pnlCls],
    [t('tx.dividends_received'), dividends.length, ''],
  ];
  el.innerHTML = cards.map(([l, v, c]) =>
    `<div class="metric-card"><div class="label">${l}</div><div class="value ${c || ''}">${v}</div></div>`
  ).join('');
}

function pushTxUrlState() {
  const params = new URLSearchParams(window.location.search);
  if (txPage > 0) params.set('page', txPage + 1); else params.delete('page');
  if (txTypeFilter.size > 0) params.set('type', [...txTypeFilter].sort().join(',')); else params.delete('type');
  const df = txDateFromEl && txDateFromEl.value;
  if (df) params.set('dateFrom', df); else params.delete('dateFrom');
  const dt = txDateToEl && txDateToEl.value;
  if (dt) params.set('dateTo', dt); else params.delete('dateTo');
  const sort = txSortEl && txSortEl.value;
  if (sort && sort !== 'date-desc') params.set('sort', sort); else params.delete('sort');
  const q = txFilterEl && txFilterEl.value;
  if (q) params.set('q', q); else params.delete('q');
  const qs = params.toString();
  history.replaceState(null, '', (qs ? '?' + qs : window.location.pathname) + window.location.hash);
}

function restoreTxUrlState() {
  const params = new URLSearchParams(window.location.search);
  const typeParam = params.get('type');
  if (typeParam) txTypeFilter = new Set(typeParam.split(',').filter(Boolean));
  if (txDateFromEl) { const v = params.get('dateFrom'); if (v) txDateFromEl.value = v; }
  if (txDateToEl)   { const v = params.get('dateTo');   if (v) txDateToEl.value = v; }
  if (txSortEl)     { const v = params.get('sort');     if (v) txSortEl.value = v; }
  if (txFilterEl)   { const v = params.get('q');        if (v) txFilterEl.value = v; }
  return params.has('page') ? Math.max(0, parseInt(params.get('page'), 10) - 1) : 0;
}

function updateTransactions() {
  const restoredPage = restoreTxUrlState();
  txPage = restoredPage;
  buildTypeChips();
  updateTxStats();
  applyTxFilter();
  // Clamp to valid range in case URL page exceeds current data
  const totalPages = Math.ceil(txFiltered.length / PAGE_SIZE);
  if (txPage > 0 && txPage >= totalPages) {
    txPage = Math.max(0, totalPages - 1);
    renderTxPage();
  }
}

function buildTxPagination(totalPages, currentPage) {
  if (totalPages <= 1) return '';
  const shown = new Set([0, totalPages - 1, currentPage - 1, currentPage, currentPage + 1].filter(p => p >= 0 && p < totalPages));
  const sorted = Array.from(shown).sort((a, b) => a - b);
  let html = '';
  let prev = -1;
  sorted.forEach(p => {
    if (prev !== -1 && p > prev + 1) html += '<span class="pagination-ellipsis">…</span>';
    html += `<button onclick="txGoTo(${p})"${p === currentPage ? ' class="active" disabled' : ''}>${p + 1}</button>`;
    prev = p;
  });
  return html;
}

function renderTxPage() {
  const start = txPage * PAGE_SIZE, end = start + PAGE_SIZE;
  const page = txFiltered.slice(start, end);
  const totalPages = Math.ceil(txFiltered.length / PAGE_SIZE);
  txCountEl.textContent = txFiltered.length + ' ' + t('tx.count');
  const tagClsMap = {cfd:'tag-cfd', stock:'tag-stock', crypto:'tag-crypto', savings:'tag-savings'};
  txTable.innerHTML = '<thead><tr><th>'+t('tx.col.date')+'</th><th>'+t('tx.col.ticker')+'</th><th>'+t('tx.col.type')+'</th><th>'+t('tx.col.qty')+'</th><th>'+t('tx.col.price')+'</th><th>'+t('tx.col.amount')+'</th><th>'+t('tx.col.ccy')+'</th><th>'+t('tx.col.fx')+'</th><th>'+t('tx.col.class')+'</th></tr></thead><tbody>'+
    page.map(t => {
      const tagCls = tagClsMap[t.asset_class] || 'tag-stock';
      return `<tr><td>${t.date}</td><td><strong>${t.ticker}</strong></td><td>${t.type}</td><td>${t.quantity!=null?fmt(t.quantity,4):'—'}</td><td>${t.price_per_share!=null?fmt(t.price_per_share,4):'—'}</td><td class="${cls(t.total_amount)}">${t.total_amount!=null?fmt(t.total_amount):'—'}</td><td>${t.currency}</td><td>${t.fx_rate!=null?fmt(t.fx_rate,4):'—'}</td><td><span class="tag ${tagCls}">${t.asset_class}</span></td></tr>`;
    }).join('') + '</tbody>';
  txPag.innerHTML = buildTxPagination(totalPages, txPage);
  makeSortable(txTable);
}
window.txGoTo = function(page) { txPage = page; renderTxPage(); pushTxUrlState(); };
window.txGo = function(dir) { txPage = Math.max(0, txPage + dir); renderTxPage(); pushTxUrlState(); };
txFilterEl.addEventListener('input', function() { txPage = 0; applyTxFilter(); pushTxUrlState(); });
txDateFromEl && txDateFromEl.addEventListener('change', function() { txPage = 0; applyTxFilter(); pushTxUrlState(); });
txDateToEl   && txDateToEl.addEventListener('change', function() { txPage = 0; applyTxFilter(); pushTxUrlState(); });
txSortEl     && txSortEl.addEventListener('change', function() { txPage = 0; applyTxFilter(); pushTxUrlState(); });
