/**
 * Custom Dashboard - Gridstack.js initialization and event handlers
 */

/**
 * Maps widget IDs to their section init functions.
 * Each init function receives the widget's inner container element so that
 * scopedFind(container, role) resolves elements within that widget clone,
 * not the hidden #widgetTemplates pool or the predefined page elements.
 *
 * Functions must be defined after section JS is loaded; this object is
 * populated lazily on first access via getWidgetInitFn().
 */
const WIDGET_INIT_MAP = {
  'quick-glance':  function() { if (window._quickGlanceRefresh) window._quickGlanceRefresh(); },
  'health-score':  function() { if (typeof initHealthScore === 'function') initHealthScore(); },
  'summary':       function() { if (typeof updateSummary === 'function') updateSummary(); if (typeof updateMilestones === 'function') updateMilestones(); },
  'charts':        function() { if (typeof buildPortfolioChart === 'function') buildPortfolioChart(); },
  'positions':     function() { if (typeof updatePositions === 'function') updatePositions(); if (typeof updateTopMovers === 'function') updateTopMovers(); },
  'dividends':     function() { if (typeof updateDividends === 'function') updateDividends(); },
  'projections':   function() { if (typeof updateFire === 'function') updateFire(); },
  'notes':         function() { if (typeof initNotesWidget === 'function') initNotesWidget(); },
  'real-estate':   function() { if (typeof updateRealEstate === 'function') updateRealEstate(); },
  'risk':          function() { if (typeof updateRiskPage === 'function') updateRiskPage(); },
  'dca-strategy':  function() { if (typeof updateDCAStrategy === 'function') updateDCAStrategy(); },
  'tax-summary':   function() { if (typeof updateTaxTable === 'function') updateTaxTable(); },
  'tax-calendar':  function() { if (typeof updateYearEndCalendar === 'function') updateYearEndCalendar(); },
  'smart-sell':    function() { if (typeof updateSmartSell === 'function') updateSmartSell(); },
  'tax-wizard':    function() { if (typeof initTaxWizard === 'function') initTaxWizard(); },
  'transactions':  function() { if (typeof updateTransactions === 'function') updateTransactions(); },
};

/**
 * Destroy any Chart.js instances living inside a widget container.
 * Called before removeWidget to prevent memory leaks.
 */
function destroyWidgetCharts(container) {
  if (!container || typeof Chart === 'undefined') return;
  container.querySelectorAll('canvas').forEach(function(canvas) {
    var chart = Chart.getChart(canvas);
    if (chart) chart.destroy();
  });
}

const WIDGET_REGISTRY = {
  'quick-glance': { label: 'Quick Glance', minW: 3, minH: 2 },
  'health-score': { label: 'Health Score', minW: 3, minH: 2 },
  'summary': { label: 'Summary', minW: 4, minH: 3 },
  'charts': { label: 'Charts', minW: 6, minH: 4 },
  'positions': { label: 'Positions', minW: 6, minH: 3 },
  'dividends': { label: 'Dividends', minW: 4, minH: 3 },
  'projections': { label: 'Projections', minW: 4, minH: 3 },
  'notes': { label: 'Notes', minW: 4, minH: 2 },
  'real-estate': { label: 'Real Estate', minW: 4, minH: 3 },
  'risk': { label: 'Risk', minW: 4, minH: 3 },
  'dca-strategy': { label: 'DCA Strategy', minW: 4, minH: 3 },
  'tax-summary': { label: 'Tax Summary', minW: 6, minH: 4 },
  'tax-calendar': { label: 'Tax Calendar', minW: 4, minH: 3 },
  'smart-sell': { label: 'Smart Sell', minW: 4, minH: 3 },
  'tax-wizard': { label: 'Tax Wizard', minW: 4, minH: 3 },
  'transactions': { label: 'History', minW: 6, minH: 3 },
};

let gridstack = null;
let dashboardEditMode = false;
let dashboardLoadPromise = null;

/**
 * Initialize dashboard on page load
 */
function initDashboard() {
  const navDashboard = document.getElementById('navDashboard');

  // Show nav item only for premium/admin users
  if (D.user && D.user.role && ['premium', 'admin', 'cofounder'].includes(D.user.role)) {
    if (navDashboard) {
      navDashboard.style.display = '';
    }

    // Add click handler to dashboard nav
    if (navDashboard) {
      navDashboard.addEventListener('click', () => showDashboard());
    }
  }

  // Set up edit button
  const editBtn = document.getElementById('dashboardEditBtn');
  if (editBtn) {
    editBtn.addEventListener('click', toggleEditMode);
  }

  // Preserve a saved dashboard route on reload while keeping other routes lazy.
  const dashboardPage = document.getElementById('page-dashboard');
  if (dashboardPage && dashboardPage.classList.contains('active')) {
    showDashboard();
  }
}

