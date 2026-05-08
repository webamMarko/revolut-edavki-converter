// --- Metric tooltip definitions and rendering ---
const METRIC_TOOLTIPS = {
  'summary.portfolio_value': {
    definition: 'Current total market value of all your open positions.',
    ranges: null,
    personalize: function(v) { return null; }
  },
  'summary.total_invested': {
    definition: 'Total cash you have put into the portfolio (buys minus sells).',
    ranges: null,
    personalize: function(v) { return null; }
  },
  'summary.absolute_gain': {
    definition: 'Difference between current market value and total invested. Includes unrealized gains.',
    ranges: [
      { min: 0, label: 'Profitable', color: 'green' }
    ],
    personalize: function(v) {
      if (v == null) return null;
      return v >= 0 ? 'Your portfolio is in profit.' : 'Your portfolio is currently at a loss.';
    }
  },
  'summary.total_return': {
    definition: 'Percentage gain or loss relative to total invested capital.',
    ranges: [
      { min: 50, label: 'Excellent', color: 'green' },
      { min: 10, label: 'Good', color: 'green' },
      { min: 0, label: 'Positive', color: 'yellow' },
      { min: -Infinity, label: 'Negative', color: 'red' }
    ],
    personalize: function(v) {
      if (v == null) return null;
      if (v > 20) return 'Your ' + fmt(v) + '% return is strong.';
      if (v > 0) return 'Your portfolio is up ' + fmt(v) + '%.';
      return 'Your portfolio is down ' + fmt(Math.abs(v)) + '%.';
    }
  },
  'summary.cagr': {
    definition: 'Compound Annual Growth Rate — your average yearly return accounting for compounding.',
    ranges: [
      { min: 15, label: 'Excellent', color: 'green' },
      { min: 7, label: 'Good', color: 'green' },
      { min: 0, label: 'Low', color: 'yellow' },
      { min: -Infinity, label: 'Negative', color: 'red' }
    ],
    personalize: function(v) {
      if (v == null) return null;
      if (v > 10) return 'Your CAGR of ' + fmt(v) + '% beats the long-term market average (~7-10%).';
      if (v > 0) return 'Your CAGR of ' + fmt(v) + '% is positive but below historical market averages.';
      return 'A negative CAGR means your portfolio is shrinking on average each year.';
    }
  },
  'summary.twr': {
    definition: 'Time-Weighted Return — measures investment performance independent of cash flow timing.',
    ranges: [
      { min: 15, label: 'Excellent', color: 'green' },
      { min: 7, label: 'Good', color: 'green' },
      { min: 0, label: 'Low', color: 'yellow' },
      { min: -Infinity, label: 'Negative', color: 'red' }
    ],
    personalize: function(v) {
      if (v == null) return null;
      return 'Your TWR of ' + fmt(v) + '% reflects pure investment skill, ignoring deposit/withdrawal timing.';
    }
  },
  'summary.max_drawdown': {
    definition: 'Largest peak-to-trough decline in portfolio value. Shows worst-case loss you experienced.',
    ranges: [
      { min: -10, label: 'Low risk', color: 'green' },
      { min: -25, label: 'Moderate', color: 'yellow' },
      { min: -Infinity, label: 'High', color: 'red' }
    ],
    personalize: function(v) {
      if (v == null) return null;
      if (v > -10) return 'A drawdown of ' + fmt(Math.abs(v)) + '% is very manageable.';
      if (v > -25) return 'Your max drawdown of ' + fmt(Math.abs(v)) + '% is moderate — typical for a diversified portfolio.';
      return 'A ' + fmt(Math.abs(v)) + '% drawdown is significant. Consider whether your risk tolerance matches.';
    }
  },
  'risk.volatility': {
    definition: 'Annualized standard deviation of daily returns. Higher means more price swings.',
    ranges: [
      { min: 25, label: 'High', color: 'red' },
      { min: 15, label: 'Moderate', color: 'yellow' },
      { min: 0, label: 'Low', color: 'green' }
    ],
    personalize: function(v) {
      if (v == null) return null;
      if (v < 15) return 'Your volatility of ' + fmt(v) + '% is relatively calm.';
      if (v < 25) return 'Volatility of ' + fmt(v) + '% is typical for a stock portfolio.';
      return 'At ' + fmt(v) + '% volatility, expect large daily swings.';
    }
  },
  'risk.sharpe': {
    definition: 'Risk-adjusted return: excess return per unit of risk. Higher is better.',
    ranges: [
      { min: 1.5, label: 'Excellent', color: 'green' },
      { min: 1.0, label: 'Good', color: 'green' },
      { min: 0.5, label: 'Adequate', color: 'yellow' },
      { min: -Infinity, label: 'Poor', color: 'red' }
    ],
    personalize: function(v) {
      if (v == null) return null;
      if (v >= 1.5) return 'A Sharpe of ' + fmt(v) + ' is excellent — strong returns for the risk taken.';
      if (v >= 1.0) return 'A Sharpe of ' + fmt(v) + ' indicates good risk-adjusted performance.';
      if (v >= 0.5) return 'A Sharpe of ' + fmt(v) + ' is acceptable but there’s room to improve.';
      return 'A Sharpe below 0.5 suggests the risk isn’t being well compensated.';
    }
  },
  'risk.sortino': {
    definition: 'Like Sharpe but only penalizes downside volatility. Better for asymmetric returns.',
    ranges: [
      { min: 2.0, label: 'Excellent', color: 'green' },
      { min: 1.0, label: 'Good', color: 'green' },
      { min: 0.5, label: 'Adequate', color: 'yellow' },
      { min: -Infinity, label: 'Poor', color: 'red' }
    ],
    personalize: function(v) {
      if (v == null) return null;
      if (v >= 2.0) return 'A Sortino of ' + fmt(v) + ' means great returns with limited downside.';
      if (v >= 1.0) return 'Your Sortino of ' + fmt(v) + ' shows decent downside risk management.';
      return 'A Sortino of ' + fmt(v) + ' indicates significant downside exposure.';
    }
  },
  'risk.calmar': {
    definition: 'Annual return divided by maximum drawdown. Measures return per unit of crash risk.',
    ranges: [
      { min: 3.0, label: 'Excellent', color: 'green' },
      { min: 1.0, label: 'Good', color: 'green' },
      { min: 0.5, label: 'Fair', color: 'yellow' },
      { min: -Infinity, label: 'Poor', color: 'red' }
    ],
    personalize: function(v) {
      if (v == null) return null;
      if (v >= 3.0) return 'A Calmar of ' + fmt(v) + ' is outstanding — high return relative to worst loss.';
      if (v >= 1.0) return 'Your Calmar of ' + fmt(v) + ' shows acceptable reward for the drawdown risk.';
      return 'A Calmar of ' + fmt(v) + ' means the drawdown pain may not justify the returns.';
    }
  },
  'risk.best_day': {
    definition: 'Your single best daily return. Large values indicate high volatility.',
    ranges: null,
    personalize: function(v) { return null; }
  },
  'risk.worst_day': {
    definition: 'Your single worst daily return. Reflects tail risk exposure.',
    ranges: null,
    personalize: function(v) { return null; }
  },
  'risk.best_month': {
    definition: 'Your best calendar month return.',
    ranges: null,
    personalize: function(v) { return null; }
  },
  'risk.worst_month': {
    definition: 'Your worst calendar month return.',
    ranges: null,
    personalize: function(v) { return null; }
  },
  'risk.positive_days': {
    definition: 'Percentage of trading days with a positive return. Markets average around 53%.',
    ranges: [
      { min: 55, label: 'Above avg', color: 'green' },
      { min: 48, label: 'Normal', color: 'yellow' },
      { min: 0, label: 'Below avg', color: 'red' }
    ],
    personalize: function(v) {
      if (v == null) return null;
      return v >= 53 ? 'At ' + fmt(v,1) + '%, you have more green days than average.' : 'At ' + fmt(v,1) + '%, slightly below the market norm of ~53%.';
    }
  },
  'period.return': {
    definition: 'Simple return over the selected period (end value / start value - 1).',
    ranges: null,
    personalize: function(v) { return null; }
  }
};

