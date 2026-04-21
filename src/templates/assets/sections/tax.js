// --- Tax section ---
(function() {
  const tby = D.tax_by_year || {};
  const years = Object.keys(tby).map(Number).sort((a, b) => a - b);
  if (!years.length) return;

  let currentYear = years[years.length - 1]; // default to most recent

  // Build year selector buttons
  const bar = document.getElementById('taxYearBar');
  if (bar) {
    years.forEach(function(yr) {
      const btn = document.createElement('button');
      btn.className = 'range-btn' + (yr === currentYear ? ' active' : '');
      btn.textContent = yr;
      btn.addEventListener('click', function() {
        currentYear = yr;
        bar.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        renderTax();
      });
      bar.appendChild(btn);
    });
  }

  // Client-side netting: bucket by (asset_class, tax_rate), losses stay within class
  function computeTax(sales) {
    const buckets = {};
    let totalGain = 0;
    for (const s of sales) {
      const gainAfterCosts = s.gain_eur > 0
        ? Math.max(0, s.gain_eur - s.std_costs_eur)
        : s.gain_eur;
      const key = s.asset_class + '|' + s.tax_rate;
      buckets[key] = (buckets[key] || 0) + gainAfterCosts;
      totalGain += s.gain_eur;
    }
    // Slovenian crypto exemption: total net crypto gain < 5000 EUR → 0% tax
    const totalCryptoNet = Object.entries(buckets)
      .filter(([k]) => k.startsWith('crypto|'))
      .reduce((sum, [, net]) => sum + net, 0);
    const cryptoExempt = totalCryptoNet < 5000;

    let totalTax = 0;
    for (const [key, net] of Object.entries(buckets)) {
      const ac = key.split('|')[0];
      if (ac === 'crypto' && cryptoExempt) continue;
      const rate = parseFloat(key.split('|')[1]);
      totalTax += Math.max(0, net) * rate;
    }
    return { totalGain, totalTax, cryptoExempt };
  }

  function renderTax() {
    const t = tby[currentYear];
    if (!t) return;

    document.getElementById('taxSection').style.display = '';

    // Filter sales by active asset classes
    const sales = isDefaultSelection()
      ? t.realized_sales
      : t.realized_sales.filter(s => activeClasses.has(s.asset_class));

    const { totalGain, totalTax, cryptoExempt } = computeTax(sales);

    // Dividends & fees are stored as year-level totals (not per-class)
    const showTotals = isDefaultSelection();

    const exemptionNote = cryptoExempt
      ? `<div class="metric-card" style="grid-column:1/-1;background:var(--card-bg);border:1px solid var(--pos);color:var(--pos);font-size:0.78rem;padding:0.5rem 0.75rem;border-radius:6px">
           ℹ️ Crypto gains below 5 000 EUR threshold — exempt from tax (ZDoh-2, čl. 97)
         </div>` : '';

    document.getElementById('taxCards').innerHTML = [
      ['Tax Year',      currentYear,                                        ''],
      ['Realized Gain', sign(totalGain) + ' EUR',                           cls(totalGain)],
      ['Realized Tax',  fmtEur(totalTax),                                   ''],
      ['Dividends',     showTotals ? fmtEur(t.total_dividends_eur) : '—',   ''],
      ['Fees',          showTotals ? sign(t.total_fees_eur) + ' EUR' : '—', cls(t.total_fees_eur)],
      ['Total Tax',     fmtEur(totalTax),                                   'neg'],
    ].map(([l, v, c]) =>
      `<div class="metric-card"><div class="label">${l}</div><div class="value ${c}">${v}</div></div>`
    ).join('') + exemptionNote;

    const tt = document.getElementById('taxTable');
    if (sales.length > 0) {
      tt.innerHTML =
        '<thead><tr><th>Ticker</th><th>Date</th><th>Qty</th><th>Proceeds</th>' +
        '<th>Cost Basis</th><th>Gain</th><th>Std Costs</th><th>Held</th><th>Rate</th><th>Tax</th></tr></thead><tbody>' +
        sales.map(s =>
          `<tr>` +
          `<td>${s.ticker}</td>` +
          `<td>${s.sell_date}</td>` +
          `<td>${fmt(s.quantity, 4)}</td>` +
          `<td>${fmtEur(s.sell_price_eur)}</td>` +
          `<td>${fmtEur(s.cost_basis_eur)}</td>` +
          `<td class="${cls(s.gain_eur)}">${sign(s.gain_eur)} EUR</td>` +
          `<td style="color:var(--muted)">${s.std_costs_eur > 0 ? '-' + fmt(s.std_costs_eur) + ' EUR' : '—'}</td>` +
          `<td>${fmt(s.holding_years, 1)}y</td>` +
          `<td>${Math.round(s.tax_rate * 100)}%</td>` +
          `<td>${fmtEur(s.tax_eur)}</td>` +
          `</tr>`
        ).join('') +
        '</tbody>';
      makeSortable(tt);
    } else {
      tt.innerHTML = '<tbody><tr><td colspan="10" style="color:var(--muted);text-align:center;padding:2rem">No realized sales for this year / filter</td></tr></tbody>';
    }
  }

  // --- Export functionality (client-side, works in standalone HTML too) ---
  const exportBar = document.getElementById('taxExportBar');
  const exportBtn = document.getElementById('taxExportBtn');
  const exportSel = document.getElementById('taxExportSelect');
  if (exportBar) {
    exportBar.style.display = '';
    exportBtn.addEventListener('click', function() {
      const t = tby[currentYear];
      if (!t || !t.realized_sales || t.realized_sales.length === 0) return;

      const format = exportSel.value;
      if (format === 'fifo-csv') {
        _exportFifoCsv(t, currentYear);
      } else {
        // Try server-side export first (web mode), fall back to client-side CSV
        if (D.user && D.user.role && D.user.role !== 'guest') {
          const a = document.createElement('a');
          a.href = '/export/edavki?year=' + currentYear;
          a.download = '';
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
        } else {
          _exportFifoCsv(t, currentYear);
        }
      }
    });
  }

  function _exportFifoCsv(t, year) {
    const sales = isDefaultSelection()
      ? t.realized_sales
      : t.realized_sales.filter(function(s) { return activeClasses.has(s.asset_class); });
    if (sales.length === 0) return;
    const header = 'Ticker,Sell Date,Quantity,Proceeds (EUR),Cost Basis (EUR),Gain (EUR),Std Costs (EUR),Holding Years,Tax Rate,Tax (EUR),Asset Class';
    const rows = sales.map(function(s) {
      return [
        s.ticker, s.sell_date, s.quantity, s.sell_price_eur, s.cost_basis_eur,
        s.gain_eur, s.std_costs_eur, s.holding_years, Math.round(s.tax_rate * 100) + '%',
        s.tax_eur, s.asset_class || ''
      ].join(',');
    });
    const csv = header + '\n' + rows.join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'tax_fifo_' + year + '.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
  }

  // Expose so updateAll() can call it
  window.updateTaxTable = renderTax;
  renderTax();
})();
