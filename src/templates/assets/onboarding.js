// --- Interactive guided tour for first-time demo visitors ---
(function() {
  var STORAGE_KEY = 'tour_completed';
  var steps = [
    {
      target: '#summary',
      title: 'Your portfolio at a glance',
      text: 'Value, gains, CAGR, and more — all your key metrics in one place.',
      position: 'bottom'
    },
    {
      target: '.sidebar-nav .nav-item[data-page="tax"]',
      title: 'Automatic tax calculation',
      text: 'Ready for eDavki export — see estimated obligations, holding periods, and generate XML reports.',
      position: 'right'
    },
    {
      target: '.sidebar-nav .nav-item[data-page="charts"]',
      title: 'Benchmark your returns',
      text: 'Compare your portfolio performance against S&P 500 and 6 other indexes.',
      position: 'right'
    },
    {
      target: '.sidebar-nav .nav-item[data-page="projections"]',
      title: 'FIRE projections',
      text: 'Plan your financial independence with Monte Carlo simulations and withdrawal scenarios.',
      position: 'right'
    },
    {
      target: null,
      title: 'Ready to see your own data?',
      text: 'Upload your Revolut CSV to get personalized portfolio analytics and tax reports.',
      position: 'center',
      isCTA: true
    }
  ];

  var currentStep = 0;
  var overlay = null;
  var tooltip = null;
  var spotlight = null;

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
    var isMobile = window.innerWidth < 768;

    if (step.isCTA) {
      spotlight.style.display = 'none';
      tooltip.style.display = 'block';
      tooltip.style.left = '50%';
      tooltip.style.top = '50%';
      tooltip.style.transform = 'translate(-50%, -50%)';
      tooltip.style.right = 'auto';
      tooltip.style.position = 'fixed';
      renderTooltip(step);
      return;
    }

    tooltip.style.position = 'absolute';
    var el = document.querySelector(step.target);
    if (!el) { nextStep(); return; }

    // Make hidden nav items visible for targeting
    if (el.style.display === 'none') {
      el.style.display = '';
      el.setAttribute('data-tour-revealed', '1');
    }

    var rect = el.getBoundingClientRect();
    var scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    var scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;

    var pad = 6;
    spotlight.style.top = (rect.top + scrollTop - pad) + 'px';
    spotlight.style.left = (rect.left + scrollLeft - pad) + 'px';
    spotlight.style.width = (rect.width + pad * 2) + 'px';
    spotlight.style.height = (rect.height + pad * 2) + 'px';
    spotlight.style.display = 'block';

    renderTooltip(step);

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

  function renderTooltip(step) {
    var progress = (currentStep + 1) + ' / ' + steps.length;
    var footerHTML;

    if (step.isCTA) {
      footerHTML =
        '<div class="tour-tooltip-footer tour-cta-footer">' +
          '<span class="tour-tooltip-progress">' + progress + '</span>' +
          '<div class="tour-tooltip-actions">' +
            '<a href="/" class="tour-btn tour-btn-next tour-btn-upload">Upload Now</a>' +
            '<button class="tour-btn tour-btn-back tour-btn-explore">Explore Demo</button>' +
          '</div>' +
        '</div>';
    } else {
      footerHTML =
        '<div class="tour-tooltip-footer">' +
          '<span class="tour-tooltip-progress">' + progress + '</span>' +
          '<div class="tour-tooltip-actions">' +
            (currentStep > 0 ? '<button class="tour-btn tour-btn-back">Back</button>' : '') +
            '<button class="tour-btn tour-btn-next">Next</button>' +
          '</div>' +
        '</div>';
    }

    tooltip.innerHTML =
      '<div class="tour-tooltip-header">' +
        '<span class="tour-tooltip-title">' + step.title + '</span>' +
        '<button class="tour-tooltip-close" aria-label="Skip tour">&times;</button>' +
      '</div>' +
      '<p class="tour-tooltip-text">' + step.text + '</p>' +
      footerHTML;

    tooltip.querySelector('.tour-tooltip-close').addEventListener('click', endTour);

    if (step.isCTA) {
      tooltip.querySelector('.tour-btn-explore').addEventListener('click', endTour);
    } else {
      tooltip.querySelector('.tour-btn-next').addEventListener('click', nextStep);
      var backBtn = tooltip.querySelector('.tour-btn-back');
      if (backBtn) backBtn.addEventListener('click', prevStep);
    }

    tooltip.style.display = 'block';
  }

  function showStep() {
    if (currentStep >= steps.length) { endTour(); return; }
    var step = steps[currentStep];
    if (!step.isCTA) {
      var el = document.querySelector(step.target);
      if (!el) {
        currentStep++;
        showStep();
        return;
      }
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

  function cleanup() {
    // Restore any nav items we revealed
    var revealed = document.querySelectorAll('[data-tour-revealed]');
    for (var i = 0; i < revealed.length; i++) {
      revealed[i].style.display = 'none';
      revealed[i].removeAttribute('data-tour-revealed');
    }
    if (overlay) overlay.remove();
    if (spotlight) spotlight.remove();
    if (tooltip) tooltip.remove();
    overlay = null; spotlight = null; tooltip = null;
  }

  function endTour() {
    localStorage.setItem(STORAGE_KEY, 'true');
    cleanup();
  }

  function startTour() {
    if (overlay) cleanup();
    currentStep = 0;
    createOverlay();
    showStep();
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

  // Auto-start on first visit
  if (localStorage.getItem(STORAGE_KEY) !== 'true') {
    setTimeout(startTour, 600);
  }

  // Expose globally for the help icon
  window.replayTour = function() {
    localStorage.removeItem(STORAGE_KEY);
    startTour();
  };
})();