// Tooltip DOM singleton
let _tooltipEl = null;
function _getTooltipEl() {
  if (_tooltipEl) return _tooltipEl;
  _tooltipEl = document.createElement('div');
  _tooltipEl.className = 'metric-tooltip';
  _tooltipEl.setAttribute('role', 'tooltip');
  document.body.appendChild(_tooltipEl);
  _tooltipEl.addEventListener('mouseenter', function() { _tooltipEl.classList.add('visible'); });
  _tooltipEl.addEventListener('mouseleave', function() { _hideTooltip(); });
  return _tooltipEl;
}

function _showTooltip(anchor, key, rawValue) {
  var def = METRIC_TOOLTIPS[key];
  if (!def) return;
  var tip = _getTooltipEl();

  var html = '<div class="tt-def">' + def.definition + '</div>';

  if (def.ranges && def.ranges.length > 0 && rawValue != null) {
    var rating = def.ranges[def.ranges.length - 1];
    for (var i = 0; i < def.ranges.length; i++) {
      if (rawValue >= def.ranges[i].min) { rating = def.ranges[i]; break; }
    }
    html += '<div class="tt-range tt-range-' + rating.color + '">' + rating.label + '</div>';
  }

  var personal = def.personalize(rawValue);
  if (personal) {
    html += '<div class="tt-personal">' + personal + '</div>';
  }

  tip.innerHTML = html;
  tip.classList.add('visible');

  // Position relative to anchor
  var rect = anchor.getBoundingClientRect();
  var tipW = tip.offsetWidth;
  var tipH = tip.offsetHeight;
  var left = rect.left + rect.width / 2 - tipW / 2;
  var top = rect.top - tipH - 8;

  // Clamp to viewport
  if (left < 8) left = 8;
  if (left + tipW > window.innerWidth - 8) left = window.innerWidth - 8 - tipW;
  if (top < 8) {
    top = rect.bottom + 8;
  }

  tip.style.left = left + 'px';
  tip.style.top = top + window.scrollY + 'px';
}

