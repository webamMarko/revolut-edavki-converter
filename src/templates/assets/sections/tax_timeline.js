// --- Tax Timeline Visualization ---
(function() {
  var positions = D.positions || [];
  var lots = D.position_lots || {};
  var regime = D.regime || {};
  var section = document.getElementById('taxTimelineSection');
  if (!section) return;

  var today = new Date();
  var MS_PER_DAY = 1000 * 60 * 60 * 24;
  var timelineChart = null;
  var currentSort = 'days';
  var timelineData = [];

  var bracketColors = {
    0.25: { bg: 'rgba(248,113,113,0.7)', border: '#f87171' },
    0.20: { bg: 'rgba(251,146,60,0.7)', border: '#fb923c' },
    0.15: { bg: 'rgba(250,204,21,0.7)', border: '#facc15' },
    0.10: { bg: 'rgba(52,211,153,0.7)', border: '#34d399' },
    0.0:  { bg: 'rgba(96,165,250,0.7)', border: '#60a5fa' },
  };

  function getColorForRate(rate) {
    var r = Math.round(rate * 100) / 100;
    if (bracketColors[r]) return bracketColors[r];
    if (r >= 0.25) return bracketColors[0.25];
    if (r >= 0.20) return bracketColors[0.20];
    if (r >= 0.15) return bracketColors[0.15];
    if (r >= 0.10) return bracketColors[0.10];
    return bracketColors[0.0];
  }

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

  function findNextBracket(brackets, holdingYears) {
    if (!brackets || brackets.length <= 1) return null;
    for (var i = 0; i < brackets.length; i++) {
      if (brackets[i].min_years > holdingYears) return brackets[i];
    }
    return null;
  }

  function computeTimelineData() {
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
      var totalQty = 0;
      var weightedDays = 0;
      var totalCost = 0;

      for (var li = 0; li < posLots.length; li++) {
        var lot = posLots[li];
        var lotDate = new Date(lot.date);
        var days = Math.floor((today - lotDate) / MS_PER_DAY);
        weightedDays += lot.qty * days;
        totalQty += lot.qty;
        totalCost += lot.qty * lot.cost_eur;
      }

      var avgHoldingDays = totalQty > 0 ? weightedDays / totalQty : 0;
      var avgHoldingYears = avgHoldingDays / 365.25;
      var currentRate = getRateForHolding(brackets, avgHoldingYears);
      var nextBracket = findNextBracket(brackets, avgHoldingYears);

      if (!nextBracket) continue;

      var daysToNext = Math.ceil((nextBracket.min_years * 365.25) - avgHoldingDays);
      var marketValue = pricePerShare * totalQty;
      var unrealizedGain = marketValue - totalCost;
      var taxNow = unrealizedGain > 0 ? unrealizedGain * currentRate : 0;
      var taxAfter = unrealizedGain > 0 ? unrealizedGain * nextBracket.rate : 0;
      var saving = Math.max(0, taxNow - taxAfter);

      var earliestLot = posLots[0].date;
      for (var j = 1; j < posLots.length; j++) {
        if (posLots[j].date < earliestLot) earliestLot = posLots[j].date;
      }

      items.push({
        ticker: pos.ticker,
        name: (D.company_names || {})[pos.ticker] || pos.ticker,
        assetClass: ac,
        purchaseDate: earliestLot,
        avgHoldingDays: Math.round(avgHoldingDays),
        avgHoldingYears: avgHoldingYears,
        currentRate: currentRate,
        nextRate: nextBracket.rate,
        nextMinYears: nextBracket.min_years,
        daysToNext: daysToNext,
        marketValue: marketValue,
        unrealizedGain: unrealizedGain,
        taxNow: taxNow,
        taxAfter: taxAfter,
        saving: saving,
        quantity: totalQty,
        costBasis: totalCost,
        comingSoon: daysToNext <= 30
      });
    }
    return items;
  }

  function sortData(items, sortBy) {
    var sorted = items.slice();
    if (sortBy === 'days') sorted.sort(function(a, b) { return a.daysToNext - b.daysToNext; });
    else if (sortBy === 'size') sorted.sort(function(a, b) { return b.marketValue - a.marketValue; });
    else if (sortBy === 'savings') sorted.sort(function(a, b) { return b.saving - a.saving; });
    return sorted;
  }

  function buildChart(items) {
    var canvas = document.getElementById('taxTimelineCanvas');
    if (!canvas) return;
    var ctx = canvas.getContext('2d');

    if (timelineChart) {
      timelineChart.destroy();
      timelineChart = null;
    }

    if (items.length === 0) return;

    var barHeight = 28;
    var chartHeight = Math.max(200, items.length * (barHeight + 8) + 60);
    canvas.parentElement.style.height = Math.min(chartHeight, 600) + 'px';

    var labels = items.map(function(it) { return it.ticker; });
    var todayTs = today.getTime();

    var bgColors = items.map(function(it) { return getColorForRate(it.currentRate).bg; });
    var borderColors = items.map(function(it) { return getColorForRate(it.currentRate).border; });

    var datasets = [
      {
        label: 'Holding period',
        data: items.map(function(it) {
          return [new Date(it.purchaseDate).getTime(), todayTs];
        }),
        backgroundColor: bgColors,
        borderColor: borderColors,
        borderWidth: 1,
        borderSkipped: false,
        barPercentage: 0.7,
        categoryPercentage: 0.85,
      },
      {
        label: 'Until next bracket',
        data: items.map(function(it) {
          return [todayTs, todayTs + it.daysToNext * MS_PER_DAY];
        }),
        backgroundColor: items.map(function(it) {
          return getColorForRate(it.nextRate).bg.replace('0.7', '0.25');
        }),
        borderColor: items.map(function(it) {
          return getColorForRate(it.nextRate).border;
        }),
        borderWidth: 1,
        borderSkipped: false,
        barPercentage: 0.7,
        categoryPercentage: 0.85,
      }
    ];

    var allStarts = items.map(function(it) { return new Date(it.purchaseDate).getTime(); });
    var allEnds = items.map(function(it) { return todayTs + it.daysToNext * MS_PER_DAY; });
    var minTs = Math.min.apply(null, allStarts);
    var maxTs = Math.max.apply(null, allEnds);
    var pad = (maxTs - minTs) * 0.02;

    timelineChart = new Chart(ctx, {
      type: 'bar',
      data: { labels: labels, datasets: datasets },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: true },
        onClick: function(evt, elems) {
          if (elems.length > 0) {
            var idx = elems[0].index;
            showWhatIf(items[idx]);
          }
        },
        scales: {
          x: {
            type: 'time',
            time: { unit: 'month', displayFormats: { month: 'MMM yyyy' } },
            min: minTs - pad,
            max: maxTs + pad,
            grid: { color: 'rgba(128,128,128,0.1)' },
            ticks: { font: { size: 10 } },
            stacked: false,
          },
          y: {
            grid: { display: false },
            ticks: { font: { size: 11 } },
            stacked: false,
          }
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: function(ctx) {
                var idx = ctx[0].dataIndex;
                var it = items[idx];
                return it.ticker + ' — ' + it.name;
              },
              label: function(ctx) {
                var idx = ctx.dataIndex;
                var it = items[idx];
                if (ctx.datasetIndex === 0) {
                  return 'Held: ' + it.avgHoldingDays + 'd (' + fmt(it.avgHoldingYears, 1) + 'y) @ ' + Math.round(it.currentRate * 100) + '%';
                }
                var lines = [
                  it.daysToNext + ' days until ' + Math.round(it.nextRate * 100) + '% bracket'
                ];
                if (it.saving > 0) {
                  lines.push('Est. savings: ' + fmtCcy(it.saving));
                }
                return lines;
              }
            }
          }
        }
      }
    });
  }

  function showWhatIf(item) {
    var panel = document.getElementById('taxTimelineWhatIf');
    var cards = document.getElementById('taxTimelineWhatIfCards');
    var note = document.getElementById('taxTimelineWhatIfNote');

    panel.style.display = '';

    var rows = [
      [item.ticker + ' — ' + item.name, '', ''],
      ['Market value', fmtCcy(item.marketValue), ''],
      ['Unrealized gain', signCcy(item.unrealizedGain), cls(item.unrealizedGain)],
      ['Tax if sold today', fmtCcy(item.taxNow), item.taxNow > 0 ? 'neg' : ''],
      ['Current rate', Math.round(item.currentRate * 100) + '%', ''],
      ['Held', fmt(item.avgHoldingYears, 1) + ' years', ''],
    ];

    cards.innerHTML = rows.map(function(r) {
      return '<div class="metric-card"><div class="label">' + r[0] + '</div><div class="value ' + r[2] + '">' + r[1] + '</div></div>';
    }).join('');

    if (item.saving > 0 && item.daysToNext > 0) {
      var targetDate = new Date(today.getTime() + item.daysToNext * MS_PER_DAY);
      note.innerHTML = '<strong>Wait ' + item.daysToNext + ' days</strong> (until ' +
        targetDate.toISOString().slice(0, 10) + ') for ' +
        Math.round(item.nextRate * 100) + '% rate → ' +
        '<strong>Tax: ' + fmtCcy(item.taxAfter) + '</strong> (save <span class="pos">' +
        fmtCcy(item.saving) + '</span>)';
      if (item.comingSoon) {
        note.innerHTML += '<br><span style="color:var(--green);font-weight:600">⏰ Coming soon — within 30 days!</span>';
      }
    } else if (item.unrealizedGain <= 0) {
      note.innerHTML = 'Position is at a loss — no tax on sale.';
    } else {
      note.innerHTML = '';
    }
  }

  document.getElementById('taxTimelineWhatIfClose').addEventListener('click', function() {
    document.getElementById('taxTimelineWhatIf').style.display = 'none';
  });

  // Sort button handlers
  var sortBtns = section.querySelectorAll('[data-sort]');
  sortBtns.forEach(function(btn) {
    btn.addEventListener('click', function() {
      currentSort = btn.dataset.sort;
      sortBtns.forEach(function(b) { b.classList.toggle('active', b === btn); });
      renderTimeline();
    });
  });

  function renderTimeline() {
    timelineData = computeTimelineData();

    if (timelineData.length === 0) {
      section.style.display = 'none';
      return;
    }

    section.style.display = '';
    document.getElementById('taxTimelineTitle').textContent = t('tax_timeline.title') !== 'tax_timeline.title' ? t('tax_timeline.title') : 'Tax Bracket Timeline';
    document.getElementById('taxTimelineDesc').textContent = t('tax_timeline.desc') !== 'tax_timeline.desc' ? t('tax_timeline.desc') : 'Visual timeline of positions colored by tax bracket. Click a bar for what-if analysis.';

    var sorted = sortData(timelineData, currentSort);
    buildChart(sorted);
  }

  window.updateTaxTimeline = renderTimeline;
  renderTimeline();
})();
