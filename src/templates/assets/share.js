// --- Share Performance Snapshot ---
var _sharePeriod = 'ytd';
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape' && document.getElementById('shareModal').style.display !== 'none') closeShareModal();
});

function openShareModal() {
  document.getElementById('shareModal').style.display = 'flex';
  document.body.style.overflow = 'hidden';
  renderShareCard();
}

function closeShareModal() {
  document.getElementById('shareModal').style.display = 'none';
  document.body.style.overflow = '';
}

function setSharePeriod(period) {
  _sharePeriod = period;
  document.querySelectorAll('.share-period-btn').forEach(function(b) {
    b.classList.toggle('active', b.getAttribute('data-period') === period);
  });
  renderShareCard();
}

function _getShareMetrics() {
  var dates = ds.dates;
  if (!dates || dates.length < 2) return null;

  var endIdx = dates.length - 1;
  var startIdx = 0;
  var periodLabel = 'All-time';

  if (_sharePeriod === 'ytd') {
    var year = dates[endIdx].slice(0, 4);
    for (var i = 0; i < dates.length; i++) {
      if (dates[i].slice(0, 4) === year) { startIdx = i; break; }
    }
    periodLabel = 'YTD ' + year;
  } else if (_sharePeriod === '1y') {
    var cutoff = new Date(dates[endIdx]);
    cutoff.setFullYear(cutoff.getFullYear() - 1);
    var cutStr = cutoff.toISOString().slice(0, 10);
    for (var i = 0; i < dates.length; i++) {
      if (dates[i] >= cutStr) { startIdx = i; break; }
    }
    periodLabel = '1 Year';
  } else {
    periodLabel = dates[0].slice(0, 4) + ' – ' + dates[endIdx].slice(0, 4);
  }

  var m = computePeriodMetrics(startIdx, endIdx);
  var s = getActiveSummary();

  var benchmarkAlpha = null;
  if (D.benchmarks && D.benchmarks.length > 0) {
    var spx = D.benchmarks.find(function(b) { return b.name === 'S&P 500'; }) || D.benchmarks[0];
    if (_sharePeriod === 'all') {
      benchmarkAlpha = spx.alpha_pct;
    } else {
      var startDate = new Date(dates[startIdx]);
      var endDate = new Date(dates[endIdx]);
      var bKey = Object.keys(D.benchmark_series).find(function(k) { return D.benchmark_series[k].name === spx.name; });
      if (bKey) {
        var bs = D.benchmark_series[bKey];
        var bsi = 0, bei = bs.dates.length - 1;
        for (var i = 0; i < bs.dates.length; i++) { if (new Date(bs.dates[i]) >= startDate) { bsi = i; break; } }
        for (var i = bs.dates.length - 1; i >= 0; i--) { if (new Date(bs.dates[i]) <= endDate) { bei = i; break; } }
        var bStart = bs.values[bsi], bEnd = bs.values[bei];
        var benchRet = bStart > 0 ? (bEnd / bStart - 1) * 100 : 0;
        benchmarkAlpha = m.returnPct - benchRet;
      }
    }
  }

  var topPerformers = [];
  var positions = getActivePositions();
  if (positions && positions.length > 0) {
    topPerformers = positions.filter(function(p) { return p.cost_basis_eur > 0; })
      .sort(function(a, b) { return b.unrealized_gain_pct - a.unrealized_gain_pct; })
      .slice(0, 3);
  }

  var assetMix = [];
  if (hasFilter && classKeys.length > 1) {
    var total = 0;
    classKeys.forEach(function(k) {
      if (perClass[k] && perClass[k].summary) total += perClass[k].summary.portfolio_value_eur;
    });
    if (total > 0) {
      classKeys.forEach(function(k) {
        if (perClass[k] && perClass[k].summary && perClass[k].summary.portfolio_value_eur > 0) {
          assetMix.push({ label: classLabels[k] || k, pct: perClass[k].summary.portfolio_value_eur / total * 100 });
        }
      });
      assetMix.sort(function(a, b) { return b.pct - a.pct; });
    }
  }

  var sparkline = [];
  var step = Math.max(1, Math.floor((endIdx - startIdx) / 60));
  for (var i = startIdx; i <= endIdx; i += step) sparkline.push(ds.value_eur[i]);
  if (sparkline[sparkline.length - 1] !== ds.value_eur[endIdx]) sparkline.push(ds.value_eur[endIdx]);

  return {
    periodLabel: periodLabel,
    totalReturn: m.returnPct,
    cagr: m.cagr,
    startDate: dates[startIdx],
    endDate: dates[endIdx],
    benchmarkAlpha: benchmarkAlpha,
    benchmarkName: D.benchmarks && D.benchmarks.length > 0 ? (D.benchmarks.find(function(b) { return b.name === 'S&P 500'; }) || D.benchmarks[0]).name : null,
    topPerformers: topPerformers,
    assetMix: assetMix,
    sparkline: sparkline,
    maxDrawdown: m.maxDD
  };
}