function _hideTooltip() {
  if (_tooltipEl) _tooltipEl.classList.remove('visible');
}

// Build a metric card HTML string with optional tooltip icon
function metricCardHtml(label, value, cssClass, sub, tooltipKey, rawValue) {
  var iconHtml = '';
  if (tooltipKey && METRIC_TOOLTIPS[tooltipKey]) {
    var rv = rawValue != null ? rawValue : '';
    iconHtml = ' <span class="tt-icon" data-tt-key="' + tooltipKey + '" data-tt-val="' + rv + '" tabindex="0" aria-label="Info">&#9432;</span>';
  }
  return '<div class="metric-card">'
    + '<div class="label">' + label + iconHtml + '</div>'
    + '<div class="value ' + (cssClass || '') + '">' + value + '</div>'
    + (sub ? '<div class="sub">' + sub + '</div>' : '')
    + '</div>';
}

// Attach event listeners (delegated on body)
(function() {
  var hideTimer = null;

  document.body.addEventListener('mouseover', function(e) {
    var icon = e.target.closest('.tt-icon');
    if (!icon) return;
    clearTimeout(hideTimer);
    var key = icon.getAttribute('data-tt-key');
    var val = icon.getAttribute('data-tt-val');
    _showTooltip(icon, key, val !== '' ? parseFloat(val) : null);
  });

  document.body.addEventListener('mouseout', function(e) {
    var icon = e.target.closest('.tt-icon');
    if (!icon) return;
    hideTimer = setTimeout(_hideTooltip, 120);
  });

  // Click support for mobile
  document.body.addEventListener('click', function(e) {
    var icon = e.target.closest('.tt-icon');
    if (!icon) {
      _hideTooltip();
      return;
    }
    var tip = _getTooltipEl();
    if (tip.classList.contains('visible')) {
      _hideTooltip();
    } else {
      var key = icon.getAttribute('data-tt-key');
      var val = icon.getAttribute('data-tt-val');
      _showTooltip(icon, key, val !== '' ? parseFloat(val) : null);
    }
  });

  // Keyboard: show on Enter/Space
  document.body.addEventListener('keydown', function(e) {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    var icon = e.target.closest('.tt-icon');
    if (!icon) return;
    e.preventDefault();
    var key = icon.getAttribute('data-tt-key');
    var val = icon.getAttribute('data-tt-val');
    var tip = _getTooltipEl();
    if (tip.classList.contains('visible')) { _hideTooltip(); }
    else { _showTooltip(icon, key, val !== '' ? parseFloat(val) : null); }
  });

  // Hide on scroll/resize
  window.addEventListener('scroll', _hideTooltip, true);
  window.addEventListener('resize', _hideTooltip);
})();
