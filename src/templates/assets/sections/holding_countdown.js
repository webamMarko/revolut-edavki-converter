// --- Holding Period Countdown Timers ---
(function() {
  var positions = D.positions || [];
  var lots = D.position_lots || {};
  var regime = D.regime || {};
  var section = document.getElementById('holdingCountdownSection');
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

  function findNextBracketForLot(brackets, holdingYears) {
    if (!brackets || brackets.length <= 1) return null;
    for (var i = 0; i < brackets.length; i++) {
      if (brackets[i].min_years > holdingYears) {
        return brackets[i];
      }
    }
    return null;
  }

  function computeCountdowns() {
    var items = [];
    for (var pi = 0; pi < positions.length; pi++) {
      var pos = positions[pi];
      if (pos.quantity <= 0) continue;
      var ac = getAssetClass(pos.ticker);
      if (!isDefaultSelection() && !activeClasses.has(ac)) continue;
      var brackets = getBrackets(ac);
      if (!brackets || brackets.length <= 1) continue;
      var posLots = lots[pos.ticker] || [];
      if (posLots.length === 0) continue;

      var pricePerShare = pos.market_value_eur / pos.quantity;

      for (var li = 0; li < posLots.length; li++) {
        var lot = posLots[li];
        var lotDate = new Date(lot.date);
        var holdingDays = Math.floor((today - lotDate) / MS_PER_DAY);
        var holdingYears = holdingDays / 365.25;
        var currentRate = getRateForHolding(brackets, holdingYears);
        var nextBracket = findNextBracketForLot(brackets, holdingYears);

        if (!nextBracket) continue; // already at 0% — no countdown needed

        var daysToNext = Math.ceil((nextBracket.min_years * 365.25) - holdingDays);
        var targetDate = new Date(lotDate.getTime() + nextBracket.min_years * 365.25 * MS_PER_DAY);

        var unrealizedGain = (pricePerShare - lot.cost_eur) * lot.qty;
        var taxNow = unrealizedGain > 0 ? unrealizedGain * currentRate : 0;
        var taxAfter = unrealizedGain > 0 ? unrealizedGain * nextBracket.rate : 0;
        var saving = Math.max(0, taxNow - taxAfter);

        items.push({
          ticker: pos.ticker,
          lotDate: lot.date,
          qty: lot.qty,
          costEur: lot.cost_eur,
          holdingDays: holdingDays,
          holdingYears: holdingYears,
          currentRate: currentRate,
          nextRate: nextBracket.rate,
          nextMinYears: nextBracket.min_years,
          daysToNext: daysToNext,
          targetDate: targetDate.toISOString().slice(0, 10),
          unrealizedGain: unrealizedGain,
          taxSaving: saving,
          marketValue: pricePerShare * lot.qty
        });
      }
    }
    items.sort(function(a, b) { return a.daysToNext - b.daysToNext; });
    return items;
  }

  function renderCountdown() {
    var items = computeCountdowns();
    if (items.length === 0) {
      section.style.display = 'none';
      return;
    }
    section.style.display = '';
    document.getElementById('holdingCountdownTitle').textContent = t('holding.title');
    document.getElementById('holdingCountdownDesc').textContent = t('holding.desc');

    // Highlight cards: closest milestones, biggest savings
    var upcoming = items.filter(function(x) { return x.daysToNext <= 365; });
    var highlightDiv = document.getElementById('holdingCountdownHighlight');

    var totalSaving = items.reduce(function(s, x) { return s + x.taxSaving; }, 0);
    var soonest = items[0];
    var biggestSaving = items.reduce(function(best, x) { return x.taxSaving > best.taxSaving ? x : best; }, items[0]);

    var cards = [
      [t('holding.lots_tracked'), items.length.toString(), ''],
      [t('holding.next_milestone'), soonest.daysToNext + ' ' + t('holding.days') + ' (' + soonest.ticker + ')', ''],
      [t('holding.within_year'), upcoming.length.toString(), upcoming.length > 0 ? 'pos' : ''],
      [t('holding.total_potential_saving'), fmtCcy(totalSaving), totalSaving > 0 ? 'pos' : ''],
    ];

    highlightDiv.innerHTML = cards.map(function(c) {
      return '<div class="metric-card"><div class="label">' + c[0] + '</div><div class="value ' + c[2] + '">' + c[1] + '</div></div>';
    }).join('');

    // Table
    var table = document.getElementById('holdingCountdownTable');
    var thead = '<thead><tr>' +
      '<th>' + t('holding.col.ticker') + '</th>' +
      '<th>' + t('holding.col.acquired') + '</th>' +
      '<th>' + t('holding.col.qty') + '</th>' +
      '<th>' + t('holding.col.held') + '</th>' +
      '<th>' + t('holding.col.current_rate') + '</th>' +
      '<th>' + t('holding.col.next_rate') + '</th>' +
      '<th>' + t('holding.col.countdown') + '</th>' +
      '<th>' + t('holding.col.target_date') + '</th>' +
      '<th>' + t('holding.col.saving') + '</th>' +
      '</tr></thead>';

    var tbody = '<tbody>';
    for (var i = 0; i < items.length; i++) {
      var it = items[i];
      var urgencyClass = it.daysToNext <= 90 ? 'pos' : it.daysToNext <= 365 ? '' : 'muted';
      var countdownLabel = it.daysToNext <= 0 ? t('holding.reached') : it.daysToNext + 'd';
      var yearsHeld = fmt(it.holdingYears, 1) + 'y';
      var name = (D.company_names || {})[it.ticker] || it.ticker;

      tbody += '<tr>' +
        '<td title="' + name + '"><strong>' + it.ticker + '</strong></td>' +
        '<td>' + it.lotDate + '</td>' +
        '<td>' + fmt(it.qty, 2) + '</td>' +
        '<td>' + yearsHeld + '</td>' +
        '<td>' + Math.round(it.currentRate * 100) + '%</td>' +
        '<td>' + Math.round(it.nextRate * 100) + '%</td>' +
        '<td class="' + urgencyClass + '"><strong>' + countdownLabel + '</strong></td>' +
        '<td>' + it.targetDate + '</td>' +
        '<td class="' + (it.taxSaving > 0 ? 'pos' : '') + '">' + fmtCcy(it.taxSaving) + '</td>' +
        '</tr>';
    }
    tbody += '</tbody>';
    table.innerHTML = thead + tbody;
  }

  window.updateHoldingCountdown = renderCountdown;
  renderCountdown();
})();
