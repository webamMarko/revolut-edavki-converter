// --- Smart Sell Advisor ---
(function() {
  var positions = D.positions || [];
  var lots = D.position_lots || {};
  var regime = D.regime || {};
  var section = scopedFind(null, 'smartSellSection');
  if (!section) return;

  var today = new Date();
  var MS_PER_DAY = 1000 * 60 * 60 * 24;

  function getBrackets(assetClass) {
    if (assetClass === 'cfd') return regime.cfd_brackets || [];
    if (assetClass === 'crypto') return regime.crypto_brackets || [];
    if (assetClass === 'savings') return regime.savings_brackets || [];
    return regime.stock_brackets || [];
  }

  function getAssetClass(ticker) {
    if (ticker.startsWith('CFD:')) return 'cfd';
    if (ticker.startsWith('CRYPTO:')) return 'crypto';
    if (ticker.startsWith('SAVINGS:')) return 'savings';
    return 'stock';
  }

  function getRateForHolding(brackets, holdingYears) {
    if (!brackets || brackets.length === 0) return 0.25;
    var rate = brackets[0].rate;
    for (var i = 0; i < brackets.length; i++) {
      if (holdingYears >= brackets[i].min_years) rate = brackets[i].rate;
    }
    return rate;
  }

  function findNextBracketForYears(brackets, holdingYears) {
    if (!brackets || brackets.length <= 1) return null;
    for (var i = 0; i < brackets.length; i++) {
      if (brackets[i].min_years > holdingYears) return brackets[i];
    }
    return null;
  }

  function getStdCostRate(assetClass) {
    return assetClass === 'cfd'
      ? (regime.std_cost_rate_leveraged || 0.0025)
      : (regime.std_cost_rate || 0.01);
  }

  function init() {
    scopedFind(null, 'smartSellTitle').textContent = t('smart_sell.title');
    scopedFind(null, 'smartSellDesc').textContent = t('smart_sell.desc');
    scopedFind(null, 'smartSellTickerLabel').textContent = t('smart_sell.ticker_label');
    scopedFind(null, 'smartSellQtyLabel').textContent = t('smart_sell.qty_label');
    scopedFind(null, 'smartSellCalc').textContent = t('smart_sell.analyze');
    scopedFind(null, 'smartSellLotsTitle').textContent = t('smart_sell.lots_title');
    scopedFind(null, 'smartSellWaitTitle').textContent = t('smart_sell.wait_title');
    scopedFind(null, 'smartSellWaitDesc').textContent = t('smart_sell.wait_desc');
    scopedFind(null, 'smartSellEmptyMsg').textContent = t('smart_sell.empty');

    populateTicker();
  }

  function populateTicker() {
    var sel = scopedFind(null, 'smartSellTicker');
    var qtyInput = scopedFind(null, 'smartSellQty');

    var filteredPositions = isDefaultSelection()
      ? positions
      : positions.filter(function(p) { return activeClasses.has(getAssetClass(p.ticker)); });

    sel.innerHTML = '<option value="">' + t('smart_sell.select') + '</option>' +
      filteredPositions
        .filter(function(p) { return p.quantity > 0 && lots[p.ticker] && lots[p.ticker].length > 0; })
        .map(function(p) {
          var name = (D.company_names || {})[p.ticker] || p.ticker;
          return '<option value="' + p.ticker + '">' + p.ticker + ' — ' + name + ' (' + fmt(p.quantity, 2) + ')</option>';
        }).join('');

    sel.onchange = function() {
      var pos = positions.find(function(p) { return p.ticker === sel.value; });
      if (pos) {
        qtyInput.value = pos.quantity;
        qtyInput.max = pos.quantity;
      }
      scopedFind(null, 'smartSellResult').style.display = 'none';
    };
  }

  function analyze() {
    var ticker = scopedFind(null, 'smartSellTicker').value;
    var qtyToSell = parseFloat(scopedFind(null, 'smartSellQty').value);
    var resultDiv = scopedFind(null, 'smartSellResult');
    var emptyDiv = scopedFind(null, 'smartSellEmpty');

    if (!ticker || !qtyToSell || qtyToSell <= 0) {
      resultDiv.style.display = 'none';
      emptyDiv.style.display = '';
      return;
    }

    var pos = positions.find(function(p) { return p.ticker === ticker; });
    if (!pos || pos.quantity <= 0) {
      resultDiv.style.display = 'none';
      emptyDiv.style.display = '';
      return;
    }

    var ac = getAssetClass(ticker);
    var brackets = getBrackets(ac);
    var posLots = lots[ticker] || [];
    if (posLots.length === 0) return;

    var pricePerShare = pos.market_value_eur / pos.quantity;
    var stdCostRate = getStdCostRate(ac);

    // FIFO matching
    var remaining = Math.min(qtyToSell, pos.quantity);
    var lotResults = [];
    var totalCost = 0;
    var totalProceeds = 0;
    var totalTax = 0;
    var totalGain = 0;

    for (var i = 0; i < posLots.length && remaining > 0; i++) {
      var lot = posLots[i];
      var matched = Math.min(lot.qty, remaining);
      var lotDate = new Date(lot.date);
      var holdingDays = Math.floor((today - lotDate) / MS_PER_DAY);
      var holdingYears = holdingDays / 365.25;
      var rate = getRateForHolding(brackets, holdingYears);
      var cost = matched * lot.cost_eur;
      var proceeds = matched * pricePerShare;
      var gain = proceeds - cost;
      var stdCosts = gain > 0 ? stdCostRate * (cost + proceeds) : 0;
      var taxableGain = gain > 0 ? Math.max(0, gain - stdCosts) : gain;
      var tax = Math.max(0, taxableGain * rate);

      var nextBracket = findNextBracketForYears(brackets, holdingYears);
      var daysToNext = null;
      var targetDate = null;
      var taxIfWait = null;
      var saving = null;

      if (nextBracket && gain > 0) {
        daysToNext = Math.ceil(nextBracket.min_years * 365.25 - holdingDays);
        targetDate = new Date(lotDate.getTime() + nextBracket.min_years * 365.25 * MS_PER_DAY);
        var taxableIfWait = Math.max(0, gain - stdCostRate * (cost + proceeds));
        taxIfWait = Math.max(0, taxableIfWait * nextBracket.rate);
        saving = tax - taxIfWait;
      }

      lotResults.push({
        lotIndex: i + 1,
        date: lot.date,
        qty: matched,
        costPerShare: lot.cost_eur,
        cost: cost,
        proceeds: proceeds,
        gain: gain,
        holdingDays: holdingDays,
        holdingYears: holdingYears,
        rate: rate,
        stdCosts: stdCosts,
        tax: tax,
        nextRate: nextBracket ? nextBracket.rate : null,
        daysToNext: daysToNext,
        targetDate: targetDate ? targetDate.toISOString().slice(0, 10) : null,
        taxIfWait: taxIfWait,
        saving: saving
      });

      totalCost += cost;
      totalProceeds += proceeds;
      totalGain += gain;
      totalTax += tax;
      remaining -= matched;
    }

    var totalSavingIfWait = lotResults.reduce(function(s, l) { return s + (l.saving || 0); }, 0);
    var lotsWithSaving = lotResults.filter(function(l) { return l.saving && l.saving > 0; });

    // Render summary cards
    var cardsDiv = scopedFind(null, 'smartSellCards');
    cardsDiv.innerHTML = [
      [t('smart_sell.proceeds'), fmtCcy(totalProceeds), ''],
      [t('smart_sell.cost_basis'), fmtCcy(totalCost), ''],
      [t('smart_sell.gain'), signCcy(totalGain), cls(totalGain)],
      [t('smart_sell.tax_now'), fmtCcy(totalTax), 'neg'],
      [t('smart_sell.potential_saving'), fmtCcy(totalSavingIfWait), totalSavingIfWait > 0 ? 'pos' : ''],
      [t('smart_sell.lots_used'), lotResults.length + ' ' + t('smart_sell.lots_word'), ''],
    ].map(function(x) {
      return '<div class="metric-card"><div class="label">' + x[0] + '</div><div class="value ' + x[2] + '">' + x[1] + '</div></div>';
    }).join('');

    // Per-lot breakdown table
    var table = scopedFind(null, 'smartSellLotsTable');
    table.innerHTML =
      '<thead><tr>' +
      '<th>#</th>' +
      '<th>' + t('smart_sell.col.acquired') + '</th>' +
      '<th>' + t('smart_sell.col.qty') + '</th>' +
      '<th>' + t('smart_sell.col.cost') + '</th>' +
      '<th>' + t('smart_sell.col.proceeds') + '</th>' +
      '<th>' + t('smart_sell.col.gain') + '</th>' +
      '<th>' + t('smart_sell.col.held') + '</th>' +
      '<th>' + t('smart_sell.col.rate') + '</th>' +
      '<th>' + t('smart_sell.col.tax') + '</th>' +
      '</tr></thead><tbody>' +
      lotResults.map(function(l) {
        return '<tr>' +
          '<td>' + l.lotIndex + '</td>' +
          '<td>' + l.date + '</td>' +
          '<td>' + fmt(l.qty, 2) + '</td>' +
          '<td>' + fmtCcy(l.cost) + '</td>' +
          '<td>' + fmtCcy(l.proceeds) + '</td>' +
          '<td class="' + cls(l.gain) + '">' + signCcy(l.gain) + '</td>' +
          '<td>' + fmt(l.holdingYears, 1) + 'y</td>' +
          '<td>' + Math.round(l.rate * 100) + '%</td>' +
          '<td>' + fmtCcy(l.tax) + '</td>' +
          '</tr>';
      }).join('') +
      '</tbody>';

    // Wait suggestions section
    var waitSection = scopedFind(null, 'smartSellWaitSection');
    var waitTable = scopedFind(null, 'smartSellWaitTable');
    var waitNote = scopedFind(null, 'smartSellWaitNote');

    if (lotsWithSaving.length > 0) {
      waitSection.style.display = '';
      waitTable.innerHTML =
        '<thead><tr>' +
        '<th>' + t('smart_sell.col.lot') + '</th>' +
        '<th>' + t('smart_sell.col.acquired') + '</th>' +
        '<th>' + t('smart_sell.col.qty') + '</th>' +
        '<th>' + t('smart_sell.col.current_rate') + '</th>' +
        '<th>' + t('smart_sell.col.next_rate') + '</th>' +
        '<th>' + t('smart_sell.col.wait_days') + '</th>' +
        '<th>' + t('smart_sell.col.sell_after') + '</th>' +
        '<th>' + t('smart_sell.col.saving') + '</th>' +
        '</tr></thead><tbody>' +
        lotsWithSaving.map(function(l) {
          var urgency = l.daysToNext <= 90 ? 'pos' : l.daysToNext <= 365 ? '' : '';
          return '<tr>' +
            '<td>' + l.lotIndex + '</td>' +
            '<td>' + l.date + '</td>' +
            '<td>' + fmt(l.qty, 2) + '</td>' +
            '<td>' + Math.round(l.rate * 100) + '%</td>' +
            '<td class="pos">' + Math.round(l.nextRate * 100) + '%</td>' +
            '<td class="' + urgency + '"><strong>' + l.daysToNext + 'd</strong></td>' +
            '<td>' + l.targetDate + '</td>' +
            '<td class="pos">' + fmtCcy(l.saving) + '</td>' +
            '</tr>';
        }).join('') +
        '</tbody>';

      var soonest = lotsWithSaving.reduce(function(min, l) { return l.daysToNext < min.daysToNext ? l : min; }, lotsWithSaving[0]);
      if (soonest.daysToNext <= 90) {
        waitNote.innerHTML = '<strong>' + t('smart_sell.wait_tip_soon', { days: soonest.daysToNext, saving: fmtCcy(totalSavingIfWait) }) + '</strong>';
      } else {
        waitNote.textContent = t('smart_sell.wait_tip_general', { saving: fmtCcy(totalSavingIfWait) });
      }
    } else {
      waitSection.style.display = 'none';
      waitNote.textContent = '';
    }

    resultDiv.style.display = '';
    emptyDiv.style.display = 'none';
  }

  scopedFind(null, 'smartSellCalc').addEventListener('click', analyze);

  // Also trigger on Enter in qty input
  scopedFind(null, 'smartSellQty').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') analyze();
  });

  window.updateSmartSell = function() {
    populateTicker();
    scopedFind(null, 'smartSellResult').style.display = 'none';
  };

  init();
})();
