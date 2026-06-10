/**
 * createPaginator — reusable pagination controller.
 * Encapsulates page-size state, page slicing, and rendering of pagination
 * controls (page-size dropdown, prev/next, numbered pages, "Page X of Y"
 * indicator) into a container element. Mirrors the page-window logic of
 * buildTxPagination() in transactions.js and reuses the .pagination CSS.
 *
 * @param {Element|null} containerEl - element to render controls into (class
 *   "pagination" is added automatically). Pass null for headless/data-only use.
 * @param {Object} [opts]
 * @param {number} [opts.pageSize] - initial page size (default: opts.pageSizes[0])
 * @param {number[]} [opts.pageSizes] - selectable page sizes (default: [10, 25, 50])
 * @param {function(Object)} [opts.onChange] - called with the paginator after
 *   the current page or page size changes via the rendered controls, before re-render
 * @returns {Object} paginator - setData(arr), getPage(), render(), reset(), currentPage, pageSize
 */
function createPaginator(containerEl, opts) {
  opts = opts || {};
  var pageSizes = opts.pageSizes || [10, 25, 50];

  var paginator = {
    currentPage: 0,
    pageSize: opts.pageSize || pageSizes[0],
    _data: [],
  };

  function totalPages() {
    return Math.max(1, Math.ceil(paginator._data.length / paginator.pageSize));
  }

  function clampPage() {
    var total = totalPages();
    if (paginator.currentPage >= total) paginator.currentPage = total - 1;
    if (paginator.currentPage < 0) paginator.currentPage = 0;
  }

  // Windowed page-button list with ellipses, matching buildTxPagination().
  function buildPageButtons(total, current) {
    if (total <= 1) return '';
    var shown = new Set([0, total - 1, current - 1, current, current + 1].filter(function (p) {
      return p >= 0 && p < total;
    }));
    var sorted = Array.from(shown).sort(function (a, b) { return a - b; });
    var html = '';
    var prev = -1;
    sorted.forEach(function (p) {
      if (prev !== -1 && p > prev + 1) html += '<span class="pagination-ellipsis">…</span>';
      html += '<button type="button" class="pagination-page' + (p === current ? ' active' : '') +
        '" data-page="' + p + '"' + (p === current ? ' disabled' : '') + '>' + (p + 1) + '</button>';
      prev = p;
    });
    return html;
  }

  function goTo(page) {
    var target = Math.max(0, Math.min(page, totalPages() - 1));
    if (target === paginator.currentPage) return;
    paginator.currentPage = target;
    if (opts.onChange) opts.onChange(paginator);
    paginator.render();
  }

  paginator.setData = function (arr) {
    paginator._data = arr || [];
    clampPage();
  };

  paginator.getPage = function () {
    var start = paginator.currentPage * paginator.pageSize;
    return paginator._data.slice(start, start + paginator.pageSize);
  };

  paginator.reset = function () {
    paginator.currentPage = 0;
  };

  paginator.render = function () {
    if (!containerEl) return;
    containerEl.classList.add('pagination');

    var total = totalPages();
    var current = paginator.currentPage;
    var sizeOptions = pageSizes.map(function (size) {
      return '<option value="' + size + '"' + (size === paginator.pageSize ? ' selected' : '') + '>' + size + '</option>';
    }).join('');

    var html = '<label class="pagination-size">' +
      '<span class="pagination-size-label">Show</span>' +
      '<select class="pagination-size-select" aria-label="Rows per page">' + sizeOptions + '</select>' +
      '</label>';
    html += '<button type="button" class="pagination-prev" aria-label="Previous page"' + (current === 0 ? ' disabled' : '') + '>‹</button>';
    html += buildPageButtons(total, current);
    html += '<button type="button" class="pagination-next" aria-label="Next page"' + (current >= total - 1 ? ' disabled' : '') + '>›</button>';
    html += '<span class="pagination-info" aria-live="polite">Page ' + (current + 1) + ' of ' + total + ' (' + paginator._data.length + ' total)</span>';
    containerEl.innerHTML = html;

    var prevBtn = containerEl.querySelector('.pagination-prev');
    var nextBtn = containerEl.querySelector('.pagination-next');
    var sizeSelect = containerEl.querySelector('.pagination-size-select');
    if (prevBtn) prevBtn.addEventListener('click', function () { goTo(current - 1); });
    if (nextBtn) nextBtn.addEventListener('click', function () { goTo(current + 1); });
    containerEl.querySelectorAll('.pagination-page').forEach(function (btn) {
      btn.addEventListener('click', function () { goTo(parseInt(btn.dataset.page, 10)); });
    });
    if (sizeSelect) {
      sizeSelect.addEventListener('change', function () {
        paginator.pageSize = parseInt(sizeSelect.value, 10);
        paginator.reset();
        if (opts.onChange) opts.onChange(paginator);
        paginator.render();
      });
    }
  };

  return paginator;
}
