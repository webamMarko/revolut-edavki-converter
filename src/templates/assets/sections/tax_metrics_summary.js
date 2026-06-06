// --- Tax Metrics Summary (Summary sub-tab) ---
(function() {
  const tby = D.tax_by_year || {};
  const years = Object.keys(tby).map(Number).sort((a, b) => a - b);
  const positions = D.positions || [];
  const section = scopedFind(null, 'taxSummaryMetrics');
  if (!section || !years.length) return;

  let currentYear = years[years.length - 1];
  const regime = D.regime || {};

  // Populate year selector
  const yearBar = scopedFind(null, 'taxSummaryYearBar');
  if (yearBar) {
    years.forEach(function(yr) {
      const btn = document.createElement('button');
      btn.className = 'range-btn' + (yr === currentYear ? ' active' : '');
      btn.textContent = yr;
      btn.addEventListener('click', function() {
        currentYear = yr;
        yearBar.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        renderSummaryMetrics();
      });
      yearBar.appendChild(btn);
    });
  }

  function _getBrackets(assetClass) {
    if (assetClass === 'cfd') return regime.cfd_brackets || [];
    if (assetClass === 'crypto') return regime.crypto_brackets || [];
    if (assetClass === 'savings') return regime.savings_brackets || [];
    return regime.stock_brackets || [{ min_years: 0, rate: 0 }];
  }

  function _getRate(brackets, holdingYears) {
    let rate = brackets[0] ? brackets[0].rate : 0;
    for (const b of brackets) {
      if (holdingYears >= b.min_years) rate = b.rate;
    }
    return rate;
  }

  function computeRealizedTax(sales) {
    let totalGain = 0;
    let totalTax = 0;
    const nettingMode = regime.netting || 'per_class';
    const buckets = {};
    for (const s of sales) {
      const brackets = _getBrackets(s.asset_class);
      const rate = regime.flat_rate != null ? regime.flat_rate : _getRate(brackets, s.holding_years);
      const gainAfterCosts = s.gain_eur > 0
        ? Math.max(0, s.gain_eur - (s.std_costs_eur || 0))
        : s.gain_eur;
      const acKey = nettingMode === 'all_classes' ? 'all' : s.asset_class;
      const key = acKey + '|' + rate;
      buckets[key] = (buckets[key] || 0) + gainAfterCosts;
      totalGain += s.gain_eur;
    }
    for (const [key, net] of Object.entries(buckets)) {
      const rate = parseFloat(key.split('|')[1]);
      totalTax += Math.max(0, net) * rate;
    }
    return { totalGain, totalTax };
  }

  function _setText(role, html, cssClass) {
    const el = scopedFind(null, role);
    if (!el) return;
    el.innerHTML = html;
    el.className = 'value ' + (cssClass || '');
  }

  function renderSummaryMetrics() {
    const ty = tby[currentYear];
    if (!ty) return;

    section.style.display = '';

    const sales = ty.realized_sales || [];
    const { totalGain, totalTax } = computeRealizedTax(sales);

    // Unrealized gains from positions
    const unrealizedGain = positions.reduce(function(s, p) {
      return s + (p.unrealized_gain_eur || 0);
    }, 0);

    // Tax-loss harvesting opportunities
    const harvestCandidates = ty.harvest_candidates || [];
    const harvestCount = harvestCandidates.length;
    const harvestSaving = harvestCandidates.reduce(function(s, c) {
      return s + (c.potential_tax_saving_eur || 0);
    }, 0);
    const harvestDisplay = harvestCount > 0
      ? fmtCcy(harvestSaving) + ' (' + harvestCount + (harvestCount === 1 ? ' opportunity' : ' opportunities') + ')'
      : '—';

    _setText('taxSummaryRealizedGainsValue', signCcy(totalGain), cls(totalGain));
    _setText('taxSummaryTaxLiabilityValue',  fmtCcy(totalTax),   'neg');
    _setText('taxSummaryUnrealizedGainsValue', signCcy(unrealizedGain), cls(unrealizedGain));
    _setText('taxSummaryHarvestValue', harvestDisplay, harvestCount > 0 ? 'pos' : '');
  }

  // Wire AdvancedToolsLink click to switch to Advanced tab
  const advLink = document.getElementById('taxAdvancedLink');
  if (advLink) {
    function goToAdvanced() {
      if (typeof window.switchTaxSubtab === 'function') {
        window.switchTaxSubtab('advanced');
      }
    }
    advLink.addEventListener('click', goToAdvanced);
    advLink.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        goToAdvanced();
      }
    });
  }

  // Expose so updateAll() can call it
  window.updateTaxSummaryMetrics = renderSummaryMetrics;
  renderSummaryMetrics();
})();
