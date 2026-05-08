// --- Tax Wizard ---
(function() {
  var wizard = document.getElementById('wizardStepper');
  if (!wizard) return;

  var STORAGE_KEY = 'taxWizardState';
  var totalSteps = 6;
  var currentStep = 1;
  var selectedYear = null;
  var completedSteps = {};

  // Determine available years from tax data
  var tby = D.tax_by_year || {};
  var dtby = D.dividend_tax || {};
  var allYears = Object.keys(tby).map(Number).sort(function(a, b) { return b - a; });
  if (!allYears.length) allYears = Object.keys(dtby).map(Number).sort(function(a, b) { return b - a; });

  // Restore persisted state
  function loadState() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        var s = JSON.parse(raw);
        if (s.year && (tby[s.year] || dtby[s.year])) {
          selectedYear = s.year;
          completedSteps = s.completed || {};
          currentStep = s.currentStep || 1;
        }
      }
    } catch(e) {}
  }

  function saveState() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        year: selectedYear,
        currentStep: currentStep,
        completed: completedSteps
      }));
    } catch(e) {}
  }

  // Default to previous year
  function defaultYear() {
    var prev = new Date().getFullYear() - 1;
    if (allYears.indexOf(prev) !== -1) return prev;
    return allYears[0] || null;
  }

  // Render year grid
  function renderYearGrid() {
    var grid = document.getElementById('wizardYearGrid');
    if (!grid) return;
    grid.innerHTML = '';
    allYears.forEach(function(yr) {
      var btn = document.createElement('button');
      btn.className = 'wizard-year-btn' + (yr === selectedYear ? ' active' : '');
      btn.textContent = yr;
      btn.addEventListener('click', function() {
        selectedYear = yr;
        grid.querySelectorAll('.wizard-year-btn').forEach(function(b) { b.classList.remove('active'); });
        btn.classList.add('active');
        completedSteps[1] = true;
        saveState();
      });
      grid.appendChild(btn);
    });
  }

  // Render capital gains summary for step 2
  function renderCapGains() {
    var cards = document.getElementById('wizCapGainsCards');
    var detail = document.getElementById('wizCapGainsDetail');
    if (!cards) return;

    var ty = tby[selectedYear];
    if (!ty || !ty.realized_sales || ty.realized_sales.length === 0) {
      cards.innerHTML = '<div class="wizard-empty-note"><p>No realized capital gains/losses for ' + selectedYear + '.</p></div>';
      if (detail) detail.innerHTML = '';
      return;
    }

    var sales = ty.realized_sales;
    var totalGain = 0, totalTax = 0, totalProceeds = 0, totalCost = 0;
    for (var i = 0; i < sales.length; i++) {
      totalGain += sales[i].gain_eur;
      totalTax += sales[i].tax_eur;
      totalProceeds += sales[i].sell_price_eur;
      totalCost += sales[i].cost_basis_eur;
    }

    cards.innerHTML = [
      ['Total Proceeds', fmtCcy(totalProceeds), ''],
      ['Total Cost Basis', fmtCcy(totalCost), ''],
      ['Net Gain/Loss', signCcy(totalGain), cls(totalGain)],
      ['Estimated Tax', fmtCcy(totalTax), 'neg']
    ].map(function(r) {
      return '<div class="metric-card"><div class="label">' + r[0] + '</div><div class="value ' + r[2] + '">' + r[1] + '</div></div>';
    }).join('');

    if (detail) {
      detail.innerHTML = '<p style="color:var(--muted);font-size:0.8rem;margin-top:0.75rem">' +
        sales.length + ' transaction' + (sales.length > 1 ? 's' : '') + ' across ' +
        _uniqueTickers(sales) + ' ticker' + (_uniqueTickers(sales) > 1 ? 's' : '') + '</p>';
    }

    completedSteps[2] = true;
    saveState();
  }

  function _uniqueTickers(sales) {
    var s = {};
    for (var i = 0; i < sales.length; i++) s[sales[i].ticker] = 1;
    return Object.keys(s).length;
  }

  // Render dividend summary for step 3
  function renderDividends() {
    var cards = document.getElementById('wizDivCards');
    var detail = document.getElementById('wizDivDetail');
    if (!cards) return;

    var data = dtby[selectedYear];
    if (!data) {
      cards.innerHTML = '<div class="wizard-empty-note"><p>No dividend income for ' + selectedYear + '. You can skip this step.</p></div>';
      if (detail) detail.innerHTML = '';
      completedSteps[3] = true;
      saveState();
      return;
    }

    cards.innerHTML = [
      ['Gross Dividends', fmtCcy(data.total_gross_eur), ''],
      ['WHT Paid', signCcy(-data.total_withholding_eur), 'neg'],
      ['SI Tax (25%)', fmtCcy(data.si_tax_liability), 'neg'],
      ['Treaty Credit', signCcy(-data.total_credit_eur), 'pos'],
      ['Net Tax Owed', fmtCcy(data.net_tax_owed_si), data.net_tax_owed_si > 0 ? 'neg' : '']
    ].map(function(r) {
      return '<div class="metric-card"><div class="label">' + r[0] + '</div><div class="value ' + r[2] + '">' + r[1] + '</div></div>';
    }).join('');

    if (detail && data.by_country) {
      var countries = Object.keys(data.by_country).length;
      detail.innerHTML = '<p style="color:var(--muted);font-size:0.8rem;margin-top:0.75rem">' +
        'Dividends from ' + countries + ' countr' + (countries > 1 ? 'ies' : 'y') + '</p>';
    }

    completedSteps[3] = true;
    saveState();
  }

  // Step 4: Doh-KDVP download
  function renderDownloadKdvp() {
    var yearEl = document.getElementById('wizKdvpYear');
    if (yearEl) yearEl.textContent = selectedYear;

    var btn = document.getElementById('wizDownloadKdvp');
    if (btn && !btn._wired) {
      btn._wired = true;
      btn.addEventListener('click', function() {
        var a = document.createElement('a');
        a.href = '/export/edavki?year=' + selectedYear;
        a.download = '';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        completedSteps[4] = true;
        updateStepper();
        saveState();
      });
    }
  }

  // Step 5: Doh-Div download
  function renderDownloadDohDiv() {
    var yearEl = document.getElementById('wizDivYear');
    if (yearEl) yearEl.textContent = selectedYear;

    var hasDiv = !!dtby[selectedYear];
    var btn = document.getElementById('wizDownloadDohDiv');
    var noData = document.getElementById('wizNoDivData');

    if (!hasDiv) {
      if (btn) btn.style.display = 'none';
      if (noData) noData.style.display = '';
      completedSteps[5] = true;
      saveState();
      return;
    }

    if (btn) btn.style.display = '';
    if (noData) noData.style.display = 'none';

    if (btn && !btn._wired) {
      btn._wired = true;
      btn.addEventListener('click', function() {
        window.location.href = '/export/doh-div?year=' + selectedYear;
        completedSteps[5] = true;
        updateStepper();
        saveState();
      });
    }
  }

  // Step 6: Checklist
  function renderChecklist() {
    var checks = document.querySelectorAll('.wizard-checkbox');
    var stored = completedSteps[6] || {};
    checks.forEach(function(cb, idx) {
      cb.checked = !!stored[idx];
      cb.onchange = function() {
        if (!completedSteps[6]) completedSteps[6] = {};
        completedSteps[6][idx] = cb.checked;
        var allDone = true;
        checks.forEach(function(c) { if (!c.checked) allDone = false; });
        if (allDone) completedSteps['6_done'] = true;
        saveState();
      };
    });
  }

  // Navigation
  var btnNext = document.getElementById('wizBtnNext');
  var btnBack = document.getElementById('wizBtnBack');
  var progressText = document.getElementById('wizProgressText');

  function goToStep(step) {
    if (step < 1) step = 1;
    if (step > totalSteps + 1) step = totalSteps + 1;

    // Mark current step completed when navigating forward
    if (step > currentStep && currentStep <= totalSteps) {
      completedSteps[currentStep] = completedSteps[currentStep] || true;
    }

    currentStep = step;
    saveState();

    // Show/hide panels
    for (var i = 1; i <= totalSteps; i++) {
      var panel = document.getElementById('wizStep' + i);
      if (panel) panel.style.display = (i === step) ? '' : 'none';
    }
    var donePanel = document.getElementById('wizStepDone');
    if (donePanel) donePanel.style.display = (step > totalSteps) ? '' : 'none';

    // Footer
    var footer = document.getElementById('wizardFooter');
    if (footer) footer.style.display = (step > totalSteps) ? 'none' : '';
    if (btnBack) btnBack.style.display = (step <= 1) ? 'none' : '';
    if (btnNext) {
      if (step === totalSteps) {
        btnNext.textContent = 'Complete';
      } else {
        btnNext.textContent = 'Continue';
      }
    }
    if (progressText) progressText.textContent = 'Step ' + Math.min(step, totalSteps) + ' of ' + totalSteps;

    updateStepper();
    renderStepContent(step);
  }

  function renderStepContent(step) {
    if (step === 1) renderYearGrid();
    if (step === 2) renderCapGains();
    if (step === 3) renderDividends();
    if (step === 4) renderDownloadKdvp();
    if (step === 5) renderDownloadDohDiv();
    if (step === 6) renderChecklist();
    if (step > totalSteps) renderDone();
  }

  function renderDone() {
    var el = document.getElementById('wizDoneYear');
    if (el) el.textContent = selectedYear;
    var btn = document.getElementById('wizDoneBtn');
    if (btn && !btn._wired) {
      btn._wired = true;
      btn.addEventListener('click', function() {
        window.switchPage('overview');
      });
    }
  }

  function updateStepper() {
    var steps = wizard.querySelectorAll('.wizard-step');
    steps.forEach(function(el) {
      var s = parseInt(el.dataset.step);
      el.classList.toggle('active', s === currentStep);
      el.classList.toggle('done', s < currentStep || (completedSteps[s] && s !== currentStep));
    });
  }

  if (btnNext) btnNext.addEventListener('click', function() {
    if (currentStep === 1 && !selectedYear) {
      selectedYear = defaultYear();
      renderYearGrid();
    }
    goToStep(currentStep + 1);
  });

  if (btnBack) btnBack.addEventListener('click', function() {
    goToStep(currentStep - 1);
  });

  // Close button returns to tax page
  var closeBtn = document.getElementById('wizardCloseBtn');
  if (closeBtn) closeBtn.addEventListener('click', function() {
    window.switchPage('tax');
  });

  // Done button
  var doneBtn = document.getElementById('wizDoneBtn');

  // Initialize
  loadState();
  if (!selectedYear) selectedYear = defaultYear();
  goToStep(currentStep);

  // Expose function to open wizard from outside
  window.openTaxWizard = function(year) {
    if (year) selectedYear = year;
    goToStep(1);
    window.switchPage('taxwizard');
  };
})();
