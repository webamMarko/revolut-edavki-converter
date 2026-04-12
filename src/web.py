"""Lightweight web UI for CSV upload and import."""

import json
import os
import tempfile
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path


def _parse_multipart(headers, body):
    """Parse multipart/form-data body into fields and files.

    Returns: (fields: dict[str, str], files: list[dict]) where each file dict
    has keys 'filename', 'content' (bytes), 'field_name'.
    """
    content_type = headers.get("Content-Type", "")
    if "boundary=" not in content_type:
        return {}, []

    boundary = content_type.split("boundary=")[1].strip()
    if boundary.startswith('"') and boundary.endswith('"'):
        boundary = boundary[1:-1]
    boundary = boundary.encode()

    parts = body.split(b"--" + boundary)
    fields = {}
    files = []

    for part in parts:
        part = part.strip()
        if not part or part == b"--":
            continue

        if b"\r\n\r\n" not in part:
            continue
        header_block, content = part.split(b"\r\n\r\n", 1)
        # Strip trailing \r\n
        if content.endswith(b"\r\n"):
            content = content[:-2]

        header_str = header_block.decode("utf-8", errors="replace")
        # Parse Content-Disposition
        name = None
        filename = None
        for line in header_str.split("\r\n"):
            if "Content-Disposition:" in line:
                for param in line.split(";"):
                    param = param.strip()
                    if param.startswith("name="):
                        name = param.split("=", 1)[1].strip('"')
                    elif param.startswith("filename="):
                        filename = param.split("=", 1)[1].strip('"')

        if filename:
            files.append({"filename": filename, "content": content, "field_name": name})
        elif name:
            fields[name] = content.decode("utf-8", errors="replace")

    return fields, files


