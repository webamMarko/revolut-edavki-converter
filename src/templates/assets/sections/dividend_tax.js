// --- Dividend Tax (Doh-Div) section ---
(function() {
  const dtby = D.dividend_tax || {};
  const years = Object.keys(dtby).map(Number).sort((a, b) => a - b);
  if (!years.length) return;

  let currentYear = years[years.length - 1];

  const section = scopedFind(null, 'dividendTaxSection');
  if (!section) return;
  section.style.display = '';

  const bar = scopedFind(null, 'divTaxYearBar');
  if (bar) {
    years.forEach(function(yr) {
      const btn = document.createElement('button');
      btn.className = 'range-btn' + (yr === currentYear ? ' active' : '');
      btn.textContent = yr;
      btn.addEventListener('click', function() {
        currentYear = yr;
        bar.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        renderDivTax();
      });
      bar.appendChild(btn);
    });
  }

  const exportBar = scopedFind(null, 'divTaxExportBar');
  const exportBtn = scopedFind(null, 'divTaxExportBtn');
  if (exportBtn) {
    exportBtn.addEventListener('click', function() {
      window.location.href = '/export/doh-div?year=' + currentYear;
    });
  }

  function fmt(n) {
    return n.toLocaleString(D.locale || 'en', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  }

  let currentCountries = [];

  const paginationEl = scopedFind(null, 'divTaxPagination');
  const countryPaginator = paginationEl
    ? createPaginator(paginationEl, { onChange: renderCountryTable })
    : null;

  function _renderCountryDetail(c) {
    const payments = c.payments;
    if (!Array.isArray(payments) || !payments.length) {
      return `<p style="margin:0;font-size:0.85rem;color:var(--muted)">
        Payment-level detail isn't available for this country — the totals above summarize ${c.count} dividend payment${c.count === 1 ? '' : 's'}.
      </p>`;
    }
    let html = `<table class="data-table dt-payments-table">
      <thead><tr>
        <th>Date</th><th>Ticker</th><th>Gross</th><th>WHT Paid</th><th>Net</th><th>Credit</th><th>Reclaimable</th>
      </tr></thead><tbody>`;
    for (const p of payments) {
      html += `<tr>
        <td>${p.date || '—'}</td>
        <td>${p.ticker || '—'}</td>
        <td>${p.gross_eur != null ? fmt(p.gross_eur) + ' €' : '—'}</td>
        <td>${p.withholding_eur != null ? fmt(p.withholding_eur) + ' €' : '—'}</td>
        <td>${p.net_eur != null ? fmt(p.net_eur) + ' €' : '—'}</td>
        <td>${p.credit_eur != null ? fmt(p.credit_eur) + ' €' : '—'}</td>
        <td class="${(p.reclaimable_eur || 0) > 0.01 ? 'pos' : ''}">${p.reclaimable_eur != null ? fmt(p.reclaimable_eur) + ' €' : '—'}</td>
      </tr>`;
    }
    html += '</tbody></table>';
    return html;
  }

  function renderCountryTable() {
    const table = scopedFind(null, 'divTaxTable');
    if (!table) return;

    const pageItems = countryPaginator ? countryPaginator.getPage() : currentCountries;

    let html = `<thead><tr>
      <th>Country</th><th>Payments</th><th>Gross</th>
      <th>WHT Paid</th><th>Treaty Rate</th><th>Credit</th><th>Reclaimable</th>
    </tr></thead><tbody>`;
    for (const [code, c] of pageItems) {
      const detailId = 'dt-detail-' + code;
      html += `<tr class="dt-country-row">
        <td>
          <div class="pos-ticker-cell">
            <button type="button" class="dt-toggle" aria-expanded="false" aria-controls="${detailId}">
              <span class="pos-chevron">&#x25B6;</span>
            </button>
            <span>${c.country_name || code}</span>
          </div>
        </td>
        <td>${c.count}</td>
        <td>${fmt(c.gross_eur)} €</td>
        <td>${fmt(c.withholding_eur)} €</td>
        <td>${(c.treaty_rate * 100).toFixed(0)}%</td>
        <td>${fmt(c.credit_eur)} €</td>
        <td class="${c.reclaimable_eur > 0.01 ? 'pos' : ''}">${fmt(c.reclaimable_eur)} €</td>
      </tr>
      <tr class="pos-detail-row dt-detail-row" id="${detailId}" style="display:none">
        <td colspan="7">
          <div class="pos-detail">${_renderCountryDetail(c)}</div>
        </td>
      </tr>`;
    }
    html += '</tbody>';
    table.innerHTML = html;

    table.querySelectorAll('.dt-toggle').forEach(function(btn) {
      btn.addEventListener('click', function() {
        const row = btn.closest('tr');
        const detailRow = row.nextElementSibling;
        const chevron = btn.querySelector('.pos-chevron');
        const isOpen = btn.getAttribute('aria-expanded') === 'true';
        if (isOpen) {
          btn.setAttribute('aria-expanded', 'false');
          detailRow.style.display = 'none';
          chevron.classList.remove('pos-chevron-open');
        } else {
          btn.setAttribute('aria-expanded', 'true');
          detailRow.style.display = '';
          chevron.classList.add('pos-chevron-open');
        }
      });
    });
  }

  function renderDivTax() {
    const data = dtby[currentYear];
    if (!data) return;

    if (exportBar) exportBar.style.display = '';

    // Summary cards
    const cards = scopedFind(null, 'divTaxCards');
    if (cards) {
      cards.innerHTML = `
        <div class="metric-card">
          <div class="metric-label">Gross Dividends</div>
          <div class="metric-value">${fmt(data.total_gross_eur)} €</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Foreign WHT Paid</div>
          <div class="metric-value neg">${fmt(data.total_withholding_eur)} €</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Net Received</div>
          <div class="metric-value">${fmt(data.total_net_received_eur)} €</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">SI Tax (25%)</div>
          <div class="metric-value neg">${fmt(data.si_tax_liability)} €</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Treaty Credit</div>
          <div class="metric-value pos">-${fmt(data.total_credit_eur)} €</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Net Tax Owed</div>
          <div class="metric-value ${data.net_tax_owed_si > 0 ? 'neg' : ''}">${fmt(data.net_tax_owed_si)} €</div>
        </div>
      `;
    }

    // Country breakdown table (paginated, expandable rows)
    currentCountries = Object.entries(data.by_country || {}).sort((a, b) => b[1].gross_eur - a[1].gross_eur);
    if (countryPaginator) {
      countryPaginator.setData(currentCountries);
      countryPaginator.reset();
    }
    renderCountryTable();
    if (countryPaginator) countryPaginator.render();

    // Reclaim guidance
    const guidance = scopedFind(null, 'divTaxGuidance');
    if (guidance && data.by_country) {
      const reclaimable = Object.entries(data.by_country)
        .filter(([, c]) => c.reclaimable_eur > 0.01);
      if (reclaimable.length > 0) {
        let html = '<h4 style="margin:0 0 0.5rem">Withholding Tax Reclaim Guidance</h4><ul style="margin:0;padding-left:1.2rem;font-size:0.85rem">';
        for (const [code, c] of reclaimable) {
          html += `<li><strong>${c.country_name}</strong>: Reclaim <strong>${fmt(c.reclaimable_eur)} €</strong> — withholding exceeded ${(c.treaty_rate * 100).toFixed(0)}% treaty rate</li>`;
        }
        html += '</ul>';
        guidance.innerHTML = html;
      } else {
        guidance.innerHTML = '<p style="font-size:0.85rem;color:var(--muted)">All withholding is within treaty limits — no reclaim needed.</p>';
      }
    }
  }

  renderDivTax();
})();
