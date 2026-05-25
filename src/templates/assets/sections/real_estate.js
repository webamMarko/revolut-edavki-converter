// --- Real Estate section ---
try {
  const RE = D.real_estate;
  if (RE && RE.properties && RE.properties.length > 0) {
    scopedFind(null, 'realEstateSection').style.display = '';

    const propTypeLabels = {
      stanovanje: 'Apartment', hisa: 'House', garaza: 'Garage',
      poslovni: 'Commercial', zemljisce: 'Land'
    };

    const reCards = [
      ['Properties', RE.properties.length, ''],
      ['Purchase Total', fmtEur(RE.total_purchase_eur), ''],
      ['ETN Estimate', fmtEur(RE.total_estimated_eur), ''],
      ['Unrealized Gain', signCcy(RE.total_gain_eur), cls(RE.total_gain_eur),
       sign(RE.total_gain_pct) + '%'],
    ];
    scopedFind(null, 'reCards').innerHTML = reCards.map(([l, v, c, sub]) =>
      '<div class="metric-card"><div class="label">' + l + '</div><div class="value ' + (c||'') + '">' + v + '</div>' +
      (sub ? '<div class="sub ' + (c||'') + '">' + sub + '</div>' : '') + '</div>'
    ).join('');

    const hist = RE.history || {};
    const reColors = ['#db2777','#f59e0b','#8b5cf6','#06b6d4','#10b981'];
    const reDatasets = RE.properties.map(function(p, i) {
      const h = hist[p.ticker];
      if (!h) return null;
      return {
        label: p.name,
        data: h.dates.map(function(d, j) { return {x: d, y: h.values[j]}; }),
        borderColor: reColors[i % reColors.length],
        backgroundColor: reColors[i % reColors.length] + '18',
        fill: false, tension: 0.3, pointRadius: 4, borderWidth: 2,
      };
    }).filter(Boolean);

    if (reDatasets.length > 0 && typeof Chart !== 'undefined') {
      const ctx = scopedFind(null, 'reChart').getContext('2d');
      new Chart(ctx, {
        type: 'line',
        data: { datasets: reDatasets },
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
  }
} catch(e) { console.error('Real estate section error:', e); }
