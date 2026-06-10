// --- Real Estate section ---
function updateRealEstate() {
try {
  const RE = D.real_estate;
  if (RE && RE.properties && RE.properties.length > 0) {
    scopedFind(null, 'realEstateSection').style.display = '';


    const propTypeLabels = {
      stanovanje: 'Apartment', hisa: 'House', garaza: 'Garage',
      poslovni: 'Commercial', zemljisce: 'Land'
    };

    // Primary metrics: PROPERTIES and UNREALIZED GAIN % (visible by default)
    scopedFind(null, 'reCards').innerHTML = createPrimaryMetrics(RE.properties.length, RE.total_gain_pct);

    // Secondary metrics: PURCHASE TOTAL and ETN ESTIMATE (hidden by default)
    scopedFind(null, 'reCardsSecondary').innerHTML = createSecondaryMetrics(RE.total_purchase_eur, RE.total_estimated_eur);

    // Show all metrics toggle
    (function initMetricsToggle() {
      var toggleWrap = scopedFind(null, 'reMetricsToggle');
      var secondary = scopedFind(null, 'reCardsSecondary');
      if (!toggleWrap || !secondary) return;
      toggleWrap.innerHTML = createShowAllMetricsToggle(false);
      var btn = toggleWrap.querySelector('.metrics-toggle-link');
      if (!btn) return;
      btn.addEventListener('click', function() {
        var isExpanded = btn.getAttribute('aria-expanded') === 'true';
        if (isExpanded) {
          secondary.style.display = 'none';
          btn.setAttribute('aria-expanded', 'false');
          btn.textContent = 'Show all metrics';
        } else {
          secondary.style.display = '';
          btn.setAttribute('aria-expanded', 'true');
          btn.textContent = 'Show fewer';
        }
      });
    })();

    const hist = RE.history || {};
    const reColors = ['#db2777','#f59e0b','#8b5cf6','#06b6d4','#10b981'];
    const reAllDatasets = RE.properties.map(function(p, i) {
      const h = hist[p.ticker];
      if (!h) return null;
      return {
        label: p.name,
        allData: h.dates.map(function(d, j) { return {x: d, y: h.values[j]}; }),
        borderColor: reColors[i % reColors.length],
        backgroundColor: reColors[i % reColors.length] + '18',
        fill: false, tension: 0.3, pointRadius: 4, borderWidth: 2,
      };
    }).filter(Boolean);

    // TimeRangeSelector — default to ALL
    var reCurrentRange = 'ALL';
    var reChart = null;

    function reApplyTimeRange(range) {
      reCurrentRange = range;
      if (reChart) {
        reChart.data.datasets.forEach(function(ds) {
          ds.data = filterByTimeRange(ds.allData, range);
        });
        reChart.update();
      }
      // Update button states
      var wrap = scopedFind(null, 'reTimeRange');
      if (wrap) {
        wrap.innerHTML = createTimeRangeSelector(range);
        var btns = wrap.querySelectorAll('.time-range-btn');
        btns.forEach(function(btn) {
          btn.addEventListener('click', function() {
            reApplyTimeRange(btn.getAttribute('data-range'));
          });
        });
      }
    }

    // Render initial time range selector
    (function initTimeRangeSelector() {
      var wrap = scopedFind(null, 'reTimeRange');
      if (!wrap) return;
      wrap.innerHTML = createTimeRangeSelector(reCurrentRange);
      var btns = wrap.querySelectorAll('.time-range-btn');
      btns.forEach(function(btn) {
        btn.addEventListener('click', function() {
          reApplyTimeRange(btn.getAttribute('data-range'));
        });
      });
    })();

    if (reAllDatasets.length > 0 && typeof Chart !== 'undefined') {
      const ctx = scopedFind(null, 'reChart').getContext('2d');
      const chartDatasets = reAllDatasets.map(function(ds) {
        return {
          label: ds.label,
          data: filterByTimeRange(ds.allData, reCurrentRange),
          allData: ds.allData,
          borderColor: ds.borderColor,
          backgroundColor: ds.backgroundColor,
          fill: ds.fill, tension: ds.tension, pointRadius: ds.pointRadius, borderWidth: ds.borderWidth,
        };
      });
      reChart = new Chart(ctx, {
        type: 'line',
        data: { datasets: chartDatasets },
        options: {
          responsive: true, maintainAspectRatio: false,
          interaction: {mode: 'index', intersect: false},
          scales: {
            x: {type: 'time', time: {unit: 'month', tooltipFormat: 'yyyy-MM-dd'}, grid: {display: false}},
            y: {title: {display: true, text: _currency}, ticks: {callback: function(v) { return (v * _fx).toLocaleString(_locale); }}}
          },
          plugins: {tooltip: {callbacks: {label: function(c) { return c.dataset.label + ': ' + fmt(c.parsed.y * _fx) + ' ' + _currency; }}}}
        }
      });
    }

    const pt = scopedFind(null, 'reTable');
    pt.innerHTML = '<thead><tr><th>Ticker</th><th>Name</th><th>Type</th><th>Area m²</th>' +
      '<th>Purchase Date</th><th>Purchase EUR</th><th>ETN Value EUR</th>' +
      '<th>Gain EUR</th><th>Gain %</th><th>ETN Date</th></tr></thead><tbody>' +
      RE.properties.map(function(p) {
        return '<tr>' +
          '<td><strong>' + p.ticker + '</strong></td>' +
          '<td>' + p.name + (p.address ? '<br><span style="font-size:0.75rem;color:var(--muted)">' + p.address + '</span>' : '') + '</td>' +
          '<td>' + (propTypeLabels[p.property_type] || p.property_type) + '</td>' +
          '<td>' + fmt(p.area_m2, 0) + '</td>' +
          '<td>' + p.purchase_date + '</td>' +
          '<td>' + fmtEur(p.purchase_price_eur) + '</td>' +
          '<td>' + fmtEur(p.estimated_value_eur) + '</td>' +
          '<td class="' + cls(p.unrealized_gain_eur) + '">' + signCcy(p.unrealized_gain_eur) + '</td>' +
          '<td class="' + cls(p.unrealized_gain_pct) + '">' + sign(p.unrealized_gain_pct) + '%</td>' +
          '<td style="color:var(--muted);font-size:0.8rem">' + (p.estimated_date || '—') + '</td>' +
          '</tr>';
      }).join('') + '</tbody>';
    makeSortable(pt);

    // PropertyDetailsAccordion — wire header/panel toggle after table is rendered
    (function initPropertyDetailsAccordion() {
      var hdr = document.getElementById('property-details-header');
      var panel = document.getElementById('property-details-panel');
      if (!hdr || !panel) return;

      function toggle() {
        var isOpen = hdr.getAttribute('aria-expanded') === 'true';
        hdr.setAttribute('aria-expanded', isOpen ? 'false' : 'true');
        if (isOpen) {
          panel.classList.remove('is-open');
        } else {
          panel.classList.add('is-open');
        }
      }

      hdr.addEventListener('click', toggle);
      hdr.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          toggle();
        }
      });
    })();
  } else if (D.user && D.user.role && ['premium', 'admin', 'cofounder'].includes(D.user.role)) {
    // RealEstateEmptyState — no properties yet (premium/admin/cofounder only)
    scopedFind(null, 'realEstateSection').style.display = '';
    var emptyEl = scopedFind(null, 'reEmptyState');
    if (emptyEl) {
      var addPropertyUrl = (RE && RE.add_property_url) || '/properties/new';
      emptyEl.innerHTML = createRealEstateEmptyState(addPropertyUrl);
      emptyEl.style.display = '';
    }
  }
} catch(e) { console.error('Real estate section error:', e); }
}
updateRealEstate();
