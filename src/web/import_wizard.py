"""Import wizard: CSV preview, validation, and execution."""

import csv as _csv
import io as _io
import json
import os
import tempfile
import time

from .auth import get_session, get_session_token
from .portfolio import (portfolio_conn, _IMPORT_STAGING, purge_expired_staging,
                        cleanup_staging, detect_asset_class_from_headers)
from .templates import page_env, FOUC_SCRIPT, COMMON_JS, html_response, json_response, redirect


def serve_import_wizard(handler):
    """GET /import — import wizard page."""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        redirect(handler, "/login")
        return

    template = page_env.get_template("pages/import_wizard.html.j2")
    html = template.render(
        fouc_script=FOUC_SCRIPT,
        common_js=COMMON_JS,
        show_header=True,
        show_drop_import=False,
        username=session["username"],
        role=session["role"],
    )
    html_response(handler, html)


def handle_import_preview(handler):
    """POST /import/preview — preview CSV before import."""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        json_response(handler, {"error": "Login required."}, status=403)
        return

    content_length = int(handler.headers.get("Content-Length", 0))
    if content_length > 50 * 1024 * 1024:
        json_response(handler, {"error": "File too large (max 50 MB)."}, status=413)
        return

    body = handler._read_body(content_length)
    from ..server_utils import parse_multipart
    fields, files = parse_multipart(handler.headers, body)

    if not files:
        json_response(handler, {"error": "No file received."}, status=400)
        return

    f = files[0]
    filename = f["filename"]
    content = f["content"]

    # Reject binary
    if b"\x00" in content:
        json_response(handler, {"error": "Binary file rejected."}, status=400)
        return

    # Decode text
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except Exception:
            json_response(handler, {"error": "Could not decode file as text."}, status=400)
            return

    # CSV sniff
    lines = text.splitlines()
    if not lines:
        json_response(handler, {"error": "File is empty."}, status=400)
        return

    reader = _csv.reader(_io.StringIO(text))
    rows_raw = list(reader)
    if not rows_raw:
        json_response(handler, {"error": "File is empty."}, status=400)
        return

    headers = rows_raw[0]
    # Retry with semicolon if single column
    if len(headers) <= 1:
        reader2 = _csv.reader(_io.StringIO(text), delimiter=";")
        rows_raw2 = list(reader2)
        if rows_raw2 and len(rows_raw2[0]) > 1:
            rows_raw = rows_raw2
            headers = rows_raw[0]

    if len(headers) <= 1:
        json_response(handler, {"error": "Could not parse as CSV (comma or semicolon separated)."}, status=400)
        return

    preview_rows = [list(r) for r in rows_raw[1:6]]
    row_count = max(0, len(rows_raw) - 1)

    detected = detect_asset_class_from_headers(headers)

    # Stage the file
    token = get_session_token(handler)
    tmp_dir = tempfile.mkdtemp(prefix="revolut_import_")
    tmp_path = os.path.join(tmp_dir, filename)
    with open(tmp_path, "wb") as fh:
        fh.write(content)

    _IMPORT_STAGING[token] = {
        "path": tmp_path,
        "dir": tmp_dir,
        "filename": filename,
        "expires": time.time() + 3600,
    }
    purge_expired_staging()

    json_response(handler, {
        "headers": headers,
        "rows": preview_rows,
        "detected_asset_class": detected,
        "row_count": row_count,
        "filename": filename,
    })


def handle_import_validate(handler):
    """POST /import/validate — validate import mapping."""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        json_response(handler, {"error": "Login required."}, status=403)
        return

    body = handler._read_body()
    try:
        data = json.loads(body)
    except Exception:
        json_response(handler, {"error": "Invalid JSON."}, status=400)
        return

    asset_class = data.get("asset_class", "")
    column_map = data.get("mapping", {})

    if asset_class not in ("stock", "cfd", "crypto", "savings"):
        json_response(handler, {"error": "Invalid asset class."}, status=400)
        return

    token = get_session_token(handler)
    staging = _IMPORT_STAGING.get(token)
    if not staging or staging["expires"] < time.time():
        if staging:
            cleanup_staging(token)
        json_response(handler, {"error": "Upload session expired. Please re-upload the file."}, status=400)
        return

    import pandas as _pd
    from ..import_validator import validate_csv

    file_path = staging["path"]
    df = _pd.read_csv(file_path)
    if len(df.columns) == 1 or (len(df.columns) < 3 and ";" in df.columns[0]):
        df = _pd.read_csv(file_path, sep=";")

    # Get existing tickers from the user's portfolio for context
    existing_tickers = []
    try:
        conn = portfolio_conn(session, get_session_token(handler))
        rows = conn.execute("SELECT DISTINCT ticker FROM transactions WHERE ticker IS NOT NULL").fetchall()
        existing_tickers = [r[0] for r in rows]
        conn.close()
    except Exception:
        pass

    report = validate_csv(df, column_map, asset_class, existing_tickers)
    json_response(handler, report.to_dict())


def handle_import_run(handler):
    """POST /import/run — execute import."""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        json_response(handler, {"error": "Login required."}, status=403)
        return

    body = handler._read_body()
    try:
        data = json.loads(body)
    except Exception:
        json_response(handler, {"error": "Invalid JSON."}, status=400)
        return

    asset_class = data.get("asset_class", "")
    column_map = data.get("mapping", {})
    filename = data.get("filename", "")

    if asset_class not in ("stock", "cfd", "crypto", "savings"):
        json_response(handler, {"error": "Invalid asset class."}, status=400)
        return

    token = get_session_token(handler)
    staging = _IMPORT_STAGING.get(token)
    if not staging or staging["expires"] < time.time():
        if staging:
            cleanup_staging(token)
        json_response(handler, {"error": "Upload session expired. Please re-upload the file."}, status=400)
        return

    from ..importer import import_csv_mapped
    from ..analytics_cache import invalidate_cache
    from ..tax_cache import invalidate_current_year_tax
    from ..report_cache import invalidate_user_html
    conn = portfolio_conn(session, get_session_token(handler))
    try:
        result = import_csv_mapped(
            conn,
            staging["path"],
            asset_class=asset_class,
            column_map=column_map,
            filename_hint=filename or staging["filename"],
            verbose=handler.verbose,
        )
        invalidate_cache(conn)
        invalidate_current_year_tax(conn)
        invalidate_user_html(session["username"])
    except Exception as e:
        conn.close()
        json_response(handler, {"error": str(e)}, status=500)
        return
    finally:
        conn.close()

    cleanup_staging(token)
    json_response(handler, {
        "total": result.total,
        "new": result.new,
        "skipped": result.skipped,
    })
