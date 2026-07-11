// ---- Manual transaction modal (report / positions context) ----
// Provides: openMtxModal, openMtxEditModal, openMtxDelModal, confirmMtxDelete,
//           closeMtxModal, closeMtxDelModal, refreshPosTickerTx
(function() {
  'use strict';

  var _deleteId = null;
  var _deleteTicker = null;

  var TYPE_OPTIONS = {
    stock:   ['BUY', 'SELL', 'DIVIDEND', 'STOCK SPLIT'],
    cfd:     ['BUY', 'SELL'],
    crypto:  ['BUY', 'SELL', 'Staking reward'],
    savings: ['BUY', 'SELL', 'Interest PAID'],
  };

  // Track open ticker panels for refresh after CRUD
  var _openPanels = {}; // raw ticker -> containerEl

  // ---- Helpers ----

  function _updateTypeOptions(preset) {
    var ac = document.getElementById('mtxAssetClass').value;
    var sel = document.getElementById('mtxType');
    var opts = TYPE_OPTIONS[ac] || [];
    sel.innerHTML = '<option value="">Select…</option>';
    opts.forEach(function(t) {
      var o = document.createElement('option');
      o.value = t; o.textContent = t;
      if (preset && t === preset) o.selected = true;
      sel.appendChild(o);
    });
  }

  function _onCurrencyChange() {
    var cur = (document.getElementById('mtxCurrency').value || '').trim().toUpperCase();
    var label = document.getElementById('mtxFxLabel');
    if (label) label.textContent = cur && cur !== 'EUR' ? '(required for non-EUR)' : '(EUR rate)';
  }

  function _clearErrors() {
    ['Date','AssetClass','Ticker','Type','Quantity','Price_per_share','Currency','Fx_rate','Commission','Withholding_tax'].forEach(function(f) {
      var el = document.getElementById('mtxErr' + f);
      if (el) el.textContent = '';
    });
    var fe = document.getElementById('mtxFormError');
    if (fe) { fe.style.display = 'none'; fe.textContent = ''; }
  }

  function _showToast(msg, type) {
    var toast = document.createElement('div');
    toast.className = 'notify-toast';
    var icon = type === 'error' ? '✕' : '✓';
    toast.innerHTML = '<div class="notify-toast-content">'
      + '<span class="notify-toast-icon">' + icon + '</span>'
      + '<span class="notify-toast-text">' + msg + '</span>'
      + '</div>';
    document.body.appendChild(toast);
    setTimeout(function() { toast.classList.add('notify-toast-visible'); }, 10);
    setTimeout(function() {
      toast.classList.remove('notify-toast-visible');
      toast.classList.add('notify-toast-exit');
      setTimeout(function() { if (toast.parentNode) toast.parentNode.removeChild(toast); }, 300);
    }, 3500);
  }

  function _refreshOpenPanel(rawTicker) {
    if (!rawTicker) return;
    var el = _openPanels[rawTicker];
    if (el) window.refreshPosTickerTx(rawTicker, null, el);
  }

  // ---- Public API ----

  window.openMtxModal = function(ticker, assetClass) {
    document.getElementById('mtxId').value = '';
    document.getElementById('mtxReloadTicker').value = ticker || '';
    document.getElementById('mtxModalTitle').textContent = 'Add Transaction';
    document.getElementById('mtxSubmitBtn').textContent = 'Add';
    document.getElementById('mtxForm').reset();
    _clearErrors();
    document.getElementById('mtxCurrency').value = 'EUR';
    document.getElementById('mtxFx').value = '';
    if (ticker) document.getElementById('mtxTicker').value = ticker;
    if (assetClass) document.getElementById('mtxAssetClass').value = assetClass;
    _updateTypeOptions();
    document.getElementById('mtxModal').style.display = 'flex';
    document.getElementById('mtxDate').focus();
  };

  window.openMtxEditModal = function(row) {
    document.getElementById('mtxId').value = row.id;
    document.getElementById('mtxReloadTicker').value = row.ticker || '';
    document.getElementById('mtxModalTitle').textContent = 'Edit Transaction';
    document.getElementById('mtxSubmitBtn').textContent = 'Save';
    _clearErrors();
    document.getElementById('mtxDate').value = row.date || '';
    document.getElementById('mtxAssetClass').value = row.asset_class || '';
    document.getElementById('mtxTicker').value = row.ticker || '';
    _updateTypeOptions(row.type);
    document.getElementById('mtxType').value = row.type || '';
    document.getElementById('mtxQty').value = row.quantity != null ? row.quantity : '';
    document.getElementById('mtxPrice').value = row.price_per_share != null ? row.price_per_share : '';
    document.getElementById('mtxCurrency').value = row.currency || 'EUR';
    document.getElementById('mtxFx').value = row.fx_rate != null ? row.fx_rate : '';
    document.getElementById('mtxCommission').value = row.commission != null ? row.commission : '';
    document.getElementById('mtxWht').value = row.withholding_tax != null ? row.withholding_tax : '';
    _onCurrencyChange();
    document.getElementById('mtxModal').style.display = 'flex';
    document.getElementById('mtxDate').focus();
  };

  window.closeMtxModal = function() {
    document.getElementById('mtxModal').style.display = 'none';
  };

  window.openMtxDelModal = function(id, ticker, date) {
    _deleteId = id;
    _deleteTicker = ticker;
    document.getElementById('mtxDelBody').textContent =
      'Delete ' + (ticker || 'transaction') + ' on ' + date + '? This cannot be undone.';
    document.getElementById('mtxDelModal').style.display = 'flex';
    document.getElementById('mtxDelConfirmBtn').focus();
  };

  window.closeMtxDelModal = function() {
    document.getElementById('mtxDelModal').style.display = 'none';
    _deleteId = null;
    _deleteTicker = null;
  };

  window.confirmMtxDelete = function() {
    if (!_deleteId) return;
    var btn = document.getElementById('mtxDelConfirmBtn');
    btn.disabled = true;
    var ticker = _deleteTicker;
    fetch('/api/transactions/' + _deleteId, { method: 'DELETE' })
      .then(function(r) { return r.json().then(function(d) { return { ok: r.ok, data: d }; }); })
      .then(function(res) {
        closeMtxDelModal();
        if (res.ok) {
          _showToast('Transaction deleted', 'success');
          _refreshOpenPanel(ticker);
        } else {
          _showToast(res.data.error || 'Delete failed', 'error');
        }
      })
      .catch(function() { _showToast('Network error', 'error'); })
      .finally(function() { btn.disabled = false; });
  };

  // Load/refresh per-ticker transactions into a container element
  window.refreshPosTickerTx = function(rawTicker, _ac, containerEl) {
    if (!containerEl) return;
    _openPanels[rawTicker] = containerEl;
    var isPremium = typeof D !== 'undefined' && D.user && (D.user.role === 'premium' || D.user.role === 'admin');
    containerEl.innerHTML = '<span style="color:var(--muted);font-size:0.8rem">Loading…</span>';

    fetch('/api/transactions?ticker=' + encodeURIComponent(rawTicker) + '&per_page=200')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        var txs = data.transactions || [];
        if (!txs.length) {
          containerEl.innerHTML = '<span style="color:var(--muted);font-size:0.8rem">No transactions for this ticker.</span>';
          return;
        }
        var colCount = isPremium ? 8 : 7;
        var html = '<div class="table-scroll" style="margin-top:0.25rem"><table class="data-table">'
          + '<thead><tr><th>Date</th><th>Type</th><th>Qty</th><th>Price</th><th>Total</th><th>Ccy</th><th>Src</th>'
          + (isPremium ? '<th></th>' : '') + '</tr></thead><tbody>';

        txs.forEach(function(r) {
          var isManual = r.broker_source === 'manual';
          var qty   = r.quantity != null ? (+r.quantity).toLocaleString('en', {minimumFractionDigits:0, maximumFractionDigits:4}) : '—';
          var price = r.price_per_share != null ? (+r.price_per_share).toLocaleString('en', {minimumFractionDigits:0, maximumFractionDigits:4}) : '—';
          var total = r.total_amount != null ? (+r.total_amount).toLocaleString('en', {minimumFractionDigits:2, maximumFractionDigits:2}) : '—';
          var srcIcon = isManual
            ? '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="opacity:.7" title="Manual entry"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>'
            : '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="opacity:.5" title="Imported"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>';

          var actions = '';
          if (isPremium && isManual) {
            var rowJson = JSON.stringify(r).replace(/</g, '\\u003c');
            var tEsc = (r.ticker || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
            actions = '<td style="white-space:nowrap">'
              + '<button style="padding:2px 7px;font-size:.72rem;border:1px solid var(--border);border-radius:4px;cursor:pointer;background:var(--card-bg);color:var(--text);margin-right:3px"'
              + ' onclick=\'openMtxEditModal(' + rowJson + ')\'>Edit</button>'
              + '<button style="padding:2px 7px;font-size:.72rem;border:1px solid #fca5a5;border-radius:4px;cursor:pointer;background:var(--card-bg);color:#dc2626"'
              + ' onclick=\'openMtxDelModal(' + r.id + ',\\\'' + tEsc + '\\\',\\\'' + r.date + '\\\')\'>Del</button>'
              + '</td>';
          } else if (isPremium) {
            actions = '<td></td>';
          }

          html += '<tr>'
            + '<td>' + r.date + '</td>'
            + '<td>' + (r.type || '') + '</td>'
            + '<td>' + qty + '</td>'
            + '<td>' + price + '</td>'
            + '<td>' + total + '</td>'
            + '<td>' + (r.currency || '') + '</td>'
            + '<td>' + srcIcon + '</td>'
            + actions
            + '</tr>';
        });

        html += '</tbody></table></div>';
        containerEl.innerHTML = html;
      })
      .catch(function() {
        containerEl.innerHTML = '<span style="color:#dc2626;font-size:0.8rem">Failed to load transactions.</span>';
      });
  };

  // ---- Form submit ----

  document.getElementById('mtxAssetClass').addEventListener('change', function() { _updateTypeOptions(); });
  document.getElementById('mtxCurrency').addEventListener('input', _onCurrencyChange);

  document.getElementById('mtxForm').addEventListener('submit', function(e) {
    e.preventDefault();
    _clearErrors();
    var id = document.getElementById('mtxId').value;
    var reloadTicker = document.getElementById('mtxReloadTicker').value;
    var payload = {
      date:            document.getElementById('mtxDate').value,
      asset_class:     document.getElementById('mtxAssetClass').value,
      ticker:          (document.getElementById('mtxTicker').value || '').trim().toUpperCase(),
      type:            document.getElementById('mtxType').value,
      quantity:        document.getElementById('mtxQty').value || null,
      price_per_share: document.getElementById('mtxPrice').value || null,
      currency:        (document.getElementById('mtxCurrency').value || '').trim().toUpperCase() || 'EUR',
      fx_rate:         document.getElementById('mtxFx').value || null,
      commission:      document.getElementById('mtxCommission').value || null,
      withholding_tax: document.getElementById('mtxWht').value || null,
    };

    var url = id ? '/api/transactions/' + id : '/api/transactions';
    var method = id ? 'PUT' : 'POST';
    var btn = document.getElementById('mtxSubmitBtn');
    btn.disabled = true;

    fetch(url, { method: method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      .then(function(r) { return r.json().then(function(d) { return { ok: r.ok, status: r.status, data: d }; }); })
      .then(function(res) {
        if (res.ok) {
          closeMtxModal();
          _showToast(id ? 'Transaction updated' : 'Transaction added', 'success');
          var refreshTicker = reloadTicker || payload.ticker;
          _refreshOpenPanel(refreshTicker);
        } else if (res.status === 422 && res.data.fields) {
          Object.keys(res.data.fields).forEach(function(k) {
            var key = k.charAt(0).toUpperCase() + k.slice(1);
            var el = document.getElementById('mtxErr' + key);
            if (el) el.textContent = res.data.fields[k];
          });
        } else {
          var fe = document.getElementById('mtxFormError');
          fe.textContent = (res.data && res.data.error) || 'Error saving transaction';
          fe.style.display = 'block';
        }
      })
      .catch(function() { _showToast('Network error', 'error'); })
      .finally(function() { btn.disabled = false; });
  });

  // ---- Keyboard + backdrop close ----

  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
      if (document.getElementById('mtxModal').style.display !== 'none') closeMtxModal();
      if (document.getElementById('mtxDelModal').style.display !== 'none') closeMtxDelModal();
    }
  });
  document.getElementById('mtxModal').addEventListener('click', function(e) {
    if (e.target === this) closeMtxModal();
  });
  document.getElementById('mtxDelModal').addEventListener('click', function(e) {
    if (e.target === this) closeMtxDelModal();
  });

  // ---- Show "Add New Ticker" buttons for premium/admin ----
  (function() {
    var isPremium = typeof D !== 'undefined' && D.user && (D.user.role === 'premium' || D.user.role === 'admin');
    if (!isPremium) return;
    document.querySelectorAll('[data-role="addNewTickerBtn"]').forEach(function(btn) {
      btn.style.display = '';
    });
  })();

})();
