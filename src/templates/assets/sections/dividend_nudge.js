// --- Dividend Countdown Nudge Banner ---
(function() {
  var STORAGE_KEY = 'dividendNudgeDismissed';
  var WINDOW_DAYS = 14;
  var MS_PER_DAY = 1000 * 60 * 60 * 24;

  var container = scopedFind(null, 'dividendNudgeWidget');
  if (!container) return;

  var cal = D.dividend_calendar;
  if (!cal || !cal.upcoming || cal.upcoming.length === 0) return;

  function isDismissed() {
    try {
      var s = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
      if (s && s.until && new Date(s.until) > new Date()) return true;
    } catch (e) {}
    return false;
  }

  if (isDismissed()) return;

  var today = new Date();
  today.setHours(0, 0, 0, 0);

  // Find the soonest upcoming ex-dividend event within WINDOW_DAYS
  var soonest = null;
  for (var i = 0; i < cal.upcoming.length; i++) {
    var ev = cal.upcoming[i];
    if (!ev.ex_date) continue;
    var exDate = new Date(ev.ex_date);
    exDate.setHours(0, 0, 0, 0);
    var daysUntil = Math.round((exDate - today) / MS_PER_DAY);
    if (daysUntil < 0) continue; // past
    if (daysUntil > WINDOW_DAYS) continue; // too far out
    if (!soonest || daysUntil < soonest.daysUntil) {
      soonest = { ev: ev, daysUntil: daysUntil };
    }
  }

  if (!soonest) return;

  var ev = soonest.ev;
  var daysUntil = soonest.daysUntil;
  var income = ev.projected_income_eur;
  var incomeStr = income != null ? ' (est. ' + fmtCcy(income) + ')' : '';
  var daysLabel = daysUntil === 0 ? 'today' : daysUntil === 1 ? 'in 1 day' : 'in ' + daysUntil + ' days';

  var banner = document.createElement('div');
  banner.className = 'dividend-nudge-banner';
  banner.innerHTML =
    '<span class="dividend-nudge-icon">&#128181;</span>' +
    '<span class="dividend-nudge-text">' +
      '<strong>' + ev.ticker + '</strong> goes ex-dividend <strong>' + daysLabel + '</strong>' + incomeStr + '.' +
    '</span>' +
    '<button class="dividend-nudge-action">View dividend calendar &rarr;</button>' +
    '<button class="dividend-nudge-dismiss" title="Dismiss for 1 day">&times;</button>';

  banner.querySelector('.dividend-nudge-action').addEventListener('click', function() {
    if (window.switchPage) window.switchPage('dividends');
  });

  banner.querySelector('.dividend-nudge-dismiss').addEventListener('click', function(e) {
    e.stopPropagation();
    var until = new Date(today.getTime() + MS_PER_DAY).toISOString();
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ until: until })); } catch (err) {}
    container.style.display = 'none';
    container.innerHTML = '';
  });

  container.appendChild(banner);
  container.style.display = '';
})();
