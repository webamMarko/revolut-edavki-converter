// --- Transaction history ---
const PAGE_SIZE = 50;
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
  const trades = txs.filter(t => t.type === 'BUY' || t.type === 'SELL');
  if (trades.length < 2) { section.style.display = 'none'; return; }
  section.style.display = '';

  const buys = trades.filter(t => t.type === 'BUY');
  const sells = trades.filter(t => t.type === 'SELL');

  // Average trade size
  const amounts = trades.filter(t => t.total_amount != null).map(t => Math.abs(t.total_amount));
  const avgSize = amounts.length > 0 ? amounts.reduce((a, b) => a + b, 0) / amounts.length : 0;

  // Most traded ticker
  const tickerCount = {};
  trades.forEach(t => { if (t.ticker) tickerCount[t.ticker] = (tickerCount[t.ticker] || 0) + 1; });
  const topTicker = Object.entries(tickerCount).sort((a, b) => b[1] - a[1])[0];

  // Unique tickers traded
  const uniqueTickers = Object.keys(tickerCount).length;

  // Trading frequency: trades per month
  const firstDate = trades[trades.length - 1].date;
  const lastDate = trades[0].date;
  const months = Math.max(1, (new Date(lastDate) - new Date(firstDate)) / (30.44 * 86400000));
  const tradesPerMonth = trades.length / months;

  // Dividend transactions
  const divTypes = new Set(['DIVIDEND', 'BOND COUPON', 'INTEREST PAID', 'STAKING REWARD', 'LEARN REWARD']);
  const dividends = txs.filter(t => divTypes.has(t.type));

  const el = scopedFind(null, 'txStats');
  const cards = [
    [t('tx.total_trades'), trades.length, ''],
    [t('tx.buys_sells'), buys.length + ' / ' + sells.length, ''],
    [t('tx.avg_trade_size'), fmtCcy(avgSize), ''],
    [t('tx.trades_month'), fmt(tradesPerMonth, 1), ''],
    [t('tx.unique_tickers'), uniqueTickers, ''],
    [t('tx.most_traded'), topTicker ? topTicker[0] : '—', '', topTicker ? topTicker[1] + ' ' + t('tx.trades') : ''],
    [t('tx.dividends_received'), dividends.length, ''],
  ];
  el.innerHTML = cards.map(([l, v, c, sub]) =>
    `<div class="metric-card"><div class="label">${l}</div><div class="value ${c || ''}">${v}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`
  ).join('');
}

function updateTransactions() { updateTxStats(); applyTxFilter(); }

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
  txPag.innerHTML = totalPages > 1
    ? `<button onclick="txGo(-1)" ${txPage===0?'disabled':''}>← ${t('tx.prev')}</button><span>${t('tx.page_of',{page:txPage+1,total:totalPages})}</span><button onclick="txGo(1)" ${txPage>=totalPages-1?'disabled':''}>${ t('tx.next')} →</button>`
    : '';
  makeSortable(txTable);
}
window.txGo = function(dir) { txPage = Math.max(0, txPage + dir); renderTxPage(); };
txFilterEl.addEventListener('input', function() { applyTxFilter(); });
