// --- Transaction history ---
const PAGE_SIZE = 50;
let txPage = 0, txFiltered = [], txDateFiltered = [];
const txTable = document.getElementById('txTable');
const txPag = document.getElementById('txPagination');
const txCountEl = document.getElementById('txCount');
const txFilterEl = document.getElementById('txFilter');

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

function updateTransactions() { applyTxFilter(); }

function renderTxPage() {
  const start = txPage * PAGE_SIZE, end = start + PAGE_SIZE;
  const page = txFiltered.slice(start, end);
  const totalPages = Math.ceil(txFiltered.length / PAGE_SIZE);
  txCountEl.textContent = txFiltered.length + ' transactions';
  const tagClsMap = {cfd:'tag-cfd', stock:'tag-stock', crypto:'tag-crypto', savings:'tag-savings'};
  txTable.innerHTML = '<thead><tr><th>Date</th><th>Ticker</th><th>Type</th><th>Qty</th><th>Price</th><th>Amount</th><th>Ccy</th><th>FX</th><th>Class</th></tr></thead><tbody>'+
    page.map(t => {
      const tagCls = tagClsMap[t.asset_class] || 'tag-stock';
      return `<tr><td>${t.date}</td><td><strong>${t.ticker}</strong></td><td>${t.type}</td><td>${t.quantity!=null?fmt(t.quantity,4):'—'}</td><td>${t.price_per_share!=null?fmt(t.price_per_share,4):'—'}</td><td class="${cls(t.total_amount)}">${t.total_amount!=null?fmt(t.total_amount):'—'}</td><td>${t.currency}</td><td>${t.fx_rate!=null?fmt(t.fx_rate,4):'—'}</td><td><span class="tag ${tagCls}">${t.asset_class}</span></td></tr>`;
    }).join('') + '</tbody>';
  txPag.innerHTML = totalPages > 1
    ? `<button onclick="txGo(-1)" ${txPage===0?'disabled':''}>← Prev</button><span>Page ${txPage+1} of ${totalPages}</span><button onclick="txGo(1)" ${txPage>=totalPages-1?'disabled':''}>Next →</button>`
    : '';
  makeSortable(txTable);
}
window.txGo = function(dir) { txPage = Math.max(0, txPage + dir); renderTxPage(); };
txFilterEl.addEventListener('input', function() { applyTxFilter(); });
