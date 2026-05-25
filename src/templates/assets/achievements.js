// --- Achievement & Milestone Celebration System ---
(function() {
  var STORAGE_KEY = 'achievements_earned';
  var TOAST_SHOWN_KEY = 'achievements_toast_shown';

  // --- Achievement Definitions ---
  var ACHIEVEMENTS = [
    {
      id: 'first_dividend',
      icon: '&#x1F4B0;',
      title: 'First Dividend',
      category: 'income',
      detect: function() {
        var div = D.dividends;
        if (!div || !div.total_eur || div.total_eur <= 0) return null;
        var firstMonth = div.by_month && div.by_month.length > 0 ? div.by_month[0] : null;
        var date = firstMonth ? firstMonth.month + '-01' : null;
        return { date: date, detail: fmtCcy(div.total_eur) + ' total earned' };
      }
    },
    {
      id: 'tax_bracket_1yr',
      icon: '&#x1F3C6;',
      title: '1-Year Holding',
      category: 'tax',
      detect: function() {
        return _detectHoldingMilestone(1);
      }
    },
    {
      id: 'tax_bracket_5yr',
      icon: '&#x1F48E;',
      title: '5-Year Holding',
      category: 'tax',
      detect: function() {
        return _detectHoldingMilestone(5);
      }
    },
    {
      id: 'value_1k',
      icon: '&#x1F3AF;',
      title: 'First 1K',
      category: 'value',
      detect: function() { return _detectValueThreshold(1000, '1K'); }
    },
    {
      id: 'value_5k',
      icon: '&#x1F3AF;',
      title: 'Reached 5K',
      category: 'value',
      detect: function() { return _detectValueThreshold(5000, '5K'); }
    },
    {
      id: 'value_10k',
      icon: '&#x2B50;',
      title: 'Reached 10K',
      category: 'value',
      detect: function() { return _detectValueThreshold(10000, '10K'); }
    },
    {
      id: 'value_50k',
      icon: '&#x1F31F;',
      title: 'Reached 50K',
      category: 'value',
      detect: function() { return _detectValueThreshold(50000, '50K'); }
    },
    {
      id: 'value_100k',
      icon: '&#x1F4AB;',
      title: 'Six Figures',
      category: 'value',
      detect: function() { return _detectValueThreshold(100000, '100K'); }
    },
    {
      id: 'savings_streak',
      icon: '&#x1F4AA;',
      title: 'Savings Streak',
      category: 'consistency',
      detect: function() {
        return _detectSavingsStreak();
      }
    },
    {
      id: 'tax_filing',
      icon: '&#x2705;',
      title: 'Tax Pro',
      category: 'tax',
      detect: function() {
        var completed = localStorage.getItem('tax_wizard_completed');
        if (!completed) return null;
        return { date: completed, detail: 'Filed taxes via wizard' };
      }
    },
    {
      id: 'diversified',
      icon: '&#x1F30D;',
      title: 'Diversified',
      category: 'strategy',
      detect: function() {
        var positions = D.positions || [];
        var active = positions.filter(function(p) { return p.quantity > 0; });
        if (active.length < 5) return null;
        return { date: null, detail: active.length + ' positions held' };
      }
    },
    {
      id: 'first_year',
      icon: '&#x1F382;',
      title: '1-Year Anniversary',
      category: 'time',
      detect: function() {
        return _detectPortfolioAge(365);
      }
    }
  ];

  // --- Detection helpers ---

  function _detectValueThreshold(threshold, label) {
    if (!ds || !ds.value_eur || !ds.dates) return null;
    for (var i = 0; i < ds.value_eur.length; i++) {
      if (ds.value_eur[i] >= threshold) {
        return { date: ds.dates[i], detail: label + ' ' + _currency + ' reached' };
      }
    }
    return null;
  }

  function _detectHoldingMilestone(years) {
    var lots = D.position_lots || {};
    var positions = D.positions || [];
    var today = new Date();
    var MS_PER_DAY = 86400000;
    var targetDays = years * 365.25;
    var regime = D.regime || {};
    var brackets = regime.stock_brackets || [];

    var qualifying = [];
    for (var pi = 0; pi < positions.length; pi++) {
      var pos = positions[pi];
      if (pos.quantity <= 0) continue;
      var posLots = lots[pos.ticker] || [];
      for (var li = 0; li < posLots.length; li++) {
        var lot = posLots[li];
        var holdingDays = Math.floor((today - new Date(lot.date)) / MS_PER_DAY);
        if (holdingDays >= targetDays) {
          qualifying.push({ ticker: pos.ticker, days: holdingDays });
          break;
        }
      }
    }
    if (qualifying.length === 0) return null;

    var savedPct = _estimateTaxSaving(years, brackets);
    var detail = qualifying.length + ' position' + (qualifying.length > 1 ? 's' : '') + ' held ' + years + '+ yr';
    if (savedPct !== null) {
      detail += ' (saving ' + savedPct + '% tax)';
    }
    return { date: null, detail: detail };
  }

  function _estimateTaxSaving(years, brackets) {
    if (!brackets || brackets.length < 2) return null;
    var baseRate = brackets[0].rate * 100;
    for (var i = 0; i < brackets.length; i++) {
      if (brackets[i].min_years <= years) {
        var currentRate = brackets[i].rate * 100;
        var saving = baseRate - currentRate;
        if (saving > 0) return Math.round(saving);
      }
    }
    return null;
  }

  function _detectSavingsStreak() {
    if (!ds || !ds.invested_eur || !ds.dates || ds.dates.length < 90) return null;
    var monthlyDeposits = {};
    for (var i = 1; i < ds.dates.length; i++) {
      var diff = ds.invested_eur[i] - ds.invested_eur[i - 1];
      if (diff > 0) {
        var month = ds.dates[i].slice(0, 7);
        monthlyDeposits[month] = (monthlyDeposits[month] || 0) + diff;
      }
    }
    var months = Object.keys(monthlyDeposits).sort();
    if (months.length < 3) return null;

    var maxStreak = 0, streak = 1;
    for (var m = 1; m < months.length; m++) {
      var prev = months[m - 1].split('-');
      var curr = months[m].split('-');
      var prevDate = new Date(parseInt(prev[0]), parseInt(prev[1]) - 1);
      var currDate = new Date(parseInt(curr[0]), parseInt(curr[1]) - 1);
      var diffMonths = (currDate.getFullYear() - prevDate.getFullYear()) * 12 + (currDate.getMonth() - prevDate.getMonth());
      if (diffMonths === 1) { streak++; }
      else { streak = 1; }
      if (streak > maxStreak) maxStreak = streak;
    }
    if (maxStreak < 3) return null;
    return { date: null, detail: maxStreak + ' consecutive months of deposits' };
  }

  function _detectPortfolioAge(targetDays) {
    if (!ds || !ds.dates || ds.dates.length < 2) return null;
    var firstDate = new Date(ds.dates[0]);
    var lastDate = new Date(ds.dates[ds.dates.length - 1]);
    var days = Math.round((lastDate - firstDate) / 86400000);
    if (days < targetDays) return null;
    var anniversaryDate = new Date(firstDate.getTime() + targetDays * 86400000);
    var dateStr = anniversaryDate.toISOString().slice(0, 10);
    return { date: dateStr, detail: Math.floor(days / 365) + ' year' + (Math.floor(days / 365) > 1 ? 's' : '') + ' of investing' };
  }

  // --- Persistence ---

  function getEarnedAchievements() {
    var raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    try { return JSON.parse(raw); } catch (e) { return {}; }
  }

  function saveEarnedAchievements(earned) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(earned));
  }

  // --- Core logic: detect all achievements and find new ones ---

  function detectAll() {
    var earned = getEarnedAchievements();
    var newlyEarned = [];

    for (var i = 0; i < ACHIEVEMENTS.length; i++) {
      var ach = ACHIEVEMENTS[i];
      var result = ach.detect();
      if (result && !earned[ach.id]) {
        earned[ach.id] = {
          date: result.date || new Date().toISOString().slice(0, 10),
          detail: result.detail,
          earnedAt: Date.now()
        };
        newlyEarned.push(ach);
      }
    }

    if (newlyEarned.length > 0) {
      saveEarnedAchievements(earned);
    }

    return { earned: earned, newlyEarned: newlyEarned };
  }

  // --- Achievement Toast (non-blocking, bottom-right) ---

  function showAchievementToast(achievement) {
    var earned = getEarnedAchievements();
    var data = earned[achievement.id];
    var toast = document.createElement('div');
    toast.className = 'achievement-toast';
    toast.innerHTML = '<div class="achievement-toast-inner">'
      + '<div class="achievement-toast-icon">' + achievement.icon + '</div>'
      + '<div class="achievement-toast-body">'
      + '<div class="achievement-toast-title">Achievement Unlocked</div>'
      + '<div class="achievement-toast-name">' + achievement.title + '</div>'
      + (data && data.detail ? '<div class="achievement-toast-detail">' + data.detail + '</div>' : '')
      + '</div>'
      + '<button class="achievement-toast-close" aria-label="Dismiss">&times;</button>'
      + '</div>';

    document.body.appendChild(toast);

    requestAnimationFrame(function() {
      toast.classList.add('achievement-toast-visible');
    });

    var dismiss = function() {
      toast.classList.remove('achievement-toast-visible');
      toast.classList.add('achievement-toast-exit');
      setTimeout(function() { toast.remove(); }, 300);
    };

    toast.querySelector('.achievement-toast-close').addEventListener('click', dismiss);
    setTimeout(dismiss, 5000);
  }

  function showNewAchievementToasts(newlyEarned) {
    var shownRaw = localStorage.getItem(TOAST_SHOWN_KEY);
    var shown = shownRaw ? JSON.parse(shownRaw) : [];
    var delay = 0;

    for (var i = 0; i < newlyEarned.length; i++) {
      if (shown.indexOf(newlyEarned[i].id) >= 0) continue;
      shown.push(newlyEarned[i].id);
      (function(ach, d) {
        setTimeout(function() { showAchievementToast(ach); }, d);
      })(newlyEarned[i], delay);
      delay += 1200;
    }

    localStorage.setItem(TOAST_SHOWN_KEY, JSON.stringify(shown));
  }

  // --- Milestones Section Rendering ---

  function renderAchievementsSection() {
    var section = scopedFind(null, 'achievementsSection');
    if (!section) return;

    var earned = getEarnedAchievements();
    var earnedIds = Object.keys(earned);
    if (earnedIds.length === 0) { section.style.display = 'none'; return; }

    section.style.display = '';
    var grid = scopedFind(null, 'achievementsGrid');
    if (!grid) return;

    var items = [];
    for (var i = 0; i < ACHIEVEMENTS.length; i++) {
      var ach = ACHIEVEMENTS[i];
      var data = earned[ach.id];
      if (!data) continue;
      items.push({ ach: ach, data: data });
    }

    items.sort(function(a, b) { return (b.data.earnedAt || 0) - (a.data.earnedAt || 0); });

    grid.innerHTML = items.map(function(item) {
      var dateStr = item.data.date ? '<span class="ach-date">' + item.data.date + '</span>' : '';
      return '<div class="ach-card" data-achievement-id="' + item.ach.id + '">'
        + '<div class="ach-card-icon">' + item.ach.icon + '</div>'
        + '<div class="ach-card-body">'
        + '<div class="ach-card-title">' + item.ach.title + '</div>'
        + '<div class="ach-card-detail">' + (item.data.detail || '') + '</div>'
        + dateStr
        + '</div>'
        + '<button class="ach-share-btn" title="Copy as image" data-ach-id="' + item.ach.id + '">&#x1F4CB;</button>'
        + '</div>';
    }).join('');

    // Lock section: show unearned as locked
    var locked = [];
    for (var j = 0; j < ACHIEVEMENTS.length; j++) {
      if (!earned[ACHIEVEMENTS[j].id]) {
        locked.push(ACHIEVEMENTS[j]);
      }
    }
    if (locked.length > 0) {
      grid.innerHTML += '<div class="ach-locked-row">'
        + locked.map(function(ach) {
          return '<div class="ach-card ach-locked" title="Not yet earned">'
            + '<div class="ach-card-icon">&#x1F512;</div>'
            + '<div class="ach-card-body"><div class="ach-card-title">' + ach.title + '</div></div>'
            + '</div>';
        }).join('')
        + '</div>';
    }

    // Bind share buttons
    var btns = grid.querySelectorAll('.ach-share-btn');
    for (var b = 0; b < btns.length; b++) {
      btns[b].addEventListener('click', _handleShare);
    }
  }

  // --- Share/Export Achievement as PNG ---

  function _handleShare(e) {
    var btn = e.currentTarget;
    var achId = btn.getAttribute('data-ach-id');
    var card = btn.closest('.ach-card');
    if (!card) return;

    _exportCardAsPng(card, achId);
  }

  function _exportCardAsPng(card, achId) {
    var canvas = document.createElement('canvas');
    var w = 400, h = 120;
    canvas.width = w * 2;
    canvas.height = h * 2;
    var ctx = canvas.getContext('2d');
    ctx.scale(2, 2);

    // Background
    var isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    ctx.fillStyle = isDark ? '#111520' : '#ffffff';
    ctx.beginPath();
    if (ctx.roundRect) {
      ctx.roundRect(0, 0, w, h, 10);
    } else {
      ctx.rect(0, 0, w, h);
    }
    ctx.fill();

    // Border
    ctx.strokeStyle = isDark ? '#1e2636' : '#e2e5ea';
    ctx.lineWidth = 1;
    ctx.stroke();

    // Icon
    ctx.font = '28px serif';
    ctx.textBaseline = 'middle';
    var ach = _getAchById(achId);
    var iconText = ach ? _htmlEntityToText(ach.icon) : '';
    ctx.fillText(iconText, 16, h / 2 - 5);

    // Title
    ctx.font = '600 14px Inter, sans-serif';
    ctx.fillStyle = isDark ? '#e8eaed' : '#1a1d23';
    ctx.fillText(ach ? ach.title : '', 60, 35);

    // Detail
    var earned = getEarnedAchievements();
    var data = earned[achId];
    if (data && data.detail) {
      ctx.font = '12px Inter, sans-serif';
      ctx.fillStyle = isDark ? '#8b9ab5' : '#6b7280';
      ctx.fillText(data.detail, 60, 58);
    }

    // Branding
    ctx.font = '10px Inter, sans-serif';
    ctx.fillStyle = isDark ? '#4a5568' : '#9ca3af';
    ctx.fillText('WealthEagle Portfolio', 60, 85);
    if (data && data.date) {
      ctx.fillText(data.date, 60, 100);
    }

    canvas.toBlob(function(blob) {
      if (!blob) return;
      if (navigator.clipboard && navigator.clipboard.write) {
        navigator.clipboard.write([
          new ClipboardItem({ 'image/png': blob })
        ]).then(function() {
          _showCopiedFeedback(card);
        }).catch(function() {
          _fallbackDownload(blob, achId);
        });
      } else {
        _fallbackDownload(blob, achId);
      }
    }, 'image/png');
  }

  function _showCopiedFeedback(card) {
    var btn = card.querySelector('.ach-share-btn');
    if (!btn) return;
    var orig = btn.innerHTML;
    btn.innerHTML = '&#x2714;';
    btn.classList.add('ach-share-success');
    setTimeout(function() {
      btn.innerHTML = orig;
      btn.classList.remove('ach-share-success');
    }, 1500);
  }

  function _fallbackDownload(blob, achId) {
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'achievement-' + achId + '.png';
    a.click();
    URL.revokeObjectURL(url);
  }

  function _getAchById(id) {
    for (var i = 0; i < ACHIEVEMENTS.length; i++) {
      if (ACHIEVEMENTS[i].id === id) return ACHIEVEMENTS[i];
    }
    return null;
  }

  function _htmlEntityToText(html) {
    var el = document.createElement('span');
    el.innerHTML = html;
    return el.textContent;
  }

  // --- Chart.js Plugin for Milestone Markers ---

  var milestoneMarkersPlugin = {
    id: 'milestoneMarkers',
    afterDraw: function(chart) {
      if (chart.canvas.getAttribute('data-role') !== 'portfolioChart') return;
      var markers = _getChartMarkers();
      if (markers.length === 0) return;

      var xScale = chart.scales.x;
      var yScale = chart.scales.y;
      var ctx = chart.ctx;

      for (var i = 0; i < markers.length; i++) {
        var m = markers[i];
        var xPos = xScale.getPixelForValue(new Date(m.date).getTime());
        if (xPos < xScale.left || xPos > xScale.right) continue;

        // Vertical dashed line
        ctx.save();
        ctx.setLineDash([4, 4]);
        ctx.strokeStyle = 'rgba(245, 158, 11, 0.4)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(xPos, yScale.top);
        ctx.lineTo(xPos, yScale.bottom);
        ctx.stroke();

        // Small icon at top
        ctx.setLineDash([]);
        ctx.font = '10px serif';
        ctx.textAlign = 'center';
        ctx.fillText(_htmlEntityToText(m.icon), xPos, yScale.top - 4);
        ctx.restore();
      }
    }
  };

  function _getChartMarkers() {
    var earned = getEarnedAchievements();
    var markers = [];
    for (var i = 0; i < ACHIEVEMENTS.length; i++) {
      var ach = ACHIEVEMENTS[i];
      var data = earned[ach.id];
      if (!data || !data.date) continue;
      if (ach.category === 'value' || ach.id === 'first_dividend' || ach.id === 'first_year') {
        markers.push({ date: data.date, icon: ach.icon });
      }
    }
    return markers;
  }

  // Register Chart.js plugin
  if (typeof Chart !== 'undefined') {
    Chart.register(milestoneMarkersPlugin);
  }

  // --- Public API ---

  window.updateAchievements = function() {
    var result = detectAll();
    renderAchievementsSection();
    return result;
  };

  window.showAchievementToasts = function() {
    var result = detectAll();
    if (result.newlyEarned.length > 0) {
      showNewAchievementToasts(result.newlyEarned);
    }
  };

  // Run on load
  var result = detectAll();
  renderAchievementsSection();
  if (result.newlyEarned.length > 0) {
    setTimeout(function() {
      showNewAchievementToasts(result.newlyEarned);
    }, 1500);
  }
})();
