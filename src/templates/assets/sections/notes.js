// --- Investment Notes section ---
function initNotesWidget() {
(function() {
  var _notes = D.investment_notes ? D.investment_notes.slice() : [];
  var _canEdit = D.user && (D.user.role === 'premium' || D.user.role === 'admin');

  var convClass = {high:'conviction-high', medium:'conviction-medium', low:'conviction-low'};
  var actClass  = {buy:'action-buy', sell:'action-sell', avoid:'action-avoid', watch:'action-watch'};

  function fmtPrice(t) {
    if (t.price == null) return '';
    return fmt(t.price, 2) + (t.currency ? ' ' + t.currency : '');
  }

  function renderTickerBadges(details) {
    return (details || []).map(function(t) {
      var heldClass = t.held ? ' held' : '';
      var priceStr = fmtPrice(t);
      return '<span class="note-ticker' + heldClass + '" title="' + t.ticker + (t.held ? ' (held)' : '') + '">' +
        t.ticker +
        (priceStr ? '<span class="ticker-price">' + priceStr + '</span>' : '') +
        '</span>';
    }).join('');
  }

  function renderTickerCards(details) {
    if (!details || details.length === 0) return '';
    return '<div class="note-ticker-cards">' + details.map(function(t) {
      var priceStr = fmtPrice(t) || 'n/a';
      var heldHtml = '';
      if (t.held) {
        var pctStr = t.unrealized_gain_pct != null
          ? '<div class="ntc-pct ' + (t.unrealized_gain_pct >= 0 ? 'pos' : 'neg') + '">' + sign(t.unrealized_gain_pct) + '%</div>'
          : '';
        heldHtml = '<div class="ntc-held">Held · ' + fmt(t.quantity, 4) + ' · ' + fmtEur(t.cost_basis_eur) + ' cost</div>' + pctStr;
      }
      return '<div class="note-ticker-card">' +
        '<div class="ntc-ticker">' + t.ticker + '</div>' +
        '<div class="ntc-price">' + priceStr + (t.date ? '<span style="font-size:0.68rem;margin-left:0.3rem;opacity:0.7">' + t.date + '</span>' : '') + '</div>' +
        heldHtml +
      '</div>';
    }).join('') + '</div>';
  }

  function renderNote(note) {
    var card = document.createElement('div');
    card.className = 'note-card';
    card.dataset.noteId = note.id;

    var badges = note.ticker_details || [];
    var badgeHtml = renderTickerBadges(badges);
    var convHtml = '<span class="conviction-chip ' + (convClass[note.conviction] || '') + '">' + note.conviction + '</span>';
    var actHtml  = '<span class="action-badge '  + (actClass[note.action]      || '') + '">' + note.action + '</span>';

    var editBtns = _canEdit
      ? '<div class="note-actions">' +
          '<button class="note-action-btn edit" onclick="editNote(' + note.id + ',event)">Edit</button>' +
          '<button class="note-action-btn del"  onclick="deleteNote(' + note.id + ',event)">Delete</button>' +
        '</div>'
      : '';

    card.innerHTML =
      '<div class="note-header">' +
        '<div class="note-meta">' +
          '<div class="note-title">' + _esc(note.title) + '</div>' +
          '<div class="note-summary">' + _esc(note.summary) + '</div>' +
        '</div>' +
        '<div class="note-badges">' + badgeHtml + convHtml + actHtml + '</div>' +
        '<span class="note-chevron">▼</span>' +
      '</div>' +
      '<div class="note-detail">' +
        renderTickerCards(badges) +
        (note.body
          ? '<div class="note-body">' + (typeof marked !== 'undefined' ? marked.parse(note.body) : '<pre>' + _esc(note.body) + '</pre>') + '</div>'
          : '') +
        '<div class="note-footer">' +
          'Created ' + note.created_at.slice(0, 10) +
          (note.updated_at !== note.created_at ? ' · Updated ' + note.updated_at.slice(0, 10) : '') +
          (editBtns ? '&ensp;' + editBtns : '') +
        '</div>' +
      '</div>';

    card.querySelector('.note-header').addEventListener('click', function() {
      card.classList.toggle('open');
    });

    return card;
  }

  function _esc(s) {
    return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function renderAll() {
    var list = scopedFind(null, 'notesList');
    var empty = scopedFind(null, 'notesEmpty');
    // Remove old cards
    list.querySelectorAll('.note-card').forEach(function(c){ c.remove(); });
    if (_notes.length === 0) {
      if (empty) empty.style.display = '';
    } else {
      if (empty) empty.style.display = 'none';
      _notes.forEach(function(n) { list.appendChild(renderNote(n)); });
    }
  }

  renderAll();

  // --- Modal ---
  window.openNoteModal = function(note) {
    scopedFind(null, 'noteModalTitle').textContent = note ? 'Edit note' : 'Add note';
    scopedFind(null, 'noteEditId').value = note ? note.id : '';
    scopedFind(null, 'nfTitle').value      = note ? (note.title      || '') : '';
    scopedFind(null, 'nfSummary').value    = note ? (note.summary    || '') : '';
    scopedFind(null, 'nfTickers').value    = note ? (note.tickers    || '') : '';
    scopedFind(null, 'nfConviction').value = note ? (note.conviction || 'medium') : 'medium';
    scopedFind(null, 'nfAction').value     = note ? (note.action     || 'watch')  : 'watch';
    scopedFind(null, 'nfBody').value       = note ? (note.body       || '') : '';
    scopedFind(null, 'noteModalError').textContent = '';
    scopedFind(null, 'btnSaveNote').disabled = false;
    scopedFind(null, 'noteModal').style.display = 'flex';
    scopedFind(null, 'nfTitle').focus();
  };

  window.closeNoteModal = function() {
    scopedFind(null, 'noteModal').style.display = 'none';
  };

  window.saveNote = function() {
    var id     = scopedFind(null, 'noteEditId').value;
    var title  = scopedFind(null, 'nfTitle').value.trim();
    var summary= scopedFind(null, 'nfSummary').value.trim();
    if (!title || !summary) {
      scopedFind(null, 'noteModalError').textContent = 'Title and summary are required.';
      return;
    }
    var payload = {
      title:      title,
      summary:    summary,
      tickers:    scopedFind(null, 'nfTickers').value.trim(),
      conviction: scopedFind(null, 'nfConviction').value,
      action:     scopedFind(null, 'nfAction').value,
      body:       scopedFind(null, 'nfBody').value,
    };
    var btn = scopedFind(null, 'btnSaveNote');
    btn.disabled = true;

    var url    = id ? '/api/notes/' + id : '/api/notes';
    var method = id ? 'PUT' : 'POST';
    fetch(url, {
      method: method,
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    })
    .then(function(r) {
      if (!r.ok) return r.json().then(function(e){ throw new Error(e.error || r.status); });
      return r.json();
    })
    .then(function(saved) {
      if (id) {
        var idx = _notes.findIndex(function(n){ return n.id == id; });
        if (idx !== -1) _notes[idx] = saved; else _notes.unshift(saved);
      } else {
        _notes.unshift(saved);
      }
      renderAll();
      closeNoteModal();
    })
    .catch(function(e) {
      scopedFind(null, 'noteModalError').textContent = e.message;
      btn.disabled = false;
    });
  };

  window.editNote = function(id, e) {
    if (e) e.stopPropagation();
    var note = _notes.find(function(n){ return n.id === id; });
    if (note) openNoteModal(note);
  };

  window.deleteNote = function(id, e) {
    if (e) e.stopPropagation();
    if (!confirm('Delete this note?')) return;
    fetch('/api/notes/' + id, {method: 'DELETE'})
    .then(function(r) {
      if (!r.ok) throw new Error('Delete failed');
      _notes = _notes.filter(function(n){ return n.id !== id; });
      renderAll();
    })
    .catch(function(err) { alert(err.message); });
  };

  // Escape key closes modal
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') { closeNoteModal(); }
  });

  // Show Add button only for editable users
  if (!_canEdit) {
    var btn = scopedFind(null, 'btnAddNote');
    if (btn) btn.style.display = 'none';
  }

})();

}
initNotesWidget();
