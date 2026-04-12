// --- Investment Notes section ---
try {
  const notes = D.investment_notes || [];
  if (notes.length > 0) {
    document.getElementById('notesSection').style.display = '';
    const listEl = document.getElementById('notesList');

    const convClass = {high:'conviction-high', medium:'conviction-medium', low:'conviction-low'};
    const actClass  = {buy:'action-buy', sell:'action-sell', avoid:'action-avoid', watch:'action-watch'};

    function renderTickerBadges(details) {
      return details.map(function(t) {
        const heldClass = t.held ? ' held' : '';
        const priceStr = t.price != null ? fmt(t.price, 2) + (t.currency ? ' ' + t.currency : '') : '';
        return '<span class="note-ticker' + heldClass + '" title="' + t.ticker + (t.held ? ' (held)' : '') + '">' +
          t.ticker +
          (priceStr ? '<span class="ticker-price">' + priceStr + '</span>' : '') +
          '</span>';
      }).join('');
    }

    function renderTickerCards(details) {
      if (!details || details.length === 0) return '';
      return '<div class="note-ticker-cards">' + details.map(function(t) {
        const priceStr = t.price != null ? fmt(t.price, 2) + ' ' + (t.currency || '') : 'n/a';
        let heldHtml = '';
        if (t.held) {
          const pctStr = t.unrealized_gain_pct != null
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

    notes.forEach(function(note) {
      const card = document.createElement('div');
      card.className = 'note-card';

      const badges = (note.ticker_details || []);
      const badgeHtml = renderTickerBadges(badges);
      const convHtml = '<span class="conviction-chip ' + (convClass[note.conviction] || '') + '">' + note.conviction + '</span>';
      const actHtml  = '<span class="action-badge '  + (actClass[note.action]      || '') + '">' + note.action + '</span>';

      card.innerHTML =
        '<div class="note-header">' +
          '<div class="note-meta">' +
            '<div class="note-title">' + note.title + '</div>' +
            '<div class="note-summary">' + note.summary + '</div>' +
          '</div>' +
          '<div class="note-badges">' + badgeHtml + convHtml + actHtml + '</div>' +
          '<span class="note-chevron">▼</span>' +
        '</div>' +
        '<div class="note-detail">' +
          renderTickerCards(badges) +
          (note.body
            ? '<div class="note-body">' + (typeof marked !== 'undefined' ? marked.parse(note.body) : '<pre>' + note.body + '</pre>') + '</div>'
            : '') +
          '<div class="note-footer">Created ' + note.created_at.slice(0, 10) +
            (note.updated_at !== note.created_at ? ' · Updated ' + note.updated_at.slice(0, 10) : '') +
          '</div>' +
        '</div>';

      card.querySelector('.note-header').addEventListener('click', function() {
        card.classList.toggle('open');
      });

      listEl.appendChild(card);
    });
  }
} catch(e) { console.error('Notes section error:', e); }
