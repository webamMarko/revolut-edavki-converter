// --- Dashboard Layout Customization ---
(function() {
  var STORAGE_KEY = 'dashboardLayout';
  var customizeMode = false;

  var DEFAULT_NAV_ORDER = [
    'overview', 'charts', 'positions', 'risk', 'dividends',
    'projections', 'notes', 'realestate', 'tax', 'history'
  ];

  var DEFAULT_CARD_ORDER = [
    'summary.portfolio_value', 'summary.total_invested', 'summary.absolute_gain',
    'summary.total_return', 'summary.cagr', 'summary.twr', 'summary.max_drawdown',
    'summary.avg_yearly_growth', 'summary.avg_yearly_return', 'summary.avg_yearly_invested'
  ];

  var PRESETS = {
    'tax-focused': {
      navOrder: ['overview', 'tax', 'positions', 'history', 'charts', 'risk', 'dividends', 'projections', 'notes', 'realestate'],
      cardOrder: ['summary.portfolio_value', 'summary.absolute_gain', 'summary.total_return', 'summary.max_drawdown', 'summary.cagr', 'summary.twr', 'summary.total_invested', 'summary.avg_yearly_growth', 'summary.avg_yearly_return', 'summary.avg_yearly_invested'],
      hiddenCards: []
    },
    'growth-focused': {
      navOrder: ['overview', 'charts', 'projections', 'positions', 'risk', 'dividends', 'notes', 'realestate', 'tax', 'history'],
      cardOrder: ['summary.total_return', 'summary.cagr', 'summary.twr', 'summary.portfolio_value', 'summary.absolute_gain', 'summary.avg_yearly_growth', 'summary.avg_yearly_return', 'summary.total_invested', 'summary.max_drawdown', 'summary.avg_yearly_invested'],
      hiddenCards: []
    },
    'income-focused': {
      navOrder: ['overview', 'dividends', 'positions', 'charts', 'projections', 'tax', 'risk', 'notes', 'realestate', 'history'],
      cardOrder: ['summary.portfolio_value', 'summary.total_invested', 'summary.avg_yearly_invested', 'summary.total_return', 'summary.absolute_gain', 'summary.cagr', 'summary.twr', 'summary.avg_yearly_growth', 'summary.avg_yearly_return', 'summary.max_drawdown'],
      hiddenCards: []
    }
  };

  function loadLayout() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (raw) return JSON.parse(raw);
    } catch(e) {}
    return null;
  }

  function saveLayout(layout) {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(layout)); } catch(e) {}
  }

  function getLayout() {
    return loadLayout() || { navOrder: DEFAULT_NAV_ORDER.slice(), cardOrder: DEFAULT_CARD_ORDER.slice(), hiddenCards: [] };
  }

  // --- Nav reordering ---
  function applyNavOrder(order) {
    var nav = document.querySelector('.sidebar-nav');
    if (!nav) return;
    var items = nav.querySelectorAll('.nav-item[data-page]');
    var divider = nav.querySelector('.nav-divider');
    var itemMap = {};
    items.forEach(function(el) { itemMap[el.dataset.page] = el; });

    order.forEach(function(page) {
      var el = itemMap[page];
      if (el) {
        if (divider) nav.insertBefore(el, divider);
        else nav.appendChild(el);
      }
    });
    if (divider) nav.appendChild(divider);
    items.forEach(function(el) {
      if (order.indexOf(el.dataset.page) === -1) nav.appendChild(el);
    });
  }

  // --- Summary card reordering ---
  window._layoutGetCardOrder = function() {
    var layout = getLayout();
    return { order: layout.cardOrder, hidden: layout.hiddenCards || [] };
  };

  // --- Drag and drop for nav items ---
  var dragSrc = null;
  var dragType = null;

  function initNavDrag() {
    var nav = document.querySelector('.sidebar-nav');
    if (!nav) return;
    var items = nav.querySelectorAll('.nav-item[data-page]');

    items.forEach(function(item) {
      item.setAttribute('draggable', 'true');

      item.addEventListener('dragstart', function(e) {
        if (!customizeMode) { e.preventDefault(); return; }
        dragSrc = item;
        dragType = 'nav';
        item.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', item.dataset.page);
      });

      item.addEventListener('dragend', function() {
        item.classList.remove('dragging');
        nav.querySelectorAll('.nav-item').forEach(function(el) { el.classList.remove('drag-over'); });
        dragSrc = null;
        dragType = null;
      });

      item.addEventListener('dragover', function(e) {
        if (!customizeMode || dragType !== 'nav') return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        item.classList.add('drag-over');
      });

      item.addEventListener('dragleave', function() {
        item.classList.remove('drag-over');
      });

      item.addEventListener('drop', function(e) {
        e.preventDefault();
        item.classList.remove('drag-over');
        if (!dragSrc || dragSrc === item || dragType !== 'nav') return;

        var nav = item.parentNode;
        var items = Array.from(nav.querySelectorAll('.nav-item[data-page]'));
        var srcIdx = items.indexOf(dragSrc);
        var tgtIdx = items.indexOf(item);

        if (srcIdx < tgtIdx) {
          nav.insertBefore(dragSrc, item.nextSibling);
        } else {
          nav.insertBefore(dragSrc, item);
        }

        saveCurrentNavOrder();
      });
    });
  }

  function saveCurrentNavOrder() {
    var nav = document.querySelector('.sidebar-nav');
    if (!nav) return;
    var items = nav.querySelectorAll('.nav-item[data-page]');
    var order = [];
    items.forEach(function(el) { order.push(el.dataset.page); });
    var layout = getLayout();
    layout.navOrder = order;
    saveLayout(layout);
  }

  // --- Drag and drop for summary cards ---
  function initCardDrag() {
    var grid = scopedFind(null, 'summary');
    if (!grid) return;

    grid.addEventListener('dragstart', function(e) {
      var card = e.target.closest('.metric-card');
      if (!customizeMode || !card) { e.preventDefault(); return; }
      dragSrc = card;
      dragType = 'card';
      card.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', card.dataset.cardKey || '');
    });

    grid.addEventListener('dragend', function(e) {
      var card = e.target.closest('.metric-card');
      if (card) card.classList.remove('dragging');
      grid.querySelectorAll('.metric-card').forEach(function(el) { el.classList.remove('drag-over'); });
      dragSrc = null;
      dragType = null;
    });

    grid.addEventListener('dragover', function(e) {
      if (!customizeMode || dragType !== 'card') return;
      var card = e.target.closest('.metric-card');
      if (!card || card === dragSrc) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      grid.querySelectorAll('.metric-card').forEach(function(el) { el.classList.remove('drag-over'); });
      card.classList.add('drag-over');
    });

    grid.addEventListener('dragleave', function(e) {
      var card = e.target.closest('.metric-card');
      if (card) card.classList.remove('drag-over');
    });

    grid.addEventListener('drop', function(e) {
      e.preventDefault();
      var card = e.target.closest('.metric-card');
      if (!card || !dragSrc || dragSrc === card || dragType !== 'card') return;
      card.classList.remove('drag-over');

      var cards = Array.from(grid.querySelectorAll('.metric-card'));
      var srcIdx = cards.indexOf(dragSrc);
      var tgtIdx = cards.indexOf(card);

      if (srcIdx < tgtIdx) {
        grid.insertBefore(dragSrc, card.nextSibling);
      } else {
        grid.insertBefore(dragSrc, card);
      }

      saveCurrentCardOrder();
    });
  }

  function saveCurrentCardOrder() {
    var grid = scopedFind(null, 'summary');
    if (!grid) return;
    var cards = grid.querySelectorAll('.metric-card[data-card-key]');
    var order = [];
    cards.forEach(function(el) { order.push(el.dataset.cardKey); });
    var layout = getLayout();
    layout.cardOrder = order;
    saveLayout(layout);
  }

  // --- Hide/show card ---
  function toggleCardVisibility(cardKey) {
    var layout = getLayout();
    if (!layout.hiddenCards) layout.hiddenCards = [];
    var idx = layout.hiddenCards.indexOf(cardKey);
    if (idx >= 0) {
      layout.hiddenCards.splice(idx, 1);
    } else {
      layout.hiddenCards.push(cardKey);
    }
    saveLayout(layout);
    if (window.updateSummary) updateSummary();
  }

  // --- Customize mode ---
  function setCustomizeMode(enabled) {
    customizeMode = enabled;
    document.body.classList.toggle('customize-mode', enabled);
    var btn = scopedFind(null, 'customizeToggle');
    if (btn) {
      btn.classList.toggle('active', enabled);
      btn.textContent = enabled ? 'Done' : 'Customize';
    }
    var presetBar = scopedFind(null, 'layoutPresets');
    if (presetBar) presetBar.style.display = enabled ? '' : 'none';

    // Show/hide card visibility toggles
    var cards = document.querySelectorAll('.metric-card .card-hide-btn');
    cards.forEach(function(el) { el.style.display = enabled ? '' : 'none'; });
  }

  // --- Preset application ---
  function applyPreset(name) {
    var preset = PRESETS[name];
    if (!preset) return;
    var layout = { navOrder: preset.navOrder.slice(), cardOrder: preset.cardOrder.slice(), hiddenCards: (preset.hiddenCards || []).slice() };
    saveLayout(layout);
    applyNavOrder(layout.navOrder);
    if (window.updateSummary) updateSummary();
    highlightActivePreset(name);
  }

  function highlightActivePreset(name) {
    var btns = document.querySelectorAll('.preset-btn');
    btns.forEach(function(b) { b.classList.toggle('active', b.dataset.preset === name); });
  }

  function detectActivePreset() {
    var layout = getLayout();
    for (var name in PRESETS) {
      var p = PRESETS[name];
      if (JSON.stringify(p.navOrder) === JSON.stringify(layout.navOrder) &&
          JSON.stringify(p.cardOrder) === JSON.stringify(layout.cardOrder)) {
        return name;
      }
    }
    return null;
  }

  // --- Reset to default ---
  function resetLayout() {
    localStorage.removeItem(STORAGE_KEY);
    applyNavOrder(DEFAULT_NAV_ORDER);
    if (window.updateSummary) updateSummary();
    highlightActivePreset(null);
  }

  // --- Build UI ---
  function buildCustomizeUI() {
    var sidebar = document.querySelector('.sidebar');
    if (!sidebar) return;

    var footer = sidebar.querySelector('.sidebar-footer');
    var container = document.createElement('div');
    container.className = 'customize-controls';
    container.innerHTML = '<button id="customizeToggle" class="customize-btn">Customize</button>'
      + '<div id="layoutPresets" class="preset-bar" style="display:none">'
      + '<button class="preset-btn" data-preset="tax-focused">Tax</button>'
      + '<button class="preset-btn" data-preset="growth-focused">Growth</button>'
      + '<button class="preset-btn" data-preset="income-focused">Income</button>'
      + '<button class="preset-btn reset-btn" data-preset="reset">Reset</button>'
      + '</div>';

    if (footer) sidebar.insertBefore(container, footer);
    else sidebar.appendChild(container);

    scopedFind(null, 'customizeToggle').addEventListener('click', function() {
      setCustomizeMode(!customizeMode);
    });

    container.querySelectorAll('.preset-btn').forEach(function(btn) {
      btn.addEventListener('click', function() {
        if (btn.dataset.preset === 'reset') {
          resetLayout();
        } else {
          applyPreset(btn.dataset.preset);
        }
      });
    });

    var active = detectActivePreset();
    if (active) highlightActivePreset(active);
  }

  // --- Initialize ---
  function init() {
    var layout = getLayout();
    applyNavOrder(layout.navOrder);
    buildCustomizeUI();
    initNavDrag();
    initCardDrag();
  }

  window._layoutToggleCardVisibility = toggleCardVisibility;
  window._layoutIsCustomizeMode = function() { return customizeMode; };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
