// --- What-If Benchmark Comparison ---
let whatifChart = null;

(function() {
  const section = document.getElementById('whatifSection');
  const select = document.getElementById('whatifBenchmark');
  const resultEl = document.getElementById('whatifResult');
  const emptyEl = document.getElementById('whatifEmpty');
  if (!section || !select || !D.benchmark_series) return;

  const benchKeys = Object.keys(D.benchmark_series);
  if (benchKeys.length === 0) return;

  section.style.display = '';

  benchKeys.forEach(tk => {
    const b = D.benchmark_series[tk];
    const opt = document.createElement('option');
    opt.value = tk;
    opt.textContent = b.name;
    select.appendChild(opt);
  });

  select.addEventListener('change', function() {
    if (!select.value) {
      resultEl.style.display = 'none';
      emptyEl.style.display = '';
      return;
    }
    runWhatIf(select.value);
  });
})();

function extractCashFlows() {
  const invested = ds.invested_eur;
  const dates = allDates;
  const flows = [];
  for (let i = 0; i < dates.length; i++) {
    const prev = i === 0 ? 0 : invested[i - 1];
    const diff = invested[i] - prev;
    if (Math.abs(diff) > 0.01) {
      flows.push({ date: dates[i], amount: diff });
    }
  }
  return flows;
}

function runWhatIf(benchKey) {
  const bench = D.benchmark_series[benchKey];
  if (!bench || bench.dates.length < 2) return;

  const resultEl = document.getElementById('whatifResult');
  const emptyEl = document.getElementById('whatifEmpty');
  resultEl.style.display = '';
  emptyEl.style.display = 'none';

  const cashFlows = extractCashFlows();
  if (cashFlows.length === 0) return;

  const bDates = bench.dates;
  const bValues = bench.values;

  function getBenchValue(dateStr) {
    let lo = 0, hi = bDates.length - 1, idx = 0;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (bDates[mid] <= dateStr) { idx = mid; lo = mid + 1; }
      else { hi = mid - 1; }
    }
    return bValues[idx];
  }

  // Replay cash flows: each deposit buys units of the benchmark at that day's price
  let totalUnits = 0;
  let totalInvested = 0;
  const hypotheticalDaily = [];

  // Build hypothetical equity curve on the same date axis as portfolio
  let flowIdx = 0;
  const sortedFlows = cashFlows.slice().sort((a, b) => a.date.localeCompare(b.date));

  for (let i = 0; i < allDates.length; i++) {
    const d = allDates[i];

    // Process any cash flows up to and including this date
    while (flowIdx < sortedFlows.length && sortedFlows[flowIdx].date <= d) {
      const flow = sortedFlows[flowIdx];
      const price = getBenchValue(flow.date);
      if (price > 0) {
        if (flow.amount > 0) {
          // Deposit: buy units
          totalUnits += flow.amount / price;
          totalInvested += flow.amount;
        } else {
          // Withdrawal: sell proportional units
          const withdrawPct = Math.min(1, Math.abs(flow.amount) / (totalUnits * price));
          totalUnits *= (1 - withdrawPct);
          totalInvested += flow.amount; // negative
        }
      }
      flowIdx++;
    }

    const currentPrice = getBenchValue(d);
    hypotheticalDaily.push(totalUnits * currentPrice);
  }

  // Compute summary
  const actualFinal = ds.value_eur[ds.value_eur.length - 1] || 0;
  const hypoFinal = hypotheticalDaily[hypotheticalDaily.length - 1] || 0;
  const diffAbs = actualFinal - hypoFinal;
  const diffPct = hypoFinal > 0 ? (diffAbs / hypoFinal * 100) : 0;
  const beat = diffAbs >= 0;

  renderWhatIfSummary(bench.name, actualFinal, hypoFinal, diffAbs, diffPct, beat, totalInvested);
  renderWhatIfChart(bench.name, hypotheticalDaily);
  renderWhatIfYearBreakdown(bench.name, hypotheticalDaily);
}

