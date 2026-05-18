// --- Portfolio Health Score ---
(function() {
  var hs = D.health_score;
  var section = document.getElementById('healthScoreSection');
  if (!hs || !section) return;

  section.style.display = '';

  // Overall badge
  var grade = document.getElementById('healthScoreGrade');
  var num   = document.getElementById('healthScoreNum');
  var lbl   = document.getElementById('healthScoreLabel');
  var fill  = document.getElementById('healthScoreBarFill');
  var badge = document.getElementById('healthScoreBadge');

  if (grade) grade.textContent = hs.grade;
  if (num)   num.textContent   = Math.round(hs.overall) + '/100';
  if (lbl)   lbl.textContent   = hs.label;

  // Bar fill + colour
  var pct = Math.max(0, Math.min(100, hs.overall));
  var barColor = pct >= 80 ? 'var(--green)' : pct >= 50 ? 'var(--accent)' : 'var(--red)';
  if (fill) {
    fill.style.width = pct + '%';
    fill.style.background = barColor;
  }
  if (badge) badge.style.setProperty('--hs-color', barColor);

  // Sub-scores
  var subEl = document.getElementById('healthSubScores');
  if (subEl && hs.sub_scores) {
    var catIcons = {
      'Diversification':    '&#9635;',
      'Concentration Risk': '&#9650;',
      'Tax Efficiency':     '&#128197;',
      'Drawdown Risk':      '&#9660;',
    };
    subEl.innerHTML = hs.sub_scores.map(function(s) {
      var sp = Math.max(0, Math.min(100, s.score));
      var sc = sp >= 80 ? 'pos' : sp >= 50 ? 'warn' : 'neg';
      var icon = catIcons[s.name] || '&#8226;';
      return '<div class="health-sub">'
        + '<div class="health-sub-header">'
        + '<span class="health-sub-icon">' + icon + '</span>'
        + '<span class="health-sub-name">' + s.name + '</span>'
        + '<span class="health-sub-score ' + sc + '">' + Math.round(sp) + '</span>'
        + '<span class="health-sub-lbl ' + sc + '">' + s.label + '</span>'
        + '</div>'
        + '<div class="health-sub-bar-track"><div class="health-sub-bar-fill ' + sc + '" style="width:' + sp + '%"></div></div>'
        + '<div class="health-sub-detail">' + s.detail + '</div>'
        + '</div>';
    }).join('');
  }

  // Actions
  var actionsSection = document.getElementById('healthActions');
  var actionsList    = document.getElementById('healthActionsList');
  if (actionsSection && actionsList && hs.actions && hs.actions.length > 0) {
    var catClass = {
      concentration: 'action-concentration',
      diversification: 'action-diversification',
      tax: 'action-tax',
      risk: 'action-risk',
    };
    var catLabel = {
      concentration: 'Concentration',
      diversification: 'Diversification',
      tax: 'Tax',
      risk: 'Risk',
    };
    actionsList.innerHTML = hs.actions.map(function(a, i) {
      var cc = catClass[a.category] || '';
      var cl = catLabel[a.category] || a.category;
      return '<div class="health-action-item ' + cc + '">'
        + '<div class="action-tag">' + cl + '</div>'
        + '<div class="action-title">' + a.title + '</div>'
        + '<div class="action-detail">' + a.detail + '</div>'
        + '</div>';
    }).join('');
    actionsSection.style.display = '';
  }
})();
