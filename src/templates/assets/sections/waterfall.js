// --- Return Attribution Waterfall Chart ---
let _waterfallChart = null;

function initWaterfall() {
  const section = document.getElementById('returnWaterfallSection');
  if (!section) return;

  const items = (D.return_attribution || []);
  if (items.length === 0) { section.style.display = 'none'; return; }

  const significant = items.filter(i => Math.abs(i.total_gain_eur) > 0.5);
  if (significant.length === 0) { section.style.display = 'none'; return; }
  section.style.display = '';

  _buildWaterfallChart(significant);
}

function _buildWaterfallChart(items) {
  if (_waterfallChart) { _waterfallChart.destroy(); _waterfallChart = null; }
  const canvas = document.getElementById('waterfallChart');
  if (!canvas) return;

  // Limit to top N by absolute impact, collapse remainder into "Others"
  const MAX_BARS = 20;
  let displayed = items.slice(0, MAX_BARS);
  if (items.length > MAX_BARS) {
    let othersGain = 0, othersFx = 0, othersPrice = 0;
    for (let i = MAX_BARS; i < items.length; i++) {
      othersGain += items[i].total_gain_eur;
      if (items[i].fx_gain_eur != null) othersFx += items[i].fx_gain_eur;
      if (items[i].price_return_eur != null) othersPrice += items[i].price_return_eur;
    }
    if (Math.abs(othersGain) > 0.5) {
      displayed = displayed.concat([{
        ticker: 'Others',
        total_gain_eur: othersGain,
        unrealized_gain_eur: 0,
        realized_gain_eur: othersGain,
        contribution_pct: 0,
        weight_pct: 0,
        price_return_eur: othersFx !== 0 || othersPrice !== 0 ? othersPrice : null,
        fx_gain_eur: othersFx !== 0 ? othersFx : null,
        fx_masks_loss: false,
      }]);
    }
  }

  const hasFx = displayed.some(i => i.fx_gain_eur != null && i.price_return_eur != null);

  const labels = displayed.map(i => i.ticker);

  const datasets = [];
  if (hasFx) {
    // Price return dataset
    const priceData = displayed.map(i =>
      i.price_return_eur != null ? i.price_return_eur : i.total_gain_eur
    );
    datasets.push({
      label: 'Price Return',
      data: priceData,
      backgroundColor: priceData.map(v => v >= 0 ? 'rgba(52,211,153,0.75)' : 'rgba(248,113,113,0.75)'),
      borderColor: priceData.map(v => v >= 0 ? '#34d399' : '#f87171'),
      borderWidth: 1,
      borderRadius: 3,
      stack: 'attr',
    });
    // FX impact dataset
    const fxData = displayed.map(i => i.fx_gain_eur != null ? i.fx_gain_eur : 0);
    const fxBg = displayed.map(i => {
      if (i.fx_gain_eur == null) return 'transparent';
      if (i.fx_masks_loss) return 'rgba(251,191,36,0.75)';
      return i.fx_gain_eur >= 0 ? 'rgba(99,102,241,0.6)' : 'rgba(249,115,22,0.6)';
    });
    const fxBorder = displayed.map(i => {
      if (i.fx_gain_eur == null) return 'transparent';
      if (i.fx_masks_loss) return '#fbbf24';
      return i.fx_gain_eur >= 0 ? '#6366f1' : '#f97316';
    });
    datasets.push({
      label: 'FX Impact',
      data: fxData,
      backgroundColor: fxBg,
      borderColor: fxBorder,
      borderWidth: 1,
      borderRadius: 3,
      stack: 'attr',
    });
  } else {
    const gainData = displayed.map(i => i.total_gain_eur);
    datasets.push({
      label: 'Gain / Loss',
      data: gainData,
      backgroundColor: gainData.map(v => v >= 0 ? 'rgba(52,211,153,0.75)' : 'rgba(248,113,113,0.75)'),
      borderColor: gainData.map(v => v >= 0 ? '#34d399' : '#f87171'),
      borderWidth: 1,
      borderRadius: 3,
      stack: 'attr',
    });
  }

  _waterfallChart = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      scales: {
        x: {
          stacked: true,
          grid: { display: false },
          ticks: { color: '#556075', font: { size: 10 }, maxRotation: 45 },
        },
        y: {
          stacked: true,
          grid: { color: 'rgba(30,42,58,0.8)' },
          ticks: { color: '#556075', font: { size: 10 }, callback: v => fmtEur(v) },
        },
      },
      plugins: {
        legend: {
          display: hasFx,
          labels: { color: '#8899aa', font: { size: 11 }, boxWidth: 12 },
        },
        tooltip: {
          mode: 'index',
          intersect: false,
          callbacks: {
            title: ctx => ctx[0]?.label || '',
            afterTitle: ctx => {
              const idx = ctx[0]?.dataIndex;
              if (idx == null) return '';
              const item = displayed[idx];
              const lines = [];
              if (item.weight_pct > 0) lines.push('Weight: ' + fmt(item.weight_pct, 1) + '%');
              if (item.contribution_pct !== 0)
                lines.push('Contribution to return: ' + sign(item.contribution_pct) + '%');
              return lines.join('  ·  ');
            },
            label: ctx => {
              const v = ctx.parsed.y;
              if (v === 0 && ctx.dataset.label === 'FX Impact') return null;
              return ' ' + ctx.dataset.label + ': ' + signCcy(v);
            },
            afterBody: ctx => {
              const idx = ctx[0]?.dataIndex;
              if (idx == null) return [];
              const item = displayed[idx];
              const lines = [];
              if (item.unrealized_gain_eur !== 0)
                lines.push('  Unrealized P&L: ' + signCcy(item.unrealized_gain_eur));
              if (item.realized_gain_eur !== 0)
                lines.push('  Realized P&L: ' + signCcy(item.realized_gain_eur));
              if (item.fx_masks_loss)
                lines.push('  ⚠ FX masking underlying price loss');
              return lines;
            },
          },
        },
      },
    },
  });

  // Show/hide FX masking note
  const hasMasked = displayed.some(i => i.fx_masks_loss);
  const noteEl = document.getElementById('fxMaskingNote');
  if (noteEl) noteEl.style.display = hasMasked ? '' : 'none';
}

function updateWaterfall() {
  if (isZoomed) return;
  initWaterfall();
}
