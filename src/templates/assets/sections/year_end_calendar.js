// --- Year-End Tax Action Calendar ---
(function() {
  var section = document.getElementById('yearEndCalendarSection');
  if (!section) return;

  var today = new Date();
  var currentYear = today.getFullYear();
  var yearEnd = new Date(currentYear, 11, 31); // Dec 31
  var MS_PER_DAY = 1000 * 60 * 60 * 24;
  var daysUntilYearEnd = Math.max(0, Math.ceil((yearEnd - today) / MS_PER_DAY));

  var positions = D.positions || [];
  var lots = D.position_lots || {};
  var regime = D.regime || {};
  var taxByYear = D.tax_by_year || {};
  var currentYearTax = taxByYear[currentYear] || {};
  var harvestCandidates = currentYearTax.harvest_candidates || [];

  function getBrackets(ticker) {
    if (ticker.startsWith('CFD:')) return regime.cfd_brackets || [];
    if (ticker.startsWith('CRYPTO:')) return regime.crypto_brackets || [];
    if (ticker.startsWith('SAVINGS:')) return regime.savings_brackets || [];
    return regime.stock_brackets || [];
  }

  function getRateForHolding(brackets, holdingYears) {
    if (!brackets || brackets.length === 0) return 0.25;
    var rate = brackets[0].rate;
    for (var i = 0; i < brackets.length; i++) {
      if (holdingYears >= brackets[i].min_years) rate = brackets[i].rate;
    }
    return rate;
  }

  function findNextBracket(brackets, holdingYears) {
    if (!brackets) return null;
    for (var i = 0; i < brackets.length; i++) {
      if (brackets[i].min_years > holdingYears) return brackets[i];
    }
    return null;
  }

  // Build actions list
  // Types: 'bracket_before_yearend', 'bracket_urgent', 'harvest', 'hold_past_yearend'
  function buildActions() {
    var actions = [];

    // --- Bracket crossing actions ---
    for (var pi = 0; pi < positions.length; pi++) {
      var pos = positions[pi];
      if (pos.quantity <= 0) continue;
      var brackets = getBrackets(pos.ticker);
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
        var nextBracket = findNextBracket(brackets, holdingYears);
        if (!nextBracket) continue;

        var daysToNext = Math.ceil(nextBracket.min_years * 365.25 - holdingDays);
        if (daysToNext <= 0) continue;

        var targetDate = new Date(lotDate.getTime() + nextBracket.min_years * 365.25 * MS_PER_DAY);
        var targetDateStr = targetDate.toISOString().slice(0, 10);

        var unrealizedGain = (pricePerShare - lot.cost_eur) * lot.qty;
        var taxNow = unrealizedGain > 0 ? unrealizedGain * currentRate : 0;
        var taxAfter = unrealizedGain > 0 ? unrealizedGain * nextBracket.rate : 0;
        var saving = Math.max(0, taxNow - taxAfter);

        if (daysToNext <= daysUntilYearEnd) {
          // Bracket crosses before Dec 31 — HOLD, don't sell yet
          actions.push({
            type: 'hold',
            subtype: daysToNext <= 30 ? 'urgent' : daysToNext <= 90 ? 'soon' : 'yearend',
            ticker: pos.ticker,
            lotDate: lot.date,
            qty: lot.qty,
            deadline: targetDateStr,
            daysLeft: daysToNext,
            impact: saving,
            fromRate: currentRate,
            toRate: nextBracket.rate,
            detail: t('calendar.detail.bracket_cross', {
              from: Math.round(currentRate * 100),
              to: Math.round(nextBracket.rate * 100),
              date: targetDateStr
            })
          });
        }
      }
    }

    // --- Loss harvest actions ---
    for (var hi = 0; hi < harvestCandidates.length; hi++) {
      var hc = harvestCandidates[hi];
      if ((hc.unrealized_loss_eur || 0) >= 0) continue; // must be a loss
      var netBenefit = hc.net_benefit_eur || 0;
      if (netBenefit <= 0) continue;

      actions.push({
        type: 'harvest',
        subtype: 'harvest',
        ticker: hc.ticker,
        lotDate: null,
        qty: hc.quantity || 0,
        deadline: currentYear + '-12-31',
        daysLeft: daysUntilYearEnd,
        impact: netBenefit,
        fromRate: null,
        toRate: null,
        detail: t('calendar.detail.harvest', {
          loss: fmtCcy(Math.abs(hc.unrealized_loss_eur || 0)),
          gain: fmtCcy(hc.offsettable_gain_eur || 0)
        })
      });
    }

    // Sort: urgent first, then by impact descending within group
    var order = { urgent: 0, soon: 1, yearend: 2, harvest: 3 };
    actions.sort(function(a, b) {
      var og = (order[a.subtype] || 99) - (order[b.subtype] || 99);
      if (og !== 0) return og;
      return b.impact - a.impact;
    });

    return actions;
  }

  function renderTimeline(actions) {
    var container = document.getElementById('yearEndTimeline');
    if (!container) return;
    if (actions.length === 0) { container.style.display = 'none'; return; }

    // Simple month-by-month timeline strip showing when actions cluster
    var months = {};
    for (var i = 0; i < actions.length; i++) {
      var a = actions[i];
      if (!a.deadline) continue;
      var month = a.deadline.slice(0, 7); // YYYY-MM
      if (!months[month]) months[month] = { count: 0, impact: 0 };
      months[month].count++;
      months[month].impact += a.impact;
    }

    var keys = Object.keys(months).sort();
    if (keys.length === 0) { container.style.display = 'none'; return; }

    var maxCount = Math.max.apply(null, keys.map(function(k) { return months[k].count; }));

    var html = '<div style="display:flex;gap:0.5rem;align-items:flex-end;min-height:60px;padding:0.25rem 0">';
    for (var ki = 0; ki < keys.length; ki++) {
      var k = keys[ki];
      var m = months[k];
      var heightPct = Math.max(10, Math.round((m.count / maxCount) * 100));
      var label = k.slice(5); // MM
      var monthNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
      var monthLabel = monthNames[parseInt(label, 10) - 1] || label;
      var barColor = m.count >= 3 ? 'var(--neg)' : m.count >= 2 ? 'var(--warn,#f59e0b)' : 'var(--accent)';
      html += '<div style="display:flex;flex-direction:column;align-items:center;gap:0.25rem;flex:1;min-width:40px">' +
        '<span style="font-size:0.65rem;color:var(--muted)">' + m.count + '</span>' +
        '<div title="' + fmtCcy(m.impact) + '" style="width:100%;height:' + heightPct + '%;min-height:6px;max-height:50px;background:' + barColor + ';border-radius:3px 3px 0 0;transition:height 0.2s"></div>' +
        '<span style="font-size:0.7rem;color:var(--muted)">' + monthLabel + '</span>' +
        '</div>';
    }
    html += '</div>';
    container.innerHTML = html;
    container.style.display = '';
  }

  function makeActionTable(tableEl, items) {
    if (!tableEl || items.length === 0) return;
    var thead = '<thead><tr>' +
      '<th>' + t('calendar.col.action') + '</th>' +
      '<th>' + t('calendar.col.ticker') + '</th>' +
      '<th>' + t('calendar.col.deadline') + '</th>' +
      '<th>' + t('calendar.col.days') + '</th>' +
      '<th>' + t('calendar.col.impact') + '</th>' +
      '<th>' + t('calendar.col.detail') + '</th>' +
      '</tr></thead>';

    var tbody = '<tbody>';
    for (var i = 0; i < items.length; i++) {
      var a = items[i];
      var actionLabel, actionClass;
      if (a.type === 'hold') {
        actionLabel = t('calendar.action.wait_bracket');
        actionClass = 'muted';
      } else if (a.type === 'harvest') {
        actionLabel = t('calendar.action.harvest');
        actionClass = 'pos';
      } else {
        actionLabel = t('calendar.action.sell_now');
        actionClass = '';
      }

      var daysClass = a.daysLeft <= 30 ? 'neg' : a.daysLeft <= 90 ? '' : 'muted';
      var name = (D.company_names || {})[a.ticker] || a.ticker;

      tbody += '<tr>' +
        '<td><strong class="' + actionClass + '">' + actionLabel + '</strong></td>' +
        '<td title="' + name + '"><strong>' + a.ticker + '</strong>' + (a.lotDate ? '<br><span style="font-size:0.7rem;color:var(--muted)">' + a.lotDate + '</span>' : '') + '</td>' +
        '<td>' + (a.deadline || '—') + '</td>' +
        '<td class="' + daysClass + '"><strong>' + a.daysLeft + 'd</strong></td>' +
        '<td class="pos">' + fmtCcy(a.impact) + '</td>' +
        '<td style="font-size:0.78rem;color:var(--muted)">' + a.detail + '</td>' +
        '</tr>';
    }
    tbody += '</tbody>';
    tableEl.innerHTML = thead + tbody;
  }

  function render() {
    var actions = buildActions();

    document.getElementById('yearEndCalendarTitle').textContent = t('calendar.title');
    document.getElementById('yearEndCalendarDesc').textContent = t('calendar.desc');
    document.getElementById('yearEndCalendarEmptyMsg').textContent = t('calendar.empty');
    document.getElementById('yearEndTimelineTitle').textContent = t('calendar.timeline.title');

    if (actions.length === 0) {
      document.getElementById('yearEndCalendarEmpty').style.display = '';
      document.getElementById('yearEndTimelineSection').style.display = 'none';
      document.getElementById('yearEndActionsSection').style.display = 'none';
      return;
    }

    document.getElementById('yearEndCalendarEmpty').style.display = 'none';
    document.getElementById('yearEndActionsSection').style.display = '';

    var totalImpact = actions.reduce(function(s, a) { return s + a.impact; }, 0);
    var bracketCount = actions.filter(function(a) { return a.type === 'hold'; }).length;

    // Summary cards
    var highlight = document.getElementById('yearEndCalendarHighlight');
    highlight.innerHTML = [
      [t('calendar.days_left'), daysUntilYearEnd + 'd', daysUntilYearEnd <= 30 ? 'neg' : ''],
      [t('calendar.actions_total'), actions.length.toString(), ''],
      [t('calendar.bracket_crossings'), bracketCount.toString(), bracketCount > 0 ? 'pos' : ''],
      [t('calendar.total_impact'), fmtCcy(totalImpact), totalImpact > 0 ? 'pos' : ''],
    ].map(function(c) {
      return '<div class="metric-card"><div class="label">' + c[0] + '</div><div class="value ' + c[2] + '">' + c[1] + '</div></div>';
    }).join('');

    // Timeline
    renderTimeline(actions);

    // Action groups
    var groups = [
      { key: 'urgent',  filter: function(a) { return a.subtype === 'urgent'; },  el: 'Urgent',  titleKey: 'calendar.section.urgent' },
      { key: 'soon',    filter: function(a) { return a.subtype === 'soon'; },    el: 'Soon',    titleKey: 'calendar.section.soon' },
      { key: 'yearend', filter: function(a) { return a.subtype === 'yearend'; }, el: 'Yearend', titleKey: 'calendar.section.yearend' },
      { key: 'harvest', filter: function(a) { return a.subtype === 'harvest'; }, el: 'Harvest', titleKey: 'calendar.section.harvest' },
    ];

    for (var gi = 0; gi < groups.length; gi++) {
      var g = groups[gi];
      var items = actions.filter(g.filter);
      var groupEl = document.getElementById('yearEndGroup' + g.el);
      var tableEl = document.getElementById('yearEndTable' + g.el);
      var titleEl = document.getElementById('yearEndGroup' + g.el + 'Title');
      if (!groupEl) continue;
      if (items.length === 0) {
        groupEl.style.display = 'none';
        continue;
      }
      groupEl.style.display = '';
      if (titleEl) titleEl.textContent = t(g.titleKey) + ' (' + items.length + ')';
      makeActionTable(tableEl, items);
    }

    // Hold group (don't sell before) — already covered in urgent/soon/yearend above
    // but show an explicit "hold" group if none of the above caught them
    var holdGroup = document.getElementById('yearEndGroupHold');
    if (holdGroup) holdGroup.style.display = 'none';
  }

  window.updateYearEndCalendar = render;
  render();
})();
