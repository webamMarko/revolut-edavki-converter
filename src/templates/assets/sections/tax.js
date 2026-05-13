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

  // Lookup brackets for an asset class within an arbitrary regime object
  function _getBrackets(regime, assetClass) {
    const key = assetClass === 'cfd' ? 'cfd_brackets'
               : assetClass === 'crypto' ? 'crypto_brackets'
               : assetClass === 'savings' ? 'savings_brackets'
               : 'stock_brackets';
    return regime[key] || regime.stock_brackets || [{ min_years: 0, rate: 0 }];
  }

  function _getRate(brackets, holdingYears) {
    let rate = brackets[0].rate;
    for (const b of brackets) {
      if (holdingYears >= b.min_years) rate = b.rate;
    }
    return rate;
  }

  // Compute tax for an arbitrary regime object (from D.available_regimes or D.regime)
  function computeTaxForRegime(sales, regime) {
    const buckets = {};
    let totalGain = 0;
    const nettingMode = regime.netting || 'per_class';
    for (const s of sales) {
      const brackets = _getBrackets(regime, s.asset_class);
      const rate = regime.flat_rate != null ? regime.flat_rate : _getRate(brackets, s.holding_years);
      const gainAfterCosts = s.gain_eur > 0
        ? Math.max(0, s.gain_eur - s.std_costs_eur)
        : s.gain_eur;
      const acKey = nettingMode === 'all_classes' ? 'all' : s.asset_class;
      const key = acKey + '|' + rate;
      buckets[key] = (buckets[key] || 0) + gainAfterCosts;
      totalGain += s.gain_eur;
    }
    let cryptoExempt = false;
    if (regime.crypto_exemption_type === 'threshold' && regime.crypto_exemption_threshold != null) {
      const totalCryptoNet = Object.entries(buckets)
        .filter(([k]) => k.startsWith('crypto|'))
        .reduce((sum, [, net]) => sum + net, 0);
      cryptoExempt = totalCryptoNet < regime.crypto_exemption_threshold;
    }
    let totalTax = 0;
    for (const [key, net] of Object.entries(buckets)) {
      const ac = key.split('|')[0];
      if (ac === 'crypto' && cryptoExempt) continue;
      const rate = parseFloat(key.split('|')[1]);
      totalTax += Math.max(0, net) * rate;
    }
    const effectiveRate = totalGain > 0 ? totalTax / totalGain : 0;
    const topRate = sales.length > 0 ? Math.max(...sales.map(s => {
      if (regime.flat_rate != null) return regime.flat_rate;
      return _getRate(_getBrackets(regime, s.asset_class), s.holding_years);
    })) : 0;
    return { totalGain, totalTax, cryptoExempt, effectiveRate, topRate };
  }

  function computeTax(sales) {
    return computeTaxForRegime(sales, _regime);
  }

  // ── Compare regimes ───────────────────────────────────────────────────────
  let _compareMode = false;
  let _compareRegime = null;

  const _compareToggle = document.getElementById('taxCompareToggle');
  const _compareBar = document.getElementById('taxCompareBar');
  const _compareSelect = document.getElementById('taxCompareSelect');
  const _comparePanel = document.getElementById('taxCompareTable');
  const _allRegimes = D.available_regimes || [];
  const _currentCode = D.country || 'SI';

  if (_compareSelect && _allRegimes.length > 1) {
    _allRegimes.forEach(function(r) {
      if (r.code === _currentCode) return;
      const opt = document.createElement('option');
      opt.value = r.code;
      opt.textContent = r.name + ' (' + r.currency + ')';
      _compareSelect.appendChild(opt);
    });
    _compareRegime = _allRegimes.find(r => r.code !== _currentCode) || null;
  }

  if (_compareToggle) {
    _compareToggle.addEventListener('click', function() {
      _compareMode = !_compareMode;
      _compareToggle.classList.toggle('active', _compareMode);
      if (_compareBar) _compareBar.style.display = _compareMode ? 'flex' : 'none';
      if (_comparePanel) {
        _comparePanel.style.display = _compareMode ? '' : 'none';
        if (!_compareMode) _comparePanel.innerHTML = '';
      }
      renderTax();
    });
  }

  if (_compareSelect) {
    _compareSelect.addEventListener('change', function() {
      _compareRegime = _allRegimes.find(r => r.code === _compareSelect.value) || null;
      if (_compareMode) renderTax();
    });
  }

  function renderCompare(sales) {
    if (!_compareMode || !_compareRegime || !_comparePanel) return;
    const regA = _regime;
    const regB = _compareRegime;
    const resA = computeTaxForRegime(sales, regA);
    const resB = computeTaxForRegime(sales, regB);
    const netA = resA.totalGain - resA.totalTax;
    const netB = resB.totalGain - resB.totalTax;

    function _winner(a, b, lowerIsBetter) {
      if (lowerIsBetter) return a < b ? 'a' : b < a ? 'b' : 'tie';
      return a > b ? 'a' : b > a ? 'b' : 'tie';
    }

    const rows = [
      {
        label: 'Total tax liability',
        valA: fmtCcy(resA.totalTax),
        valB: fmtCcy(resB.totalTax),
        winner: _winner(resA.totalTax, resB.totalTax, true),
      },
      {
        label: 'Effective rate',
        valA: pct(+(resA.effectiveRate * 100).toFixed(1)),
        valB: pct(+(resB.effectiveRate * 100).toFixed(1)),
        winner: _winner(resA.effectiveRate, resB.effectiveRate, true),
      },
      {
        label: 'Top bracket applied',
        valA: pct(Math.round(resA.topRate * 1000) / 10),
        valB: pct(Math.round(resB.topRate * 1000) / 10),
        winner: _winner(resA.topRate, resB.topRate, true),
      },
      {
        label: 'Net gain after tax',
        valA: fmtCcy(netA),
        valB: fmtCcy(netB),
        winner: _winner(netA, netB, false),
      },
    ];

    const nameA = (regA.country_name) || _currentCode;
    const nameB = regB.name;

    let html = '<div class="tax-compare-wrap">'
      + '<table class="tax-compare-table">'
      + '<thead><tr>'
      + '<th></th>'
      + '<th><span class="tax-compare-regime-name">' + nameA + '</span><span class="tax-compare-regime-badge">current</span></th>'
      + '<th><span class="tax-compare-regime-name">' + nameB + '</span></th>'
      + '</tr></thead><tbody>';

    for (const row of rows) {
      const clsA = row.winner === 'a' ? ' tax-compare-winner' : '';
      const clsB = row.winner === 'b' ? ' tax-compare-winner' : '';
      const badgeA = row.winner === 'a' ? ' <span class="tax-compare-badge tax-compare-badge-green">&#10003; lower</span>' : '';
      const badgeB = row.winner === 'b' ? ' <span class="tax-compare-badge tax-compare-badge-green">&#10003; lower</span>' : '';
      html += '<tr>'
        + '<td class="tax-compare-label">' + row.label + '</td>'
        + '<td class="tax-compare-val' + clsA + '">' + row.valA + badgeA + '</td>'
        + '<td class="tax-compare-val' + clsB + '">' + row.valB + badgeB + '</td>'
        + '</tr>';
    }

    html += '</tbody></table></div>';
    _comparePanel.innerHTML = html;
    _comparePanel.style.display = '';
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
      ? `<div class="metric-card" style="grid-column:1/-1;background:var(--card-bg);border:1px solid var(--green);color:var(--green);font-size:0.78rem;padding:0.5rem 0.75rem;border-radius:6px">
           ℹ️ ${t('tax.crypto_exempt', {threshold: fmt(exemptionThreshold, 0), currency: _currency})}${exemptionRef ? ' (' + exemptionRef + ')' : ''}
         </div>` : '';

    document.getElementById('taxCards').innerHTML = [
      [t('tax.year'),          currentYear,                                               ''],
      [t('tax.realized_gain'), signCcy(totalGain),                                         cls(totalGain)],
      [t('tax.realized_tax'),  fmtCcy(totalTax),                                          ''],
      [t('tax.dividends'),     showTotals ? fmtCcy(ty.total_dividends_eur) : '—',         ''],
      [t('tax.fees'),          showTotals ? signCcy(ty.total_fees_eur) : '—',              cls(ty.total_fees_eur)],
      [t('tax.total_tax'),     fmtCcy(totalTax),                                          'neg'],
    ].map(([l, v, c]) =>
      `<div class="metric-card"><div class="label">${l}</div><div class="value ${c}">${v}</div></div>`
    ).join('') + exemptionNote;

    renderCompare(sales);

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
          `<td class="${cls(s.gain_eur)}">${signCcy(s.gain_eur)}</td>` +
          `<td style="color:var(--muted)">${s.std_costs_eur > 0 ? '-' + fmt(s.std_costs_eur * _fx) + ' ' + _currency : '—'}</td>` +
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
      } else if (format === 'tax-pdf') {
        if (D.user && D.user.role && D.user.role !== 'guest') {
          const a = document.createElement('a');
          a.href = '/export/tax-pdf?year=' + currentYear + '&country=' + (D.regime ? D.regime.country_code : 'SI');
          a.download = '';
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
        }
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
        s.ticker, s.sell_date, s.quantity,
        +(s.sell_price_eur * _fx).toFixed(2), +(s.cost_basis_eur * _fx).toFixed(2),
        +(s.gain_eur * _fx).toFixed(2), +(s.std_costs_eur * _fx).toFixed(2),
        s.holding_years, Math.round(s.tax_rate * 100) + '%',
        +(s.tax_eur * _fx).toFixed(2), s.asset_class || ''
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

    const washCount = filtered.filter(c => c.wash_sale_risk).length;
    const descText = washCount > 0
      ? t('tax.harvest.desc') + ` (${washCount} with wash-sale risk)`
      : t('tax.harvest.desc');
    document.getElementById('harvestDesc').textContent = descText;

    const totalSaving = filtered.reduce((s, c) => s + c.potential_tax_saving_eur, 0);
    const totalLoss = filtered.reduce((s, c) => s + c.unrealized_loss_eur, 0);
    const totalNetBenefit = filtered.reduce((s, c) => s + (c.net_benefit_eur || 0), 0);

    const cards = [
      [t('tax.harvest.total_saving'), fmtCcy(totalSaving), 'pos'],
      [t('tax.harvest.total_loss'), signCcy(totalLoss), 'neg'],
      [t('tax.harvest.candidates'), filtered.length, ''],
    ];
    if (totalNetBenefit > 0 && totalNetBenefit < totalSaving) {
      cards.push(['Net Benefit (offsets gains)', fmtCcy(totalNetBenefit), 'pos']);
    }
    document.getElementById('harvestCards').innerHTML = cards.map(([l, v, c]) =>
      `<div class="metric-card"><div class="label">${l}</div><div class="value ${c}">${v}</div></div>`
    ).join('');

    const hasNetBenefit = filtered.some(c => c.net_benefit_eur != null);
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
      (hasNetBenefit ? '<th>Net Benefit</th>' : '') +
      '</tr></thead><tbody>' +
      filtered.map(c => {
        let washIcon = '';
        if (c.wash_sale_risk) {
          let tipText = 'Wash-sale risk';
          if (c.wash_sale_trigger_date && c.wash_sale_clear_date) {
            const clearDate = new Date(c.wash_sale_clear_date);
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            const daysLeft = Math.max(0, Math.ceil((clearDate - today) / 86400000));
            tipText = 'Wash-sale applies due to purchase on ' + c.wash_sale_trigger_date + '.' +
              ' Selling before ' + c.wash_sale_clear_date + ' disallows this loss.' +
              (daysLeft > 0 ? ' Wait ' + daysLeft + ' day' + (daysLeft === 1 ? '' : 's') + ' to harvest safely.' : ' Clear date has passed.');
          }
          washIcon = ' <button type="button" class="wash-tooltip-btn" aria-label="Wash-sale warning: ' +
            tipText.replace(/"/g, '&quot;') + '" tabindex="0" title="' +
            tipText.replace(/"/g, '&quot;') + '" style="background:none;border:none;cursor:help;padding:0;font:inherit;color:var(--warn,#e6a817)">&#9888;</button>';
        }
        return `<tr>` +
        `<td><strong>${c.ticker}</strong>${washIcon}</td>` +
        `<td>${c.asset_class}</td>` +
        `<td>${fmt(c.quantity, 4)}</td>` +
        `<td>${fmtCcy(c.cost_basis_eur)}</td>` +
        `<td>${fmtCcy(c.market_value_eur)}</td>` +
        `<td class="neg">${signCcy(c.unrealized_loss_eur)}</td>` +
        `<td>${fmt(c.avg_holding_years, 1)}y</td>` +
        `<td>${Math.round(c.tax_rate * 100)}%</td>` +
        `<td class="pos">${fmtCcy(c.potential_tax_saving_eur)}</td>` +
        (hasNetBenefit ? `<td class="pos">${fmtCcy(c.net_benefit_eur || 0)}</td>` : '') +
        `</tr>`;
      }).join('') +
      '</tbody>';
    makeSortable(ht);
  }

  // Expose so updateAll() can call it
  window.updateTaxTable = function() { renderTax(); renderHarvest(); };
  renderTax();
  renderHarvest();
})();