function renderShareCard() {
  var canvas = document.getElementById('shareCanvas');
  var ctx = canvas.getContext('2d');
  var W = 1200, H = 630;
  canvas.width = W;
  canvas.height = H;

  var metrics = _getShareMetrics();
  if (!metrics) {
    ctx.fillStyle = '#111520';
    ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = '#dce4f0';
    ctx.font = '600 24px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Not enough data to generate snapshot', W / 2, H / 2);
    return;
  }

  var showBenchmark = document.getElementById('shareShowBenchmark').checked;
  var showTop = document.getElementById('shareShowTopPerformers').checked;
  var showMix = document.getElementById('shareShowAssetMix').checked;

  // Card background
  ctx.fillStyle = '#0f1218';
  ctx.fillRect(0, 0, W, H);

  // Subtle gradient overlay
  var grad = ctx.createLinearGradient(0, 0, W, H);
  grad.addColorStop(0, 'rgba(245,158,11,0.03)');
  grad.addColorStop(1, 'rgba(96,165,250,0.03)');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, W, H);

  // Border
  ctx.strokeStyle = '#1e2a3a';
  ctx.lineWidth = 2;
  ctx.strokeRect(1, 1, W - 2, H - 2);

  // --- Header ---
  ctx.fillStyle = '#f59e0b';
  ctx.font = '700 28px Inter, sans-serif';
  ctx.textAlign = 'left';
  ctx.fillText('Portfolio Performance', 48, 60);

  ctx.fillStyle = '#556075';
  ctx.font = '500 18px Inter, sans-serif';
  ctx.fillText(metrics.periodLabel + '  |  ' + metrics.startDate + ' → ' + metrics.endDate, 48, 92);

  // --- Main metrics ---
  var metricsY = 145;

  // Total Return
  ctx.fillStyle = '#8b95a8';
  ctx.font = '500 14px Inter, sans-serif';
  ctx.fillText('TOTAL RETURN', 48, metricsY);
  ctx.fillStyle = metrics.totalReturn >= 0 ? '#34d399' : '#f87171';
  ctx.font = '700 52px Inter, sans-serif';
  ctx.fillText((metrics.totalReturn >= 0 ? '+' : '') + metrics.totalReturn.toFixed(2) + '%', 48, metricsY + 56);

  // CAGR
  var cagrX = 380;
  if (metrics.cagr != null) {
    ctx.fillStyle = '#8b95a8';
    ctx.font = '500 14px Inter, sans-serif';
    ctx.fillText('CAGR', cagrX, metricsY);
    ctx.fillStyle = metrics.cagr >= 0 ? '#34d399' : '#f87171';
    ctx.font = '700 52px Inter, sans-serif';
    ctx.fillText((metrics.cagr >= 0 ? '+' : '') + metrics.cagr.toFixed(2) + '%', cagrX, metricsY + 56);
  }

  // Max Drawdown
  var ddX = 650;
  ctx.fillStyle = '#8b95a8';
  ctx.font = '500 14px Inter, sans-serif';
  ctx.fillText('MAX DRAWDOWN', ddX, metricsY);
  ctx.fillStyle = '#f87171';
  ctx.font = '700 36px Inter, sans-serif';
  ctx.fillText(metrics.maxDrawdown.toFixed(2) + '%', ddX, metricsY + 44);

  // Benchmark alpha
  if (showBenchmark && metrics.benchmarkAlpha != null) {
    var alphaX = 650;
    var alphaY = metricsY + 80;
    ctx.fillStyle = '#8b95a8';
    ctx.font = '500 14px Inter, sans-serif';
    ctx.fillText('ALPHA VS ' + (metrics.benchmarkName || 'BENCHMARK').toUpperCase(), alphaX, alphaY);
    ctx.fillStyle = metrics.benchmarkAlpha >= 0 ? '#34d399' : '#f87171';
    ctx.font = '700 36px Inter, sans-serif';
    ctx.fillText((metrics.benchmarkAlpha >= 0 ? '+' : '') + metrics.benchmarkAlpha.toFixed(2) + '%', alphaX, alphaY + 38);
  }

  // --- Sparkline ---
  var sparkY = 300, sparkH = 120, sparkX = 48, sparkW = 560;
  if (metrics.sparkline.length > 2) {
    var minV = Math.min.apply(null, metrics.sparkline);
    var maxV = Math.max.apply(null, metrics.sparkline);
    var range = maxV - minV || 1;

    ctx.beginPath();
    for (var i = 0; i < metrics.sparkline.length; i++) {
      var x = sparkX + (i / (metrics.sparkline.length - 1)) * sparkW;
      var y = sparkY + sparkH - ((metrics.sparkline[i] - minV) / range) * sparkH;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    var lineGrad = ctx.createLinearGradient(sparkX, 0, sparkX + sparkW, 0);
    var positive = metrics.sparkline[metrics.sparkline.length - 1] >= metrics.sparkline[0];
    lineGrad.addColorStop(0, positive ? 'rgba(52,211,153,0.6)' : 'rgba(248,113,113,0.6)');
    lineGrad.addColorStop(1, positive ? '#34d399' : '#f87171');
    ctx.strokeStyle = lineGrad;
    ctx.lineWidth = 2.5;
    ctx.stroke();

    // Fill area
    ctx.lineTo(sparkX + sparkW, sparkY + sparkH);
    ctx.lineTo(sparkX, sparkY + sparkH);
    ctx.closePath();
    var areaGrad = ctx.createLinearGradient(0, sparkY, 0, sparkY + sparkH);
    areaGrad.addColorStop(0, positive ? 'rgba(52,211,153,0.12)' : 'rgba(248,113,113,0.12)');
    areaGrad.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = areaGrad;
    ctx.fill();
  }

  // --- Right panel: Top performers or Asset mix ---
  var panelX = 700, panelY = 300;

  if (showTop && metrics.topPerformers.length > 0) {
    ctx.fillStyle = '#8b95a8';
    ctx.font = '600 13px Inter, sans-serif';
    ctx.fillText('TOP PERFORMERS', panelX, panelY);

    metrics.topPerformers.forEach(function(p, i) {
      var y = panelY + 30 + i * 38;
      ctx.fillStyle = '#dce4f0';
      ctx.font = '600 16px Inter, sans-serif';
      ctx.fillText(p.ticker, panelX, y);
      ctx.fillStyle = p.unrealized_gain_pct >= 0 ? '#34d399' : '#f87171';
      ctx.font = '700 16px Inter, sans-serif';
      ctx.textAlign = 'right';
      ctx.fillText((p.unrealized_gain_pct >= 0 ? '+' : '') + p.unrealized_gain_pct.toFixed(1) + '%', W - 48, y);
      ctx.textAlign = 'left';
    });
    panelY += 30 + metrics.topPerformers.length * 38 + 20;
  }

  if (showMix && metrics.assetMix.length > 0) {
    var mixY = showTop ? panelY : panelY;
    ctx.fillStyle = '#8b95a8';
    ctx.font = '600 13px Inter, sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText('ASSET MIX', panelX, mixY);

    var barY = mixY + 20;
    var barW = W - panelX - 48;
    var barH = 14;
    var colorMap = { stock: '#60a5fa', cfd: '#f59e0b', crypto: '#a78bfa', savings: '#34d399', realestate: '#fb7185' };
    var xOff = 0;
    metrics.assetMix.forEach(function(a) {
      var segW = (a.pct / 100) * barW;
      var key = Object.keys(classLabels).find(function(k) { return classLabels[k] === a.label; }) || '';
      ctx.fillStyle = colorMap[key] || '#556075';
      _roundRect(ctx, panelX + xOff, barY, segW - 1, barH, 3);
      ctx.fill();
      xOff += segW;
    });

    // Legend
    var legY = barY + barH + 16;
    metrics.assetMix.forEach(function(a, i) {
      var lx = panelX + (i % 2) * 200;
      var ly = legY + Math.floor(i / 2) * 22;
      var key = Object.keys(classLabels).find(function(k) { return classLabels[k] === a.label; }) || '';
      ctx.fillStyle = colorMap[key] || '#556075';
      ctx.fillRect(lx, ly - 8, 10, 10);
      ctx.fillStyle = '#dce4f0';
      ctx.font = '500 13px Inter, sans-serif';
      ctx.fillText(a.label + ' ' + a.pct.toFixed(0) + '%', lx + 16, ly);
    });
  }

  // --- Footer branding ---
  var footerY = H - 40;
  ctx.fillStyle = '#1e2a3a';
  ctx.fillRect(0, footerY - 20, W, 60);

  ctx.fillStyle = '#f59e0b';
  ctx.font = '700 16px Inter, sans-serif';
  ctx.textAlign = 'left';
  ctx.fillText('WealthEagle', 48, footerY + 8);

  ctx.fillStyle = '#556075';
  ctx.font = '400 13px Inter, sans-serif';
  ctx.fillText('Tracked with WealthEagle — wealthea.gl', 180, footerY + 8);

  ctx.textAlign = 'right';
  ctx.fillStyle = '#556075';
  ctx.font = '400 12px Inter, sans-serif';
  ctx.fillText('Generated ' + new Date().toISOString().slice(0, 10), W - 48, footerY + 8);
  ctx.textAlign = 'left';
}

