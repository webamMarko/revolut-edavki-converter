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

  // Client-side netting: uses D.regime for country-specific rules
  const _regime = D.regime || {};
  function computeTax(sales) {
    const buckets = {};
    let totalGain = 0;
    const nettingMode = _regime.netting || 'per_class';
    for (const s of sales) {
      const gainAfterCosts = s.gain_eur > 0
        ? Math.max(0, s.gain_eur - s.std_costs_eur)
        : s.gain_eur;
      // Netting: all_classes → single bucket, per_class → per asset class
      const acKey = nettingMode === 'all_classes' ? 'all' : s.asset_class;
      const key = acKey + '|' + s.tax_rate;
      buckets[key] = (buckets[key] || 0) + gainAfterCosts;
      totalGain += s.gain_eur;
    }
    // Crypto exemption: threshold-based (e.g. SI: 5000 EUR, DE: 600 EUR)
    let cryptoExempt = false;
    if (_regime.crypto_exemption_type === 'threshold' && _regime.crypto_exemption_threshold != null) {
      const totalCryptoNet = Object.entries(buckets)
        .filter(([k]) => k.startsWith('crypto|'))
        .reduce((sum, [, net]) => sum + net, 0);
      cryptoExempt = totalCryptoNet < _regime.crypto_exemption_threshold;
    }

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
    const ty = tby[currentYear];
    if (!ty) return;

    document.getElementById('taxSection').style.display = '';

    // Filter sales by active asset classes
    const sales = isDefaultSelection()
      ? ty.realized_sales
      : ty.realized_sales.filter(s => activeClasses.has(s.asset_class));

    const { totalGain, totalTax, cryptoExempt } = computeTax(sales);

    // Dividends & fees are stored as year-level totals (not per-class)
    const showTotals = isDefaultSelection();

    const exemptionThreshold = _regime.crypto_exemption_threshold;
    const exemptionRef = (_regime.legal_refs || {}).crypto_exemption || '';
    const exemptionNote = cryptoExempt
      ? `<div class="metric-card" style="grid-column:1/-1;background:var(--card-bg);border:1px solid var(--pos);color:var(--pos);font-size:0.78rem;padding:0.5rem 0.75rem;border-radius:6px">
           ℹ️ ${t('tax.crypto_exempt', {threshold: fmt(exemptionThreshold, 0), currency: _currency})}${exemptionRef ? ' (' + exemptionRef + ')' : ''}
         </div>` : '';

    document.getElementById('taxCards').innerHTML = [
      [t('tax.year'),          currentYear,                                               ''],
      [t('tax.realized_gain'), sign(totalGain) + ' ' + _currency,                         cls(totalGain)],
      [t('tax.realized_tax'),  fmtCcy(totalTax),                                          ''],
      [t('tax.dividends'),     showTotals ? fmtCcy(ty.total_dividends_eur) : '—',         ''],
      [t('tax.fees'),          showTotals ? sign(ty.total_fees_eur) + ' ' + _currency : '—', cls(ty.total_fees_eur)],
      [t('tax.total_tax'),     fmtCcy(totalTax),                                          'neg'],
    ].map(([l, v, c]) =>
      `<div class="metric-card"><div class="label">${l}</div><div class="value ${c}">${v}</div></div>`
    ).join('') + exemptionNote;

    const tt = document.getElementById('taxTable');
    if (sales.length > 0) {
      tt.innerHTML =
        '<thead><tr><th>'+t('tax.col.ticker')+'</th><th>'+t('tax.col.date')+'</th><th>'+t('tax.col.qty')+'</th><th>'+t('tax.col.proceeds')+'</th>' +
        '<th>'+t('tax.col.cost_basis')+'</th><th>'+t('tax.col.gain')+'</th><th>'+t('tax.col.std_costs')+'</th><th>'+t('tax.col.held')+'</th><th>'+t('tax.col.rate')+'</th><th>'+t('tax.col.tax')+'</th></tr></thead><tbody>' +
        sales.map(s =>
          `<tr>` +
          `<td>${s.ticker}</td>` +
          `<td>${s.sell_date}</td>` +
          `<td>${fmt(s.quantity, 4)}</td>` +
          `<td>${fmtCcy(s.sell_price_eur)}</td>` +
          `<td>${fmtCcy(s.cost_basis_eur)}</td>` +
          `<td class="${cls(s.gain_eur)}">${sign(s.gain_eur)} ${_currency}</td>` +
          `<td style="color:var(--muted)">${s.std_costs_eur > 0 ? '-' + fmt(s.std_costs_eur) + ' ' + _currency : '—'}</td>` +
          `<td>${fmt(s.holding_years, 1)}y</td>` +
          `<td>${Math.round(s.tax_rate * 100)}%</td>` +
          `<td>${fmtCcy(s.tax_eur)}</td>` +
          `</tr>`
        ).join('') +
        '</tbody>';
      makeSortable(tt);
    } else {
      tt.innerHTML = '<tbody><tr><td colspan="10" style="color:var(--muted);text-align:center;padding:2rem">' + t('tax.no_sales') + '</td></tr></tbody>';
    }
  }

  // --- Export functionality (client-side, works in standalone HTML too) ---
  const exportBar = document.getElementById('taxExportBar');
  const exportBtn = document.getElementById('taxExportBtn');
  const exportSel = document.getElementById('taxExportSelect');
  if (exportBar) {
    exportBar.style.display = '';
    exportBtn.addEventListener('click', function() {
      const ty = tby[currentYear];
      if (!ty || !ty.realized_sales || ty.realized_sales.length === 0) return;

      const format = exportSel.value;
      if (format === 'fifo-csv') {
        _exportFifoCsv(ty, currentYear);
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
          _exportFifoCsv(ty, currentYear);
        }
      }
    });
  }

  function _exportFifoCsv(taxData, year) {
    const sales = isDefaultSelection()
      ? taxData.realized_sales
      : taxData.realized_sales.filter(function(s) { return activeClasses.has(s.asset_class); });
    if (sales.length === 0) return;
    const header = 'Ticker,Sell Date,Quantity,Proceeds ('+_currency+'),Cost Basis ('+_currency+'),Gain ('+_currency+'),Std Costs ('+_currency+'),Holding Years,Tax Rate,Tax ('+_currency+'),Asset Class';
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

  function renderHarvest() {
    const ty = tby[currentYear];
    if (!ty) return;

    const candidates = ty.harvest_candidates || [];
    const section = document.getElementById('harvestSection');
    if (!section) return;

    // Filter by active asset classes
    const filtered = isDefaultSelection()
      ? candidates
      : candidates.filter(c => activeClasses.has(c.asset_class));

    if (filtered.length === 0) {
      section.style.display = 'none';
      return;
    }

    section.style.display = '';
    document.getElementById('harvestTitle').textContent = t('tax.harvest.title');
    document.getElementById('harvestDesc').textContent = t('tax.harvest.desc');

    const totalSaving = filtered.reduce((s, c) => s + c.potential_tax_saving_eur, 0);
    const totalLoss = filtered.reduce((s, c) => s + c.unrealized_loss_eur, 0);

    document.getElementById('harvestCards').innerHTML = [
      [t('tax.harvest.total_saving'), fmtCcy(totalSaving), 'pos'],
      [t('tax.harvest.total_loss'), sign(totalLoss) + ' ' + _currency, 'neg'],
      [t('tax.harvest.candidates'), filtered.length, ''],
    ].map(([l, v, c]) =>
      `<div class="metric-card"><div class="label">${l}</div><div class="value ${c}">${v}</div></div>`
    ).join('');

    const ht = document.getElementById('harvestTable');
    ht.innerHTML =
      '<thead><tr>' +
      '<th>'+t('tax.harvest.col.ticker')+'</th>' +
      '<th>'+t('tax.harvest.col.class')+'</th>' +
      '<th>'+t('tax.harvest.col.qty')+'</th>' +
      '<th>'+t('tax.harvest.col.cost_basis')+'</th>' +
      '<th>'+t('tax.harvest.col.mkt_value')+'</th>' +
      '<th>'+t('tax.harvest.col.loss')+'</th>' +
      '<th>'+t('tax.harvest.col.held')+'</th>' +
      '<th>'+t('tax.harvest.col.rate')+'</th>' +
      '<th>'+t('tax.harvest.col.saving')+'</th>' +
      '</tr></thead><tbody>' +
      filtered.map(c =>
        `<tr>` +
        `<td><strong>${c.ticker}</strong></td>` +
        `<td>${c.asset_class}</td>` +
        `<td>${fmt(c.quantity, 4)}</td>` +
        `<td>${fmtCcy(c.cost_basis_eur)}</td>` +
        `<td>${fmtCcy(c.market_value_eur)}</td>` +
        `<td class="neg">${sign(c.unrealized_loss_eur)} ${_currency}</td>` +
        `<td>${fmt(c.avg_holding_years, 1)}y</td>` +
        `<td>${Math.round(c.tax_rate * 100)}%</td>` +
        `<td class="pos">${fmtCcy(c.potential_tax_saving_eur)}</td>` +
        `</tr>`
      ).join('') +
      '</tbody>';
    makeSortable(ht);
  }

  // Expose so updateAll() can call it
  window.updateTaxTable = function() { renderTax(); renderHarvest(); };
  renderTax();
  renderHarvest();
})();