class UploadHandler(BaseHTTPRequestHandler):
    verbose = False

    def log_message(self, format, *args):
        if self.verbose:
            super().log_message(format, *args)

    def do_GET(self):
        if self.path == "/":
            self._serve_upload_page()
        elif self.path == "/status":
            self._serve_status()
        elif self.path == "/report":
            self._serve_report()
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/upload":
            self._handle_upload()
        elif self.path == "/sync":
            self._handle_sync()
        else:
            self.send_error(404)

    def _serve_upload_page(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(_UPLOAD_HTML.encode("utf-8"))

    def _serve_status(self):
        from .db import get_connection, DB_PATH

        data = {"has_data": False, "db_path": str(DB_PATH)}
        if DB_PATH.exists():
            conn = get_connection()
            try:
                row_count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
                data["has_data"] = row_count > 0
                data["transaction_count"] = row_count
                data["ticker_count"] = conn.execute(
                    "SELECT COUNT(DISTINCT ticker) FROM transactions WHERE ticker IS NOT NULL"
                ).fetchone()[0]
                date_range = conn.execute("SELECT MIN(date), MAX(date) FROM transactions").fetchone()
                if date_range and date_range[0]:
                    data["date_range"] = [date_range[0][:10], date_range[1][:10]]
                # Per-class counts
                class_rows = conn.execute(
                    "SELECT asset_class, COUNT(*) FROM transactions GROUP BY asset_class"
                ).fetchall()
                data["asset_classes"] = {r[0]: r[1] for r in class_rows}
                import_count = conn.execute("SELECT COUNT(*) FROM import_log").fetchone()[0]
                data["import_count"] = import_count
                price_count = conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
                data["price_count"] = price_count
            finally:
                conn.close()

        self._json_response(data)

    def _handle_upload(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 100 * 1024 * 1024:  # 100MB limit
            self._json_response({"error": "File too large (max 100MB)"}, status=413)
            return

        body = self.rfile.read(content_length)
        fields, files = _parse_multipart(self.headers, body)

        if not files:
            self._json_response({"error": "No files uploaded"}, status=400)
            return

        from .db import get_connection
        from .importer import import_csv

        conn = get_connection()
        results = []
        try:
            for f in files:
                filename = f["filename"]
                ext = Path(filename).suffix.lower()
                if ext not in (".csv", ".xlsx", ".xls"):
                    results.append({"filename": filename, "error": f"Unsupported format: {ext}"})
                    continue

                # Write to temp file preserving original name
                tmp_dir = tempfile.mkdtemp(prefix="revolut_upload_")
                tmp_path = os.path.join(tmp_dir, filename)
                try:
                    with open(tmp_path, "wb") as tmp:
                        tmp.write(f["content"])
                    result = import_csv(conn, tmp_path, verbose=self.verbose)
                    results.append({
                        "filename": filename,
                        "total": result.total,
                        "new": result.new,
                        "skipped": result.skipped,
                    })
                except Exception as e:
                    results.append({"filename": filename, "error": str(e)})
                finally:
                    os.unlink(tmp_path)
                    os.rmdir(tmp_dir)
        finally:
            conn.close()

        self._json_response({"results": results})

    def _handle_sync(self):
        from .db import get_connection
        from .price_fetcher import sync_all

        conn = get_connection()
        try:
            sync_all(conn, verbose=self.verbose)
            self._json_response({"ok": True})
        except Exception as e:
            self._json_response({"error": str(e)}, status=500)
        finally:
            conn.close()

    def _serve_report(self):
        from .db import get_connection
        from .analytics import compute_analytics
        from .tax import compute_tax_report
        from .html_report import generate_html_report, query_transactions
        from datetime import datetime

        conn = get_connection()
        try:
            analytics = compute_analytics(conn, scope="all")
            tax = None
            try:
                tax = compute_tax_report(conn, year=datetime.now().year, include_unrealized=True, scope="all")
            except Exception:
                pass
            transactions = query_transactions(conn)

            # Per-class analytics
            per_class = {}
            asset_classes = [r[0] for r in conn.execute(
                "SELECT DISTINCT asset_class FROM transactions"
            ).fetchall()]
            for ac in asset_classes:
                try:
                    per_class[ac] = compute_analytics(conn, scope=ac)
                except Exception:
                    pass

            html = generate_html_report(analytics, tax, transactions, per_class=per_class)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"Error generating report: {e}".encode("utf-8"))
        finally:
            conn.close()

    def _json_response(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_server(host="127.0.0.1", port=8080, verbose=False):
    """Start the upload web server."""
    UploadHandler.verbose = verbose
    server = HTTPServer((host, port), UploadHandler)
    url = f"http://{host}:{port}"
    print(f"Upload server running at {url}")
    print("Press Ctrl+C to stop.")

    import webbrowser
    webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


# ---------------------------------------------------------------------------
# Self-contained HTML upload page
# ---------------------------------------------------------------------------
_UPLOAD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Revolut eDavki — Import</title>
<style>
:root {
  --bg: #f5f6fa; --card: #fff; --text: #1a1a2e; --muted: #6b7280;
  --border: #e5e7eb; --blue: #4285f4; --green: #16a34a; --red: #dc2626;
  --hover: #f9fafb;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f172a; --card: #1e293b; --text: #e2e8f0; --muted: #94a3b8;
    --border: #334155; --hover: #293548;
  }
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.5;
  min-height: 100vh; display: flex; flex-direction: column; align-items: center;
}
header {
  width: 100%; background: var(--card); border-bottom: 1px solid var(--border);
  padding: 1.5rem 2rem; text-align: center;
}
header h1 { font-size: 1.5rem; font-weight: 700; }
.subtitle { color: var(--muted); font-size: 0.875rem; margin-top: 0.25rem; }
main { max-width: 700px; width: 100%; padding: 2rem 1rem; display: flex; flex-direction: column; gap: 1.5rem; }
.card {
  background: var(--card); border: 1px solid var(--border); border-radius: 10px;
  padding: 1.5rem;
}
.card h2 { font-size: 1.1rem; margin-bottom: 1rem; }
.form-group { margin-bottom: 1rem; }
.form-group label { display: block; font-size: 0.85rem; font-weight: 600; color: var(--muted); margin-bottom: 0.35rem; text-transform: uppercase; letter-spacing: 0.05em; }
select, input[type="file"] {
  width: 100%; padding: 0.5rem 0.75rem; border: 1px solid var(--border); border-radius: 6px;
  background: var(--bg); color: var(--text); font-size: 0.9rem;
}
select { cursor: pointer; appearance: auto; }

.drop-zone {
  border: 2px dashed var(--border); border-radius: 10px; padding: 2.5rem 1.5rem;
  text-align: center; cursor: pointer; transition: all 0.15s ease;
  position: relative;
}
.drop-zone:hover, .drop-zone.dragover { border-color: var(--blue); background: rgba(66,133,244,0.04); }
.drop-zone .icon { font-size: 2.5rem; margin-bottom: 0.5rem; }
.drop-zone .label { font-size: 0.95rem; color: var(--muted); }
.drop-zone .label strong { color: var(--blue); }
.drop-zone .hint { font-size: 0.75rem; color: var(--muted); margin-top: 0.35rem; }
.drop-zone input[type="file"] { position: absolute; inset: 0; opacity: 0; cursor: pointer; }

.file-list { margin-top: 0.75rem; display: flex; flex-direction: column; gap: 0.35rem; }
.file-item {
  display: flex; align-items: center; gap: 0.5rem; padding: 0.4rem 0.75rem;
  background: var(--bg); border-radius: 6px; font-size: 0.85rem;
}
.file-item .name { flex: 1; font-weight: 500; }
.file-item .size { color: var(--muted); font-size: 0.8rem; }
.file-item .remove { cursor: pointer; color: var(--red); font-weight: 700; padding: 0 0.25rem; border: none; background: none; font-size: 1rem; }

.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 0.5rem;
  padding: 0.6rem 1.5rem; border-radius: 8px; font-size: 0.9rem; font-weight: 600;
  cursor: pointer; border: none; transition: all 0.15s ease;
}
.btn-primary { background: var(--blue); color: #fff; }
.btn-primary:hover { opacity: 0.9; }
.btn-primary:disabled { opacity: 0.4; cursor: default; }
.btn-secondary { background: var(--bg); color: var(--text); border: 1px solid var(--border); }
.btn-secondary:hover { background: var(--hover); }
.btn-group { display: flex; gap: 0.75rem; margin-top: 1rem; flex-wrap: wrap; }

.progress { display: none; margin-top: 1rem; }
.progress.active { display: block; }
.progress-bar {
  height: 4px; background: var(--border); border-radius: 4px; overflow: hidden;
}
.progress-bar .fill { height: 100%; background: var(--blue); transition: width 0.3s ease; border-radius: 4px; }
.progress-label { font-size: 0.8rem; color: var(--muted); margin-top: 0.35rem; }

.results { margin-top: 1rem; display: none; }
.results.active { display: block; }
.result-item {
  display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem;
  border-bottom: 1px solid var(--border); font-size: 0.85rem;
}
.result-item:last-child { border-bottom: none; }
.result-item .status { font-size: 1.2rem; }
.result-item .info { flex: 1; }
.result-item .info .filename { font-weight: 600; }
.result-item .info .detail { color: var(--muted); font-size: 0.8rem; }
.result-item .info .error { color: var(--red); font-size: 0.8rem; }

.status-bar {
  background: var(--card); border: 1px solid var(--border); border-radius: 10px;
  padding: 1rem 1.25rem; display: flex; align-items: center; gap: 1.25rem;
  flex-wrap: wrap; font-size: 0.85rem;
}
.status-item { display: flex; align-items: center; gap: 0.35rem; }
.status-item .num { font-weight: 700; }
.status-item .lbl { color: var(--muted); }

.actions { display: none; }
.actions.active { display: flex; gap: 0.75rem; flex-wrap: wrap; margin-top: 1rem; }
</style>
</head>
<body>

<header>
  <h1>Revolut eDavki — Import</h1>
  <p class="subtitle">Upload Revolut CSV exports to import into the portfolio database</p>
</header>

<main>
  <div id="statusBar" class="status-bar" style="display:none"></div>

  <div class="card">
    <h2>Upload CSV Files</h2>

    <div class="drop-zone" id="dropZone">
      <div class="icon">&#128196;</div>
      <div class="label">Drop files here or <strong>browse</strong></div>
      <div class="hint">CSV or Excel — stocks, CFD, crypto, or savings (auto-detected)</div>
      <input type="file" id="fileInput" accept=".csv,.xlsx,.xls" multiple>
    </div>

    <div id="fileList" class="file-list"></div>

    <div class="btn-group">
      <button class="btn btn-primary" id="uploadBtn" disabled>Upload &amp; Import</button>
    </div>

    <div class="progress" id="progress">
      <div class="progress-bar"><div class="fill" id="progressFill" style="width:0%"></div></div>
      <div class="progress-label" id="progressLabel">Importing...</div>
    </div>

    <div class="results" id="results"></div>

    <div class="actions" id="actions">
      <button class="btn btn-secondary" id="syncBtn">Sync Prices</button>
      <a class="btn btn-primary" href="/report" target="_blank">View Report</a>
      <button class="btn btn-secondary" id="resetBtn">Import More</button>
    </div>
  </div>
</main>

<script>
(function() {
  const fileInput = document.getElementById('fileInput');
  const dropZone = document.getElementById('dropZone');
  const fileList = document.getElementById('fileList');
  const uploadBtn = document.getElementById('uploadBtn');
  const progress = document.getElementById('progress');
  const progressFill = document.getElementById('progressFill');
  const progressLabel = document.getElementById('progressLabel');
  const resultsEl = document.getElementById('results');
  const actionsEl = document.getElementById('actions');
  const statusBar = document.getElementById('statusBar');
  const syncBtn = document.getElementById('syncBtn');
  const resetBtn = document.getElementById('resetBtn');

  let selectedFiles = [];

  // --- Load status on page load ---
  fetch('/status').then(r=>r.json()).then(data => {
    if (data.has_data) {
      const items = [];
      items.push(`<span class="num">${data.transaction_count}</span> <span class="lbl">transactions</span>`);
      items.push(`<span class="num">${data.ticker_count}</span> <span class="lbl">tickers</span>`);
      if (data.date_range) items.push(`<span class="lbl">${data.date_range[0]} to ${data.date_range[1]}</span>`);
      if (data.asset_classes) {
        const tags = Object.entries(data.asset_classes).map(([k,v]) => `${k}: ${v}`).join(', ');
        items.push(`<span class="lbl">${tags}</span>`);
      }
      statusBar.innerHTML = items.map(i => `<div class="status-item">${i}</div>`).join('');
      statusBar.style.display = '';
    }
  }).catch(()=>{});

  // --- Drag and drop ---
  dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
  dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    addFiles(e.dataTransfer.files);
  });
  fileInput.addEventListener('change', () => { addFiles(fileInput.files); fileInput.value = ''; });

  function addFiles(fileListObj) {
    for (const f of fileListObj) {
      const ext = f.name.split('.').pop().toLowerCase();
      if (!['csv','xlsx','xls'].includes(ext)) continue;
      if (selectedFiles.some(sf => sf.name === f.name && sf.size === f.size)) continue;
      selectedFiles.push(f);
    }
    renderFileList();
  }

  function renderFileList() {
    uploadBtn.disabled = selectedFiles.length === 0;
    fileList.innerHTML = selectedFiles.map((f, i) => {
      const size = f.size < 1024 ? f.size + ' B'
        : f.size < 1024*1024 ? (f.size/1024).toFixed(1) + ' KB'
        : (f.size/1024/1024).toFixed(1) + ' MB';
      return `<div class="file-item">
        <span class="name">${esc(f.name)}</span>
        <span class="size">${size}</span>
        <button class="remove" data-idx="${i}">&times;</button>
      </div>`;
    }).join('');
    fileList.querySelectorAll('.remove').forEach(btn => {
      btn.addEventListener('click', () => {
        selectedFiles.splice(parseInt(btn.dataset.idx), 1);
        renderFileList();
      });
    });
  }

  function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

  // --- Upload ---
  uploadBtn.addEventListener('click', async () => {
    if (selectedFiles.length === 0) return;
    uploadBtn.disabled = true;
    progress.classList.add('active');
    resultsEl.classList.remove('active');
    actionsEl.classList.remove('active');
    progressFill.style.width = '30%';
    progressLabel.textContent = 'Uploading ' + selectedFiles.length + ' file(s)...';

    const form = new FormData();
    selectedFiles.forEach(f => form.append('files', f));

    try {
      progressFill.style.width = '60%';
      progressLabel.textContent = 'Importing...';
      const resp = await fetch('/upload', { method: 'POST', body: form });
      const data = await resp.json();
      progressFill.style.width = '100%';

      if (data.error) {
        progressLabel.textContent = 'Error: ' + data.error;
        uploadBtn.disabled = false;
        return;
      }

      progressLabel.textContent = 'Done!';
      // Show results
      resultsEl.innerHTML = data.results.map(r => {
        if (r.error) {
          return `<div class="result-item">
            <span class="status">&#10060;</span>
            <div class="info"><div class="filename">${esc(r.filename)}</div><div class="error">${esc(r.error)}</div></div>
          </div>`;
        }
        const icon = r.new > 0 ? '&#9989;' : '&#9898;';
        return `<div class="result-item">
          <span class="status">${icon}</span>
          <div class="info">
            <div class="filename">${esc(r.filename)}</div>
            <div class="detail">${r.new} new, ${r.skipped} skipped (of ${r.total} rows)</div>
          </div>
        </div>`;
      }).join('');
      resultsEl.classList.add('active');
      actionsEl.classList.add('active');
      selectedFiles = [];
      renderFileList();

      // Refresh status bar
      fetch('/status').then(r=>r.json()).then(st => {
        if (st.has_data) {
          const items = [];
          items.push(`<span class="num">${st.transaction_count}</span> <span class="lbl">transactions</span>`);
          items.push(`<span class="num">${st.ticker_count}</span> <span class="lbl">tickers</span>`);
          if (st.date_range) items.push(`<span class="lbl">${st.date_range[0]} to ${st.date_range[1]}</span>`);
          statusBar.innerHTML = items.map(i => `<div class="status-item">${i}</div>`).join('');
          statusBar.style.display = '';
        }
      }).catch(()=>{});

    } catch (e) {
      progressFill.style.width = '100%';
      progressLabel.textContent = 'Error: ' + e.message;
      uploadBtn.disabled = false;
    }
  });

  // --- Sync ---
  syncBtn.addEventListener('click', async () => {
    syncBtn.disabled = true;
    syncBtn.textContent = 'Syncing...';
    try {
      const resp = await fetch('/sync', { method: 'POST' });
      const data = await resp.json();
      syncBtn.textContent = data.ok ? 'Synced!' : 'Error: ' + data.error;
    } catch (e) {
      syncBtn.textContent = 'Error';
    }
    setTimeout(() => { syncBtn.textContent = 'Sync Prices'; syncBtn.disabled = false; }, 3000);
  });

  // --- Reset ---
  resetBtn.addEventListener('click', () => {
    resultsEl.classList.remove('active');
    actionsEl.classList.remove('active');
    progress.classList.remove('active');
    progressFill.style.width = '0%';
    uploadBtn.disabled = true;
  });
})();
</script>
</body>
</html>
"""
