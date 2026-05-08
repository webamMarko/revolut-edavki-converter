// --- Dividend Tax (Doh-Div) section ---
(function() {
  const dtby = D.dividend_tax || {};
  const years = Object.keys(dtby).map(Number).sort((a, b) => a - b);
  if (!years.length) return;

  let currentYear = years[years.length - 1];

  const section = document.getElementById('dividendTaxSection');
  if (!section) return;
  section.style.display = '';

  const bar = document.getElementById('divTaxYearBar');
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

  const exportBar = document.getElementById('divTaxExportBar');
  const exportBtn = document.getElementById('divTaxExportBtn');
  if (exportBtn) {
    exportBtn.addEventListener('click', function() {
      window.location.href = '/export/doh-div?year=' + currentYear;
    });
  }

  function fmt(n) {
    return n.toLocaleString(D.locale || 'en', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  }

  function renderDivTax() {
    const data = dtby[currentYear];
    if (!data) return;

    if (exportBar) exportBar.style.display = '';

    // Summary cards
    const cards = document.getElementById('divTaxCards');
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

    // Country breakdown table
    const table = document.getElementById('divTaxTable');
    if (table && data.by_country) {
      const countries = Object.entries(data.by_country).sort((a, b) => b[1].gross_eur - a[1].gross_eur);
      let html = `<thead><tr>
        <th>Country</th><th>Payments</th><th>Gross</th>
        <th>WHT Paid</th><th>Treaty Rate</th><th>Credit</th><th>Reclaimable</th>
      </tr></thead><tbody>`;
      for (const [code, c] of countries) {
        html += `<tr>
          <td>${c.country_name || code}</td>
          <td>${c.count}</td>
          <td>${fmt(c.gross_eur)} €</td>
          <td>${fmt(c.withholding_eur)} €</td>
          <td>${(c.treaty_rate * 100).toFixed(0)}%</td>
          <td>${fmt(c.credit_eur)} €</td>
          <td class="${c.reclaimable_eur > 0.01 ? 'pos' : ''}">${fmt(c.reclaimable_eur)} €</td>
        </tr>`;
      }
      html += '</tbody>';
      table.innerHTML = html;
    }

    // Reclaim guidance
    const guidance = document.getElementById('divTaxGuidance');
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
