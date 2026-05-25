// --- eDavki Filing Deadline Tracker Widget ---
(function() {
  var container = scopedFind(null, 'edavkiDeadlineWidget');
  if (!container) return;

  var meta = D.edavki_meta;
  if (!meta) return;

  var today = new Date();
  var currentYear = today.getFullYear();
  var currentMonth = today.getMonth() + 1; // 1-based

  // eDavki filing windows: Feb 28 (primary, Jan–Feb), or Oct 31 (optional, Oct–Nov)
  // Slovenian Doh-KDVP deadline: last day of February for prior year.
  // Optional capital-gains review: Oct 31 (year-end planning window).
  var PRIMARY_DEADLINE_MONTH = 2;
  var PRIMARY_DEADLINE_DAY = 28;
  var SECONDARY_DEADLINE_MONTH = 10;
  var SECONDARY_DEADLINE_DAY = 31;

  function getDeadline() {
    // Primary: show January through February → deadline Feb 28 of current year
    if (currentMonth <= PRIMARY_DEADLINE_MONTH) {
      var d = new Date(currentYear, PRIMARY_DEADLINE_MONTH - 1, PRIMARY_DEADLINE_DAY);
      return { date: d, label: 'eDavki Filing Deadline', year: currentYear - 1, kind: 'primary' };
    }
    // Secondary: show October through November → deadline Oct 31 of current year
    if (currentMonth >= SECONDARY_DEADLINE_MONTH && currentMonth <= SECONDARY_DEADLINE_MONTH + 1) {
      var d2 = new Date(currentYear, SECONDARY_DEADLINE_MONTH - 1, SECONDARY_DEADLINE_DAY);
      return { date: d2, label: 'Year-End Tax Review Deadline', year: currentYear - 1, kind: 'secondary' };
    }
    return null;
  }

  var deadline = getDeadline();
  if (!deadline) return;

  // Check dismissal: server-side dismissed_until or local sessionStorage backup
  var SESSION_KEY = 'edavkiDeadlineDismissed';
  function isDismissed() {
    // Server-side dismissal
    if (meta.dismissed_until) {
      try {
        if (new Date(meta.dismissed_until) > today) return true;
      } catch (e) {}
    }
    // Session fallback
    try {
      var s = JSON.parse(sessionStorage.getItem(SESSION_KEY) || 'null');
      if (s && s.until && new Date(s.until) > today) return true;
    } catch (e) {}
    return false;
  }

  if (isDismissed()) return;

  var filedYears = meta.filed_years || [];
  var filingYear = deadline.year; // the tax year being filed
  if (filedYears.indexOf(filingYear) !== -1) return; // already filed

  var yearsWithTx = meta.years_with_transactions || [];
  var pendingYears = yearsWithTx.filter(function(y) {
    return y <= filingYear && filedYears.indexOf(y) === -1;
  });

  if (pendingYears.length === 0) return; // nothing to file

  // Compute countdown
  var msLeft = deadline.date - today;
  var daysLeft = Math.ceil(msLeft / (1000 * 60 * 60 * 24));
  if (daysLeft < 0) return; // past deadline

  // Build checklist
  var checks = [];

  // 1. Last import freshness
  var lastImportDays = null;
  if (meta.last_import_at) {
    try {
      lastImportDays = Math.floor((today - new Date(meta.last_import_at)) / (1000 * 60 * 60 * 24));
    } catch (e) {}
  }
  if (lastImportDays === null) {
    checks.push({ cls: 'check-err', icon: '&#10007;', text: 'No imports found — import your Revolut CSV first' });
  } else if (lastImportDays > 14) {
    checks.push({ cls: 'check-warn', icon: '&#9888;', text: 'Last import was <strong>' + lastImportDays + ' days ago</strong> — consider re-importing' });
  } else {
    var d = new Date(meta.last_import_at);
    checks.push({ cls: 'check-ok', icon: '&#10003;', text: 'Data imported on <strong>' + d.toISOString().slice(0, 10) + '</strong>' });
  }

  // 2. Price sync freshness
  var lastSyncDays = null;
  if (meta.last_sync_date) {
    try {
      lastSyncDays = Math.floor((today - new Date(meta.last_sync_date)) / (1000 * 60 * 60 * 24));
    } catch (e) {}
  }
  if (lastSyncDays === null) {
    checks.push({ cls: 'check-warn', icon: '&#9888;', text: 'Prices not synced yet — run a sync for accurate FX rates' });
  } else if (lastSyncDays > 7) {
    checks.push({ cls: 'check-warn', icon: '&#9888;', text: 'Prices last synced <strong>' + lastSyncDays + ' days ago</strong>' });
  } else {
    checks.push({ cls: 'check-ok', icon: '&#10003;', text: 'Prices synced on <strong>' + meta.last_sync_date + '</strong>' });
  }

  // 3. Pending years
  if (pendingYears.length > 1) {
    checks.push({ cls: 'check-warn', icon: '&#9888;', text: 'Pending tax years: <strong>' + pendingYears.join(', ') + '</strong>' });
  } else {
    checks.push({ cls: 'check-ok', icon: '&#10003;', text: 'Tax year <strong>' + pendingYears[0] + '</strong> ready to generate' });
  }

  // Build widget DOM
  var urgentClass = daysLeft <= 7 ? ' urgent' : '';
  var countdownText = daysLeft === 0 ? 'Today!' : daysLeft === 1 ? '1 day left' : daysLeft + ' days left';

  var widget = document.createElement('div');
  widget.className = 'edavki-deadline-widget';

  var header = document.createElement('div');
  header.className = 'edavki-deadline-header';
  header.innerHTML =
    '<span class="edavki-deadline-icon">&#128203;</span>' +
    '<span class="edavki-deadline-title">' + deadline.label + ' &mdash; ' + filingYear + '</span>' +
    '<span class="edavki-deadline-countdown' + urgentClass + '">' + countdownText + '</span>' +
    '<button class="edavki-deadline-dismiss" title="Dismiss for 7 days">&times;</button>';

  var body = document.createElement('div');
  body.className = 'edavki-deadline-body';

  var ul = document.createElement('ul');
  ul.className = 'edavki-checklist';
  for (var i = 0; i < checks.length; i++) {
    var li = document.createElement('li');
    li.innerHTML =
      '<span class="' + checks[i].cls + '">' + checks[i].icon + '</span>' +
      '<span>' + checks[i].text + '</span>';
    ul.appendChild(li);
  }

  var actions = document.createElement('div');
  actions.className = 'edavki-deadline-actions';

  // Year selector (only if multiple pending years)
  var yearSelect = null;
  if (pendingYears.length > 1) {
    yearSelect = document.createElement('select');
    yearSelect.className = 'edavki-year-select';
    for (var pi = 0; pi < pendingYears.length; pi++) {
      var opt = document.createElement('option');
      opt.value = pendingYears[pi];
      opt.textContent = pendingYears[pi];
      yearSelect.appendChild(opt);
    }
    actions.appendChild(yearSelect);
  }

  var genBtn = document.createElement('button');
  genBtn.className = 'edavki-generate-btn';
  genBtn.textContent = 'Generate XML';
  genBtn.addEventListener('click', function() {
    var yr = yearSelect ? parseInt(yearSelect.value) : pendingYears[0];
    window.location.href = '/export/edavki?year=' + yr;
  });
  actions.appendChild(genBtn);

  var filedBtn = document.createElement('button');
  filedBtn.className = 'edavki-filed-btn';
  filedBtn.textContent = 'Mark as Filed';
  filedBtn.addEventListener('click', function() {
    var yr = yearSelect ? parseInt(yearSelect.value) : pendingYears[0];
    var newFiled = (meta.filed_years || []).concat([yr]);
    fetch('/api/edavki-filed', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filed_years: newFiled }),
    }).then(function() {
      container.style.display = 'none';
      container.innerHTML = '';
    }).catch(function() {
      container.style.display = 'none';
    });
  });
  actions.appendChild(filedBtn);

  body.appendChild(ul);
  body.appendChild(actions);
  widget.appendChild(header);
  widget.appendChild(body);
  container.appendChild(widget);
  container.style.display = '';

  // Dismiss handler: snooze for 7 days via server + sessionStorage backup
  header.querySelector('.edavki-deadline-dismiss').addEventListener('click', function() {
    var snoozeUntil = new Date(today.getTime() + 7 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
    fetch('/api/edavki-filed', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dismissed_until: snoozeUntil }),
    }).catch(function() {});
    try { sessionStorage.setItem(SESSION_KEY, JSON.stringify({ until: snoozeUntil })); } catch (e) {}
    container.style.display = 'none';
    container.innerHTML = '';
  });
})();