function _roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function downloadSharePNG() {
  var canvas = document.getElementById('shareCanvas');
  var link = document.createElement('a');
  link.download = 'portfolio-snapshot-' + new Date().toISOString().slice(0, 10) + '.png';
  link.href = canvas.toDataURL('image/png');
  link.click();
}

function copyShareToClipboard() {
  var canvas = document.getElementById('shareCanvas');
  if (!canvas.toBlob) {
    alert('Clipboard copy not supported in this browser.');
    return;
  }
  canvas.toBlob(function(blob) {
    if (!navigator.clipboard || !navigator.clipboard.write) {
      alert('Clipboard API not available. Use Download instead.');
      return;
    }
    navigator.clipboard.write([
      new ClipboardItem({ 'image/png': blob })
    ]).then(function() {
      _shareNotify('Copied to clipboard!');
    }).catch(function() {
      alert('Failed to copy. Try the Download button instead.');
    });
  }, 'image/png');
}

function _shareNotify(msg) {
  var toast = document.createElement('div');
  toast.className = 'notify-toast';
  toast.innerHTML = '<div class="notify-toast-content">'
    + '<span class="notify-toast-icon">&#x2705;</span>'
    + '<span class="notify-toast-text">' + msg + '</span>'
    + '</div>';
  document.body.appendChild(toast);
  requestAnimationFrame(function() { toast.classList.add('notify-toast-visible'); });
  setTimeout(function() {
    toast.classList.add('notify-toast-exit');
    setTimeout(function() { toast.remove(); }, 300);
  }, 2500);
}
