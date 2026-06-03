// --- Transaction history ---
const PAGE_SIZE = 20;
let txPage = 0, txFiltered = [], txDateFiltered = [];
const txTable = scopedFind(null, 'txTable');
const txPag = scopedFind(null, 'txPagination');
const txCountEl = scopedFind(null, 'txCount');
const txFilterEl = scopedFind(null, 'txFilter');

function getDateFilteredTx() {
  let txs = D.transactions;
  if (hasFilter && !isDefaultSelection()) {
    txs = txs.filter(t => activeClasses.has(t.asset_class));
  }
  if (!isZoomed) return txs;
  const sd = allDates[selStart], ed = allDates[selEnd];
  return txs.filter(t => t.date >= sd && t.date <= ed);
}

function applyTxFilter() {
  txDateFiltered = getDateFilteredTx();
  const q = txFilterEl.value.toUpperCase();
  txFiltered = q
    ? txDateFiltered.filter(t => (t.ticker && t.ticker.toUpperCase().includes(q)) || (t.type && t.type.toUpperCase().includes(q)))
    : txDateFiltered;
  txPage = 0;
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

function updateTransactions() { updateTxStats(); applyTxFilter(); }

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
window.txGoTo = function(page) { txPage = page; renderTxPage(); };
window.txGo = function(dir) { txPage = Math.max(0, txPage + dir); renderTxPage(); };
txFilterEl.addEventListener('input', function() { applyTxFilter(); });
