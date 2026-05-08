// --- Guided onboarding tour for first-time users ---
(function() {
  var STORAGE_KEY = 'onboarding_completed';
  var SESSION_KEY = 'onboarding_session_count';

  if (localStorage.getItem(STORAGE_KEY) === 'true') return;

  var sessionCount = parseInt(localStorage.getItem(SESSION_KEY) || '0', 10) + 1;
  localStorage.setItem(SESSION_KEY, String(sessionCount));

  var steps = [
    {
      target: '.sidebar-nav .nav-item[data-page="overview"]',
      title: 'Welcome to your Portfolio',
      text: 'This is your dashboard. Start here for a quick snapshot of your total value, gains, and key metrics.',
      position: 'right'
    },
    {
      target: '#regimeFilter',
      title: 'Tax Country',
      text: 'Select your tax jurisdiction here. This adjusts all tax calculations and holding period rules.',
      position: 'right'
    },
    {
      target: '.sidebar-nav .nav-item[data-page="charts"]',
      title: 'Performance Charts',
      text: 'Track your portfolio growth over time with interactive charts. Compare against benchmarks.',
      position: 'right'
    },
    {
      target: '.sidebar-nav .nav-item[data-page="positions"]',
      title: 'Positions',
      text: 'View all your open and closed positions. See individual stock performance and allocation.',
      position: 'right'
    },
    {
      target: '.sidebar-nav .nav-item[data-page="tax"]',
      title: 'Tax Reports',
      text: 'Generate tax reports for eDavki filing. See estimated tax obligations and holding period countdowns.',
      position: 'right'
    },
    {
      target: '.sidebar-nav .nav-item[data-page="history"]',
      title: 'Transaction History',
      text: 'Browse all imported transactions. This is where your CSV data appears after import.',
      position: 'right'
    },
    {
      target: '.sidebar-footer',
      title: 'Keyboard Navigation',
      text: 'Use arrow keys or number keys (1-8) to switch between sections. Press ? for all shortcuts.',
      position: 'right'
    }
  ];

  var currentStep = 0;
  var overlay = null;
  var tooltip = null;
  var spotlight = null;
  var checklist = null;

  function createOverlay() {
    overlay = document.createElement('div');
    overlay.className = 'tour-overlay';
    overlay.addEventListener('click', function(e) {
      if (e.target === overlay) nextStep();
    });
    document.body.appendChild(overlay);

    spotlight = document.createElement('div');
    spotlight.className = 'tour-spotlight';
    document.body.appendChild(spotlight);

    tooltip = document.createElement('div');
    tooltip.className = 'tour-tooltip';
    document.body.appendChild(tooltip);
  }

  function positionTooltip(step) {
    var el = document.querySelector(step.target);
    if (!el) { nextStep(); return; }

    var rect = el.getBoundingClientRect();
    var scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    var scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;

    var pad = 6;
    spotlight.style.top = (rect.top + scrollTop - pad) + 'px';
    spotlight.style.left = (rect.left + scrollLeft - pad) + 'px';
    spotlight.style.width = (rect.width + pad * 2) + 'px';
    spotlight.style.height = (rect.height + pad * 2) + 'px';
    spotlight.style.display = 'block';

    var progress = (currentStep + 1) + ' / ' + steps.length;
    tooltip.innerHTML =
      '<div class="tour-tooltip-header">' +
        '<span class="tour-tooltip-title">' + step.title + '</span>' +
        '<button class="tour-tooltip-close" aria-label="Skip tour">&times;</button>' +
      '</div>' +
      '<p class="tour-tooltip-text">' + step.text + '</p>' +
      '<div class="tour-tooltip-footer">' +
        '<span class="tour-tooltip-progress">' + progress + '</span>' +
        '<div class="tour-tooltip-actions">' +
          (currentStep > 0 ? '<button class="tour-btn tour-btn-back">Back</button>' : '') +
          '<button class="tour-btn tour-btn-next">' +
            (currentStep === steps.length - 1 ? 'Done' : 'Next') +
          '</button>' +
        '</div>' +
      '</div>';

    tooltip.querySelector('.tour-tooltip-close').addEventListener('click', endTour);
    tooltip.querySelector('.tour-btn-next').addEventListener('click', nextStep);
    var backBtn = tooltip.querySelector('.tour-btn-back');
    if (backBtn) backBtn.addEventListener('click', prevStep);

    tooltip.style.display = 'block';
    var isMobile = window.innerWidth < 768;

    if (isMobile) {
      tooltip.style.left = '50%';
      tooltip.style.transform = 'translateX(-50%)';
      tooltip.style.top = (rect.bottom + scrollTop + 16) + 'px';
      tooltip.style.right = 'auto';
    } else if (step.position === 'right') {
      tooltip.style.left = (rect.right + scrollLeft + 16) + 'px';
      tooltip.style.top = (rect.top + scrollTop) + 'px';
      tooltip.style.transform = '';
      tooltip.style.right = 'auto';
    } else if (step.position === 'bottom') {
      tooltip.style.left = (rect.left + scrollLeft) + 'px';
      tooltip.style.top = (rect.bottom + scrollTop + 16) + 'px';
      tooltip.style.transform = '';
      tooltip.style.right = 'auto';
    }

    var ttRect = tooltip.getBoundingClientRect();
    if (ttRect.right > window.innerWidth - 16) {
      tooltip.style.left = 'auto';
      tooltip.style.right = '16px';
      tooltip.style.transform = '';
    }
    if (ttRect.bottom > window.innerHeight - 16 && !isMobile) {
      tooltip.style.top = (rect.top + scrollTop - ttRect.height - 16) + 'px';
    }
  }

  function showStep() {
    if (currentStep >= steps.length) { endTour(); return; }
    var step = steps[currentStep];
    var el = document.querySelector(step.target);
    if (!el || el.style.display === 'none') {
      currentStep++;
      showStep();
      return;
    }
    positionTooltip(step);
  }

  function nextStep() {
    currentStep++;
    if (currentStep >= steps.length) { endTour(); return; }
    showStep();
  }

  function prevStep() {
    if (currentStep > 0) { currentStep--; showStep(); }
  }

  function endTour() {
    localStorage.setItem(STORAGE_KEY, 'true');
    if (overlay) overlay.remove();
    if (spotlight) spotlight.remove();
    if (tooltip) tooltip.remove();
    overlay = null; spotlight = null; tooltip = null;
    if (checklist) { checklist.style.opacity = '0'; setTimeout(function() { if (checklist) checklist.remove(); checklist = null; }, 300); }
  }

  function startTour() {
    currentStep = 0;
    createOverlay();
    showStep();
  }

  function buildChecklist() {
    if (sessionCount > 3) return;
    checklist = document.createElement('div');
    checklist.className = 'tour-checklist';
    checklist.innerHTML =
      '<div class="tour-checklist-header">' +
        '<span>Getting Started</span>' +
        '<button class="tour-checklist-close" aria-label="Dismiss">&times;</button>' +
      '</div>' +
      '<ul class="tour-checklist-items">' +
        '<li data-check="import"><span class="tour-check-icon"></span> Import your CSV data</li>' +
        '<li data-check="sync"><span class="tour-check-icon"></span> Sync market prices</li>' +
        '<li data-check="overview"><span class="tour-check-icon"></span> Review portfolio summary</li>' +
        '<li data-check="tax"><span class="tour-check-icon"></span> Check tax estimates</li>' +
      '</ul>' +
      '<button class="tour-btn tour-btn-next tour-checklist-replay">Replay Tour</button>';

    var hasData = D && D.summary && D.summary.total_value_eur > 0;
    var hasPrices = D && D.daily_series && D.daily_series.dates && D.daily_series.dates.length > 0;
    if (hasData) checklist.querySelector('[data-check="import"]').classList.add('checked');
    if (hasPrices) checklist.querySelector('[data-check="sync"]').classList.add('checked');
    if (hasData) checklist.querySelector('[data-check="overview"]').classList.add('checked');

    checklist.querySelector('.tour-checklist-close').addEventListener('click', function() {
      checklist.style.opacity = '0';
      setTimeout(function() { if (checklist) checklist.remove(); checklist = null; }, 300);
    });
    checklist.querySelector('.tour-checklist-replay').addEventListener('click', function() {
      if (checklist) { checklist.remove(); checklist = null; }
      localStorage.removeItem(STORAGE_KEY);
      startTour();
    });

    document.body.appendChild(checklist);
  }

  function handleKeydown(e) {
    if (!overlay) return;
    if (e.key === 'Escape') { endTour(); e.preventDefault(); }
    if (e.key === 'ArrowRight' || e.key === 'Enter') { nextStep(); e.preventDefault(); }
    if (e.key === 'ArrowLeft') { prevStep(); e.preventDefault(); }
  }

  document.addEventListener('keydown', handleKeydown);

  window.addEventListener('resize', function() {
    if (overlay && currentStep < steps.length) positionTooltip(steps[currentStep]);
  });

  if (sessionCount === 1) {
    setTimeout(startTour, 600);
  }
  buildChecklist();
})();