function renderWhatIfSummary(benchName, actual, hypo, diffAbs, diffPct, beat, invested) {
  const card = document.getElementById('whatifSummaryCard');
  const icon = beat ? '&#9650;' : '&#9660;';
  const colorClass = beat ? 'pos' : 'neg';
  const verb = beat ? 'beat' : 'trailed';

  const actualReturn = invested > 0 ? ((actual - invested) / invested * 100) : 0;
  const hypoReturn = invested > 0 ? ((hypo - invested) / invested * 100) : 0;

  card.innerHTML = '<div class="whatif-summary-grid">' +
    '<div class="whatif-metric">' +
      '<div class="whatif-metric-label">Your Portfolio</div>' +
      '<div class="whatif-metric-value">' + fmtCcy(actual) + '</div>' +
      '<div class="whatif-metric-sub ' + cls(actualReturn) + '">' + sign(actualReturn) + '%</div>' +
    '</div>' +
    '<div class="whatif-metric">' +
      '<div class="whatif-metric-label">If ' + benchName + '</div>' +
      '<div class="whatif-metric-value">' + fmtCcy(hypo) + '</div>' +
      '<div class="whatif-metric-sub ' + cls(hypoReturn) + '">' + sign(hypoReturn) + '%</div>' +
    '</div>' +
    '<div class="whatif-metric whatif-verdict">' +
      '<div class="whatif-metric-label">Difference</div>' +
      '<div class="whatif-metric-value ' + colorClass + '">' +
        '<span class="whatif-icon">' + icon + '</span> ' + signCcy(diffAbs) +
      '</div>' +
      '<div class="whatif-metric-sub ' + colorClass + '">You ' + verb + ' ' + benchName + ' by ' + fmt(Math.abs(diffPct)) + '%</div>' +
    '</div>' +
  '</div>';
}

function renderWhatIfChart(benchName, hypotheticalDaily) {
  const ctx = document.getElementById('whatifChart').getContext('2d');
  if (whatifChart) whatifChart.destroy();

  const labels = allDates.slice(selStart, selEnd + 1);
  const actualData = ds.value_eur.slice(selStart, selEnd + 1);
  const hypoData = hypotheticalDaily.slice(selStart, selEnd + 1);

  whatifChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Your Portfolio',
          data: actualData,
          borderColor: '#4285f4',
          backgroundColor: 'rgba(66,133,244,0.06)',
          fill: true,
          tension: 0.15,
          pointRadius: 0,
          borderWidth: 2
        },
        {
          label: 'If ' + benchName,
          data: hypoData,
          borderColor: '#f59e0b',
          backgroundColor: 'rgba(245,158,11,0.06)',
          fill: true,
          tension: 0.15,
          pointRadius: 0,
          borderWidth: 2,
          borderDash: [5, 3]
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: { type: 'time', time: { unit: 'month', tooltipFormat: 'yyyy-MM-dd' }, grid: { display: false } },
        y: { title: { display: true, text: _currency }, ticks: { callback: v => (v * _fx).toLocaleString(_locale) } }
      },
      plugins: {
        tooltip: {
          callbacks: {
            label: c => c.parsed.y != null ? c.dataset.label + ': ' + fmt(c.parsed.y * _fx) + ' ' + _currency : ''
          }
        },
        legend: { display: true, position: 'top' }
      }
    }
  });
}

function renderWhatIfYearBreakdown(benchName, hypotheticalDaily) {
  const section = document.getElementById('whatifYearBreakdown');
  const table = document.getElementById('whatifYearTable');
  if (!section || !table) return;

  // Group by year
  const years = {};
  for (let i = 0; i < allDates.length; i++) {
    const y = allDates[i].slice(0, 4);
    if (!years[y]) years[y] = { firstIdx: i, lastIdx: i };
    else years[y].lastIdx = i;
  }

  const yearKeys = Object.keys(years).sort();
  if (yearKeys.length < 2) { section.style.display = 'none'; return; }

  section.style.display = '';
  let html = '<thead><tr><th>Year</th><th>Your Portfolio</th><th>If ' + benchName + '</th><th>Difference</th></tr></thead><tbody>';

  yearKeys.forEach(y => {
    const { firstIdx, lastIdx } = years[y];
    const actualStart = ds.value_eur[firstIdx] || 0;
    const actualEnd = ds.value_eur[lastIdx] || 0;
    const hypoStart = hypotheticalDaily[firstIdx] || 0;
    const hypoEnd = hypotheticalDaily[lastIdx] || 0;

    // TWR-ish: just show EOY values and year-over-year change
    const actualPct = actualStart > 0 ? ((actualEnd - actualStart) / actualStart * 100) : 0;
    const hypoPct = hypoStart > 0 ? ((hypoEnd - hypoStart) / hypoStart * 100) : 0;
    const diff = actualPct - hypoPct;

    html += '<tr>' +
      '<td>' + y + '</td>' +
      '<td class="' + cls(actualPct) + '">' + sign(actualPct) + '%</td>' +
      '<td class="' + cls(hypoPct) + '">' + sign(hypoPct) + '%</td>' +
      '<td class="' + cls(diff) + '">' + sign(diff) + '%</td>' +
    '</tr>';
  });

  html += '</tbody>';
  table.innerHTML = html;
}

function updateWhatIf() {
  const select = document.getElementById('whatifBenchmark');
  if (select && select.value) runWhatIf(select.value);
}