/**
 * Show dashboard section and hide others
 */
function showDashboard() {
  // Hide all content sections
  document.querySelectorAll('.content-section').forEach(el => {
    el.style.display = 'none';
  });

  // Show dashboard
  const dashboard = document.getElementById('dashboard');
  if (dashboard) {
    dashboard.style.display = '';
  }

  // Initialize Gridstack if needed
  if (!gridstack) {
    initGridstack();
  }

  // Dashboard is off-screen for most report visits. Defer API, Gridstack
  // widget creation, and section initialization until first use.
  if (!dashboardLoadPromise) {
    dashboardLoadPromise = loadDashboardLayout();
  }

  // Update nav item active state
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.remove('active');
  });
  const navDashboard = document.getElementById('navDashboard');
  if (navDashboard) {
    navDashboard.classList.add('active');
  }
}

/**
 * Initialize Gridstack grid
 */
function initGridstack() {
  const container = document.getElementById('dashboardGrid');
  if (!container) return;

  if (typeof GridStack === 'undefined') return;
  var isMobile = window.innerWidth <= 768;
  gridstack = GridStack.init({
    column: isMobile ? 1 : 12,
    float: true,
    animate: false,
    disableOneColumnMode: false,
    oneColumnSize: 768,
    cellHeight: 80,
    draggable: { handle: '.grid-stack-item-content' },
    resizable: { handles: isMobile ? '' : 'se' },
  }, container);

  // Disable dragging/resizing initially
  gridstack.disable();
}

/**
 * Load layout from API and render widgets
 */
async function loadDashboardLayout() {
  try {
    const response = await fetch('/api/dashboard-layout');
    const data = await response.json();

    const widgets = data.widgets || [];
    const isDefault = data.isDefault || false;

    // Show/hide default banner
    const banner = document.getElementById('dashboardDefaultBanner');
    if (banner) {
      banner.style.display = isDefault ? '' : 'none';
    }

    // Render widgets
    renderWidgets(widgets);

    // Populate widget picker
    populateWidgetPicker(widgets);

  } catch (error) {
    console.error('Failed to load dashboard layout:', error);
  }
}

/**
 * Render widgets from layout
 */
function renderWidgets(widgets) {
  if (!gridstack) {
    initGridstack();
  }

  // Clear existing widgets
  gridstack.removeAll();

  // Add each widget
  widgets.forEach(widget => {
    const { id, x, y, w, h } = widget;

    // Find template for this widget
    const template = document.getElementById(`widget-${id}`);
    if (!template) {
      console.warn(`No template found for widget: ${id}`);
      return;
    }

    // Clone template content
    const content = template.content.firstElementChild.cloneNode(true);
    content.style.display = '';

    // Create grid item
    const item = document.createElement('div');
    item.className = 'grid-stack-item';
    item.setAttribute('gs-x', x);
    item.setAttribute('gs-y', y);
    item.setAttribute('gs-w', w);
    item.setAttribute('gs-h', h);
    item.setAttribute('data-widget-id', id);

    // Add content wrapper
    const innerDiv = document.createElement('div');
    innerDiv.className = 'grid-stack-item-content';
    innerDiv.appendChild(content);
    item.appendChild(innerDiv);

    // Add to grid
    gridstack.addWidget(item);

    const initFn = WIDGET_INIT_MAP[id];
    if (initFn) {
      requestAnimationFrame(function() {
        _widgetScope = innerDiv;
        try { initFn(innerDiv); } finally { _widgetScope = null; }
      });
    }
  });
}

/**
 * Populate widget picker with available widgets
 */
function populateWidgetPicker(currentWidgets) {
  const pickerList = document.getElementById('widgetPickerList');
  if (!pickerList) return;

  const currentIds = currentWidgets.map(w => w.id);
  pickerList.innerHTML = '';

  Object.entries(WIDGET_REGISTRY).forEach(([id, meta]) => {
    const isAdded = currentIds.includes(id);

    const item = document.createElement('div');
    item.className = 'widget-picker-item' + (isAdded ? ' added' : '');

    const btn = document.createElement('button');
    btn.className = 'btn btn-sm' + (isAdded ? ' btn-danger' : '');
    btn.textContent = isAdded ? 'Remove' : 'Add';

    const label = document.createElement('div');
    label.className = 'widget-picker-label';
    label.textContent = meta.label;

    item.appendChild(label);
    item.appendChild(btn);

    btn.addEventListener('click', () => {
      if (isAdded) {
        removeWidget(id);
      } else {
        addWidget(id);
      }
      const current = [];
      gridstack.getGridItems().forEach(el => {
        var wid = el.getAttribute('data-widget-id');
        if (wid) current.push({ id: wid });
      });
      populateWidgetPicker(current);
    });

    pickerList.appendChild(item);
  });
}

