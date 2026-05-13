// --- Tax Action Nudge Widget ---
(function() {
  var container = document.getElementById('taxNudgeWidget');
  if (!container) return;

  var today = new Date();
  var currentMonth = today.getMonth() + 1; // 1-based
  var MS_PER_DAY = 1000 * 60 * 60 * 24;
  var SESSION_KEY = 'taxNudgeDismissed';

  function getDismissed() {
    try { return JSON.parse(sessionStorage.getItem(SESSION_KEY) || '{}'); } catch (e) { return {}; }
  }

  function dismiss(key) {
    var d = getDismissed();
    d[key] = true;
    try { sessionStorage.setItem(SESSION_KEY, JSON.stringify(d)); } catch (e) {}
    var el = document.getElementById('taxNudge-' + key);
    if (el) el.remove();
    if (!container.children.length) container.style.display = 'none';
  }

  function navToTax(subtab) {
    if (window.switchPage) window.switchPage('tax');
    if (subtab) {
      setTimeout(function() {
        if (window.switchTaxSubtab) window.switchTaxSubtab(subtab);
      }, 150);
    }
  }

  function makeItem(id, typeClass, icon, html, actionLabel, onAction) {
    var div = document.createElement('div');
    div.id = 'taxNudge-' + id;
    div.className = 'tax-nudge-item ' + typeClass;
    div.innerHTML =
      '<span class="tax-nudge-icon">' + icon + '</span>' +
      '<span class="tax-nudge-text">' + html + '</span>' +
      '<button class="tax-nudge-action">' + actionLabel + '</button>' +
      '<button class="tax-nudge-dismiss" title="Dismiss">×</button>';
    div.querySelector('.tax-nudge-action').addEventListener('click', onAction);
    div.querySelector('.tax-nudge-dismiss').addEventListener('click', function(e) {
      e.stopPropagation();
      dismiss(id);
    });
    return div;
  }

  var dismissed = getDismissed();
  var nudges = [];

  // 1. Harvest opportunity
  if (!dismissed['harvest']) {
    var tby = D.tax_by_year || {};
    var years = Object.keys(tby).map(Number).sort(function(a, b) { return b - a; });
    var latestYear = years[0];
    if (latestYear) {
      var candidates = (tby[latestYear] || {}).harvest_candidates || [];
      var totalNetBenefit = candidates.reduce(function(s, c) { return s + (c.net_benefit_eur || 0); }, 0);
      if (totalNetBenefit > 500) {
        nudges.push(makeItem(
          'harvest', 'tax-nudge-harvest', '&#127807;',
          'You have an estimated <strong>' + fmtCcy(totalNetBenefit) + '</strong> tax-loss harvest opportunity.',
          'Review',
          function() { navToTax('summary'); }
        ));
      }
    }
  }

  // 2. Bracket crossing <30 days
  if (!dismissed['bracket']) {
    var lots = D.position_lots || {};
    var positions = D.positions || [];
    var regime = D.regime || {};

    function getBrackets(ticker) {
      if (ticker.startsWith('CFD:')) return regime.cfd_brackets || [];
      if (ticker.startsWith('CRYPTO:')) return regime.crypto_brackets || [];
      if (ticker.startsWith('SAVINGS:')) return regime.savings_brackets || [];
      return regime.stock_brackets || [];
    }

    var soonest = null;
    for (var pi = 0; pi < positions.length; pi++) {
      var pos = positions[pi];
      if (pos.quantity <= 0) continue;
      var brackets = getBrackets(pos.ticker);
      if (!brackets || brackets.length <= 1) continue;
      var posLots = lots[pos.ticker] || [];
      for (var li = 0; li < posLots.length; li++) {
        var lot = posLots[li];
        var lotDate = new Date(lot.date);
        var holdingDays = Math.floor((today - lotDate) / MS_PER_DAY);
        var holdingYears = holdingDays / 365.25;
        // Find next bracket
        var nextBracket = null;
        for (var bi = 0; bi < brackets.length; bi++) {
          if (brackets[bi].min_years > holdingYears) { nextBracket = brackets[bi]; break; }
        }
        if (!nextBracket) continue;
        var daysToNext = Math.ceil(nextBracket.min_years * 365.25 - holdingDays);
        if (daysToNext > 0 && daysToNext <= 30) {
          if (!soonest || daysToNext < soonest.daysToNext) {
            soonest = { ticker: pos.ticker, daysToNext: daysToNext, nextRate: nextBracket.rate };
          }
        }
      }
    }

    if (soonest) {
      var rateLabel = Math.round(soonest.nextRate * 100) + '%';
      nudges.push(makeItem(
        'bracket', 'tax-nudge-bracket', '&#9201;',
        '<strong>' + soonest.ticker + '</strong> drops to <strong>' + rateLabel + '</strong> tax rate in <strong>' + soonest.daysToNext + ' day' + (soonest.daysToNext === 1 ? '' : 's') + '</strong>.',
        'See details',
        function() { navToTax('summary'); }
      ));
    }
  }

  // 3. Year-end window (Oct–Dec)
  if (!dismissed['yearend'] && currentMonth >= 10) {
    var tbyYE = D.tax_by_year || {};
    var yearsYE = Object.keys(tbyYE).map(Number).sort(function(a, b) { return b - a; });
    var latestYearYE = yearsYE[0];
    if (latestYearYE) {
      var tyYE = tbyYE[latestYearYE] || {};
      var sales = tyYE.realized_sales || [];
      var _regime = D.regime || {};
      var buckets = {};
      for (var si = 0; si < sales.length; si++) {
        var s = sales[si];
        var gain = s.gain_eur > 0 ? Math.max(0, s.gain_eur - s.std_costs_eur) : s.gain_eur;
        var key = s.tax_rate;
        buckets[key] = (buckets[key] || 0) + gain;
      }
      var totalTax = 0;
      for (var k in buckets) {
        totalTax += Math.max(0, buckets[k]) * parseFloat(k);
      }
      nudges.push(makeItem(
        'yearend', 'tax-nudge-yearend', '&#128203;',
        'Year-end tax review: estimated liability is <strong>' + fmtCcy(totalTax) + '</strong> for <strong>' + latestYearYE + '</strong>.',
        'Export eDavki',
        function() { navToTax('file'); }
      ));
    }
  }

  if (nudges.length === 0) {
    container.style.display = 'none';
    return;
  }

  container.style.display = '';
  var widget = document.createElement('div');
  widget.className = 'tax-nudge-widget';
  for (var ni = 0; ni < nudges.length; ni++) {
    widget.appendChild(nudges[ni]);
  }
  container.appendChild(widget);
})();
