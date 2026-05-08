// --- Tax Liability Preview ---
(function() {
  const tby = D.tax_by_year || {};
  const positions = D.positions || [];
  const lots = D.position_lots || {};
  const regime = D.regime || {};
  const section = document.getElementById('taxPreviewSection');
  if (!section || positions.length === 0) return;

  const currentYear = new Date().getFullYear();
  const today = new Date();

  function getBrackets(assetClass) {
    if (assetClass === 'cfd') return regime.cfd_brackets || [];
    if (assetClass === 'crypto') return regime.crypto_brackets || [];
    if (assetClass === 'savings') return regime.savings_brackets || [];
    return regime.stock_brackets || [];
  }

  function getRateForHolding(brackets, holdingYears) {
    if (!brackets || brackets.length === 0) return 0.25;
    let rate = brackets[0].rate;
    for (const b of brackets) {
      if (holdingYears >= b.min_years) rate = b.rate;
    }
    return rate;
  }

  function getAssetClass(ticker) {
    if (ticker.startsWith('CFD:')) return 'cfd';
    if (ticker.startsWith('CRYPTO:')) return 'crypto';
    if (ticker.startsWith('SAVINGS:')) return 'savings';
    return 'stock';
  }

  function getBracketLabel(brackets, holdingYears) {
    if (!brackets || brackets.length === 0) return '0y+';
    let matched = brackets[0];
    for (let i = 0; i < brackets.length; i++) {
      if (holdingYears >= brackets[i].min_years) matched = brackets[i];
    }
    const idx = brackets.indexOf(matched);
    const next = brackets[idx + 1];
    if (next) return matched.min_years + '-' + next.min_years + 'y';
    return matched.min_years + 'y+';
  }

  function computePositionTaxDetails(ticker, sellPct) {
    const posLots = lots[ticker] || [];
    if (posLots.length === 0) return null;

    const pos = positions.find(function(p) { return p.ticker === ticker; });
    if (!pos || pos.quantity <= 0) return null;

    const ac = getAssetClass(ticker);
    const brackets = getBrackets(ac);
    const qtyToSell = pos.quantity * (sellPct / 100);
    const pricePerShare = pos.market_value_eur / pos.quantity;

    let remaining = qtyToSell;
    let totalCost = 0;
    let weightedDays = 0;
    const lotDetails = [];

    for (const lot of posLots) {
      if (remaining <= 0) break;
      const matched = Math.min(lot.qty, remaining);
      const lotDate = new Date(lot.date);
      const holdingDays = (today - lotDate) / (1000 * 60 * 60 * 24);
      const holdingYears = holdingDays / 365.25;
      const cost = matched * lot.cost_eur;
      const proceeds = matched * pricePerShare;
      const gain = proceeds - cost;
      const rate = getRateForHolding(brackets, holdingYears);
      const stdCostRate = ac === 'cfd' ? (regime.std_cost_rate_leveraged || 0.0025) : (regime.std_cost_rate || 0.01);
      const stdCosts = gain > 0 ? stdCostRate * (cost + proceeds) : 0;
      const taxableGain = gain > 0 ? Math.max(0, gain - stdCosts) : gain;
      const tax = Math.max(0, taxableGain * rate);

      lotDetails.push({
        qty: matched, cost: cost, proceeds: proceeds,
        gain: gain, stdCosts: stdCosts, holdingYears: holdingYears,
        rate: rate, tax: tax, bracketLabel: getBracketLabel(brackets, holdingYears)
      });

      totalCost += cost;
      weightedDays += matched * holdingDays;
      remaining -= matched;
    }

    const totalProceeds = qtyToSell * pricePerShare;
    const totalGain = totalProceeds - totalCost;
    const avgHoldingYears = qtyToSell > 0 ? (weightedDays / qtyToSell) / 365.25 : 0;
    const totalTax = lotDetails.reduce(function(s, d) { return s + d.tax; }, 0);

    const nextBracket = findNextBracket(brackets, avgHoldingYears);

    return {
      ticker: ticker,
      assetClass: ac,
      quantity: qtyToSell,
      totalCost: totalCost,
      totalProceeds: totalProceeds,
      totalGain: totalGain,
      totalTax: totalTax,
      avgHoldingYears: avgHoldingYears,
      currentRate: getRateForHolding(brackets, avgHoldingYears),
      lotDetails: lotDetails,
      nextBracket: nextBracket,
    };
  }

  function findNextBracket(brackets, currentYears) {
    if (!brackets || brackets.length <= 1) return null;
    for (let i = 0; i < brackets.length; i++) {
      if (brackets[i].min_years > currentYears) {
        const daysUntil = Math.ceil((brackets[i].min_years - currentYears) * 365.25);
        const targetDate = new Date(today.getTime() + daysUntil * 24 * 60 * 60 * 1000);
        return {
          rate: brackets[i].rate,
          minYears: brackets[i].min_years,
          daysUntil: daysUntil,
          targetDate: targetDate.toISOString().slice(0, 10),
        };
      }
    }
    return null;
  }

  function computeYTDBracketBreakdown() {
    const yearTax = tby[currentYear];
    const sales = yearTax ? yearTax.realized_sales : [];

    // Group realized sales by bracket
    const bracketMap = {};
    for (const s of sales) {
      if (!isDefaultSelection() && !activeClasses.has(s.asset_class)) continue;
      const brackets = getBrackets(s.asset_class);
      const label = getBracketLabel(brackets, s.holding_years);
      const rate = s.tax_rate;
      const key = label + '|' + Math.round(rate * 100);
      if (!bracketMap[key]) {
        bracketMap[key] = { label: label, rate: rate, gain: 0, tax: 0, count: 0, stdCosts: 0 };
      }
      bracketMap[key].gain += s.gain_eur;
      bracketMap[key].stdCosts += s.std_costs_eur;
      bracketMap[key].count++;
      const gainAfterCosts = s.gain_eur > 0 ? Math.max(0, s.gain_eur - s.std_costs_eur) : s.gain_eur;
      bracketMap[key].tax += Math.max(0, gainAfterCosts * rate);
    }

    // Add unrealized positions grouped by bracket
    const unrealizedMap = {};
    for (const pos of positions) {
      if (pos.quantity <= 0) continue;
      if (!isDefaultSelection() && !activeClasses.has(getAssetClass(pos.ticker))) continue;
      const ac = getAssetClass(pos.ticker);
      const posLots = lots[pos.ticker] || [];
      if (posLots.length === 0) continue;

      let weightedDays = 0;
      let totalQty = 0;
      for (const lot of posLots) {
        const lotDate = new Date(lot.date);
        const days = (today - lotDate) / (1000 * 60 * 60 * 24);
        weightedDays += lot.qty * days;
        totalQty += lot.qty;
      }
      const avgYears = totalQty > 0 ? (weightedDays / totalQty) / 365.25 : 0;
      const brackets = getBrackets(ac);
      const rate = getRateForHolding(brackets, avgYears);
      const label = getBracketLabel(brackets, avgYears);
      const key = label + '|' + Math.round(rate * 100);

      const gain = pos.unrealized_gain_eur;
      const estTax = gain > 0 ? gain * rate : 0;

      if (!unrealizedMap[key]) {
        unrealizedMap[key] = { label: label, rate: rate, gain: 0, tax: 0, count: 0 };
      }
      unrealizedMap[key].gain += gain;
      unrealizedMap[key].tax += estTax;
      unrealizedMap[key].count++;
    }

    return { realized: Object.values(bracketMap), unrealized: Object.values(unrealizedMap) };
  }

  function renderPreview() {
    section.style.display = '';
    document.getElementById('taxPreviewTitle').textContent = t('tax_preview.title');
    document.getElementById('taxPreviewDesc').textContent = t('tax_preview.desc');

    const yearTax = tby[currentYear];
    const sales = yearTax ? yearTax.realized_sales : [];
    const filteredSales = isDefaultSelection()
      ? sales
      : sales.filter(function(s) { return activeClasses.has(s.asset_class); });

    // YTD realized totals
    const realizedGain = filteredSales.reduce(function(s, x) { return s + x.gain_eur; }, 0);
    const realizedTax = filteredSales.reduce(function(s, x) { return s + x.tax_eur; }, 0);

    // Unrealized totals
    const filteredPositions = isDefaultSelection()
      ? positions
      : positions.filter(function(p) { return activeClasses.has(getAssetClass(p.ticker)); });
    const unrealizedGain = filteredPositions.reduce(function(s, p) { return s + p.unrealized_gain_eur; }, 0);

    // Estimate unrealized tax using bracket rates
    let unrealizedTax = 0;
    for (const pos of filteredPositions) {
      if (pos.unrealized_gain_eur <= 0) continue;
      const ac = getAssetClass(pos.ticker);
      const posLots = lots[pos.ticker] || [];
      let weightedDays = 0, totalQty = 0;
      for (const lot of posLots) {
        const lotDate = new Date(lot.date);
        weightedDays += lot.qty * ((today - lotDate) / (1000 * 60 * 60 * 24));
        totalQty += lot.qty;
      }
      const avgYears = totalQty > 0 ? (weightedDays / totalQty) / 365.25 : 0;
      const rate = getRateForHolding(getBrackets(ac), avgYears);
      unrealizedTax += pos.unrealized_gain_eur * rate;
    }

    const totalProjectedTax = realizedTax + unrealizedTax;

    document.getElementById('taxPreviewCards').innerHTML = [
      [t('tax_preview.ytd_realized'), signCcy(realizedGain), cls(realizedGain)],
      [t('tax_preview.ytd_tax'), fmtCcy(realizedTax), 'neg'],
      [t('tax_preview.unrealized_gain'), signCcy(unrealizedGain), cls(unrealizedGain)],
      [t('tax_preview.unrealized_tax'), fmtCcy(unrealizedTax), 'neg'],
      [t('tax_preview.projected_total'), fmtCcy(totalProjectedTax), 'neg'],
    ].map(function(x) {
      return '<div class="metric-card"><div class="label">' + x[0] + '</div><div class="value ' + x[2] + '">' + x[1] + '</div></div>';
    }).join('');

    // Bracket breakdown table
    const breakdown = computeYTDBracketBreakdown();
    const bt = document.getElementById('taxBracketTable');
    const allBrackets = breakdown.realized.concat(breakdown.unrealized.map(function(u) {
      return { label: u.label, rate: u.rate, gain: u.gain, tax: u.tax, count: u.count, unrealized: true };
    }));

    if (allBrackets.length > 0) {
      bt.innerHTML =
        '<thead><tr><th>' + t('tax_preview.col.bracket') + '</th><th>' + t('tax_preview.col.rate') + '</th>' +
        '<th>' + t('tax_preview.col.type') + '</th><th>' + t('tax_preview.col.gain') + '</th>' +
        '<th>' + t('tax_preview.col.est_tax') + '</th><th>' + t('tax_preview.col.trades') + '</th></tr></thead><tbody>' +
        allBrackets.map(function(b) {
          var typeLabel = b.unrealized ? t('tax_preview.unrealized') : t('tax_preview.realized');
          return '<tr>' +
            '<td><strong>' + b.label + '</strong></td>' +
            '<td>' + Math.round(b.rate * 100) + '%</td>' +
            '<td style="font-size:0.75rem;color:var(--muted)">' + typeLabel + '</td>' +
            '<td class="' + cls(b.gain) + '">' + signCcy(b.gain) + '</td>' +
            '<td>' + fmtCcy(b.tax) + '</td>' +
            '<td>' + b.count + '</td></tr>';
        }).join('') +
        '</tbody>';
    } else {
      bt.innerHTML = '<tbody><tr><td colspan="6" style="color:var(--muted);text-align:center;padding:2rem">' +
        t('tax_preview.no_data') + '</td></tr></tbody>';
    }

    renderWhatIf();
  }

  // --- What-If Simulator ---
  function renderWhatIf() {
    const sel = document.getElementById('taxWhatIfTicker');
    const slider = document.getElementById('taxWhatIfSlider');
    const qtyLabel = document.getElementById('taxWhatIfQtyValue');

    document.getElementById('taxWhatIfTitle').textContent = t('tax_preview.whatif.title');
    document.getElementById('taxWhatIfTickerLabel').textContent = t('tax_preview.whatif.position');
    document.getElementById('taxWhatIfQtyLabel').textContent = t('tax_preview.whatif.quantity');

    // Populate position selector
    const filteredPositions = isDefaultSelection()
      ? positions
      : positions.filter(function(p) { return activeClasses.has(getAssetClass(p.ticker)); });

    sel.innerHTML = '<option value="">' + t('tax_preview.whatif.select') + '</option>' +
      filteredPositions
        .filter(function(p) { return p.quantity > 0 && lots[p.ticker] && lots[p.ticker].length > 0; })
        .map(function(p) {
          var name = (D.company_names || {})[p.ticker] || p.ticker;
          return '<option value="' + p.ticker + '">' + p.ticker + ' — ' + name + ' (' + fmt(p.quantity, 2) + ')</option>';
        }).join('');

    slider.value = 100;
    qtyLabel.textContent = '100%';

    slider.oninput = function() {
      qtyLabel.textContent = slider.value + '%';
    };
  }

  // Calculate button handler
  document.getElementById('taxWhatIfCalc').addEventListener('click', function() {
    var ticker = document.getElementById('taxWhatIfTicker').value;
    var pct = parseInt(document.getElementById('taxWhatIfSlider').value);
    var resultDiv = document.getElementById('taxWhatIfResult');
    var cardsDiv = document.getElementById('taxWhatIfCards');
    var noteDiv = document.getElementById('taxWhatIfBracketNote');

    if (!ticker) {
      resultDiv.style.display = 'none';
      return;
    }

    var details = computePositionTaxDetails(ticker, pct);
    if (!details) {
      resultDiv.style.display = 'none';
      return;
    }

    resultDiv.style.display = '';

    cardsDiv.innerHTML = [
      [t('tax_preview.whatif.proceeds'), fmtCcy(details.totalProceeds), ''],
      [t('tax_preview.whatif.cost_basis'), fmtCcy(details.totalCost), ''],
      [t('tax_preview.whatif.gain'), signCcy(details.totalGain), cls(details.totalGain)],
      [t('tax_preview.whatif.tax_if_sold'), fmtCcy(details.totalTax), 'neg'],
      [t('tax_preview.whatif.rate'), Math.round(details.currentRate * 100) + '%', ''],
      [t('tax_preview.whatif.held'), fmt(details.avgHoldingYears, 1) + 'y', ''],
    ].map(function(x) {
      return '<div class="metric-card"><div class="label">' + x[0] + '</div><div class="value ' + x[2] + '">' + x[1] + '</div></div>';
    }).join('');

    // Show next bracket info
    if (details.nextBracket && details.totalGain > 0) {
      var savingIfWait = details.totalTax - (details.totalGain > 0 ? Math.max(0, details.totalGain) * details.nextBracket.rate : 0);
      noteDiv.innerHTML = t('tax_preview.whatif.next_bracket', {
        rate: Math.round(details.nextBracket.rate * 100),
        days: details.nextBracket.daysUntil,
        date: details.nextBracket.targetDate,
        saving: fmtCcy(Math.max(0, savingIfWait))
      });
    } else if (details.currentRate === 0) {
      noteDiv.innerHTML = t('tax_preview.whatif.tax_free');
    } else {
      noteDiv.innerHTML = '';
    }
  });

  // Expose for updateAll()
  window.updateTaxPreview = renderPreview;
  renderPreview();
})();