/**
 * Toggle edit mode
 */
function toggleEditMode() {
  dashboardEditMode = !dashboardEditMode;
  const editBtn = document.getElementById('dashboardEditBtn');
  const pickerBackdrop = document.getElementById('widgetPickerBackdrop');
  const picker = document.getElementById('widgetPicker');

  if (dashboardEditMode) {
    // Enter edit mode
    gridstack.enable();
    if (editBtn) editBtn.classList.add('active');

    // Show widget picker
    if (pickerBackdrop) pickerBackdrop.style.display = '';
    if (picker) picker.style.display = '';

    // Add remove buttons to widgets
    document.querySelectorAll('[data-widget-id]').forEach(el => {
      const btn = document.createElement('button');
      btn.className = 'widget-remove-btn';
      btn.textContent = '×';
      btn.setAttribute('aria-label', 'Remove widget');
      btn.addEventListener('click', () => {
        const id = el.getAttribute('data-widget-id');
        removeWidget(id);
      });
      el.appendChild(btn);
    });
  } else {
    // Exit edit mode
    gridstack.disable();
    if (editBtn) editBtn.classList.remove('active');

    // Hide widget picker
    if (pickerBackdrop) pickerBackdrop.style.display = 'none';
    if (picker) picker.style.display = 'none';

    // Remove remove buttons
    document.querySelectorAll('.widget-remove-btn').forEach(btn => btn.remove());

    // Save layout
    saveDashboardLayout();
  }
}

/**
 * Add widget to grid
 */
function addWidget(widgetId) {
  if (!gridstack) return;

  const meta = WIDGET_REGISTRY[widgetId];
  if (!meta) return;

  // Find template
  const template = document.getElementById(`widget-${widgetId}`);
  if (!template) return;

  // Clone template
  const content = template.cloneNode(true);
  content.style.display = '';

  // Create item
  const item = document.createElement('div');
  item.className = 'grid-stack-item';
  item.setAttribute('gs-w', meta.defaultW || 4);
  item.setAttribute('gs-h', meta.defaultH || 2);
  item.setAttribute('data-widget-id', widgetId);

  const innerDiv = document.createElement('div');
  innerDiv.className = 'grid-stack-item-content';
  innerDiv.appendChild(content);
  item.appendChild(innerDiv);

  // Add remove button
  const removeBtn = document.createElement('button');
  removeBtn.className = 'widget-remove-btn';
  removeBtn.textContent = '×';
  removeBtn.setAttribute('aria-label', 'Remove widget');
  removeBtn.addEventListener('click', () => removeWidget(widgetId));
  item.appendChild(removeBtn);

  // Add to grid
  gridstack.addWidget(item);

  const initFn = WIDGET_INIT_MAP[widgetId];
  if (initFn) {
    requestAnimationFrame(function() {
      _widgetScope = innerDiv;
      try { initFn(innerDiv); } finally { _widgetScope = null; }
    });
  }
}

/**
 * Remove widget from grid
 */
function removeWidget(widgetId) {
  if (!gridstack) return;

  const item = document.querySelector(`[data-widget-id="${widgetId}"]`);
  if (item) {
    // Destroy any Chart.js instances before removing to free memory
    destroyWidgetCharts(item);
    gridstack.removeWidget(item);
  }
}

/**
 * Save dashboard layout to server
 */
async function saveDashboardLayout() {
  if (!gridstack) return;

  const widgets = [];
  gridstack.getGridItems().forEach(el => {
    var n = el.gridstackNode;
    if (!n) return;
    var wid = el.getAttribute('data-widget-id');
    if (!wid) return;
    widgets.push({
      id: wid,
      x: n.x || 0,
      y: n.y || 0,
      w: n.w || 4,
      h: n.h || 2,
    });
  });

  try {
    const response = await fetch('/api/dashboard-layout', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ widgets }),
    });

    if (!response.ok) {
      const error = await response.json();
      alert(`Failed to save layout: ${error.error}`);
    }
  } catch (error) {
    console.error('Failed to save dashboard layout:', error);
    alert('Failed to save layout');
  }
}

/**
 * Close widget picker
 */
function closeWidgetPicker() {
  const pickerBackdrop = document.getElementById('widgetPickerBackdrop');
  const picker = document.getElementById('widgetPicker');

  if (pickerBackdrop) pickerBackdrop.style.display = 'none';
  if (picker) picker.style.display = 'none';
}

// Wire up widget picker close button
document.addEventListener('DOMContentLoaded', () => {
  const closeBtn = document.getElementById('widgetPickerClose');
  const backdrop = document.getElementById('widgetPickerBackdrop');

  if (closeBtn) {
    closeBtn.addEventListener('click', closeWidgetPicker);
  }

  if (backdrop) {
    backdrop.addEventListener('click', closeWidgetPicker);
  }

  initDashboard();
});
