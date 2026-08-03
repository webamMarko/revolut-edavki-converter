"""Valuation Workbench — page handler and FMP API proxy."""

import json
import os
import urllib.request
import urllib.parse
from urllib.parse import urlparse, parse_qs

from .auth import get_session
from .templates import page_env, FOUC_SCRIPT, COMMON_JS, html_response, json_response

FMP_API_KEY = os.environ.get("FMP_API_KEY", "")
FMP_BASE = "https://financialmodelingprep.com/api/v3"

# Allowed FMP endpoint prefixes (whitelist — only free-tier endpoints needed)
_ALLOWED_PATHS = (
    "profile/",
    "quote/",
    "historical-price-full/",
    "income-statement/",
    "balance-sheet-statement/",
    "cash-flow-statement/",
    "key-metrics/",
    "analyst-estimates/",
    "income-statement-as-reported/",
)


def serve_valuation_page(handler):
    """GET /valuation — render the Valuation Workbench page."""
    session = get_session(handler)
    username = session["username"] if session else None
    role = session["role"] if session else "guest"

    has_fmp_key = bool(FMP_API_KEY)

    template = page_env.get_template("pages/valuation.html.j2")
    html = template.render(
        fouc_script=FOUC_SCRIPT,
        common_js=COMMON_JS,
        show_header=True,
        show_drop_import=False,
        username=username,
        role=role,
        active_page="valuation",
        active_portfolio_name=None,
        has_fmp_key=has_fmp_key,
    )
    html_response(handler, html)


def api_fmp_proxy(handler):
    """GET /api/fmp — proxy FMP API calls, injecting server-side API key."""
    if not FMP_API_KEY:
        json_response(handler, {"error": "FMP_API_KEY not configured on this server."}, status=503)
        return

    parsed = urlparse(handler.path)
    params = parse_qs(parsed.query)

    fmp_path = params.get("path", [None])[0]
    if not fmp_path:
        json_response(handler, {"error": "Missing path parameter."}, status=400)
        return

    # Whitelist check
    if not any(fmp_path.startswith(p) for p in _ALLOWED_PATHS):
        json_response(handler, {"error": "Endpoint not permitted."}, status=403)
        return

    # Forward any extra query params (period, limit, from, to, serietype)
    forward_keys = ("period", "limit", "from", "to", "serietype", "datatype")
    extra = {}
    for k in forward_keys:
        if k in params:
            extra[k] = params[k][0]

    extra["apikey"] = FMP_API_KEY
    qs = urllib.parse.urlencode(extra)
    url = f"{FMP_BASE}/{fmp_path}?{qs}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WealthEagle/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raw = e.read()
        status = e.code
    except Exception as exc:
        json_response(handler, {"error": str(exc)}, status=502)
        return

    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    handler._add_security_headers()
    handler.end_headers()
    handler.wfile.write(raw)
