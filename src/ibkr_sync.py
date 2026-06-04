"""IBKR Flex Query API integration for automated transaction import.

Uses the IBKR Flex Web Service to fetch Flex Query reports and import
them using the existing IbkrFlexAdapter parser.

Protocol (two-step):
  1. GET SendRequest?t={token}&q={queryId}&v=3 → returns ReferenceCode + Url
  2. GET {Url} → returns FlexQueryResponse XML (retry if Status=Processing)
"""

from __future__ import annotations

import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Optional

import requests
from lxml import etree

SEND_REQUEST_URL = (
    "https://ndcdyn.interactivebrokers.com"
    "/AccountManagement/FlexWebService/SendRequest"
)
MAX_RETRIES = 5
RETRY_DELAY = 5  # seconds between retries when report is still processing

# Keys in the portfolio.db metadata table
_KEY_TOKEN = "ibkr_flex_token"
_KEY_QUERY_ID = "ibkr_flex_query_id"
_KEY_LAST_SYNC = "ibkr_last_sync"
_KEY_LAST_ERROR = "ibkr_last_sync_error"


# ------------------------------------------------------------------
# Credential management (stored per-user in portfolio.db metadata)
# ------------------------------------------------------------------

def get_credentials(conn: sqlite3.Connection) -> tuple[str | None, str | None]:
    """Return (flex_token, query_id) from the metadata table, or (None, None)."""
    rows = conn.execute(
        "SELECT key, value FROM metadata WHERE key IN (?, ?)",
        (_KEY_TOKEN, _KEY_QUERY_ID),
    ).fetchall()
    creds = {r[0]: r[1] for r in rows}
    return creds.get(_KEY_TOKEN), creds.get(_KEY_QUERY_ID)


def save_credentials(conn: sqlite3.Connection, token: str, query_id: str) -> None:
    """Persist IBKR Flex credentials in the metadata table."""
    for key, value in ((_KEY_TOKEN, token), (_KEY_QUERY_ID, query_id)):
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            (key, value),
        )
    conn.commit()


def delete_credentials(conn: sqlite3.Connection) -> None:
    """Remove IBKR Flex credentials from the metadata table."""
    conn.execute(
        "DELETE FROM metadata WHERE key IN (?, ?, ?, ?)",
        (_KEY_TOKEN, _KEY_QUERY_ID, _KEY_LAST_SYNC, _KEY_LAST_ERROR),
    )
    conn.commit()


def get_sync_status(conn: sqlite3.Connection) -> dict:
    """Return current IBKR sync status for display in the settings page."""
    rows = conn.execute(
        "SELECT key, value FROM metadata WHERE key IN (?, ?, ?, ?)",
        (_KEY_TOKEN, _KEY_QUERY_ID, _KEY_LAST_SYNC, _KEY_LAST_ERROR),
    ).fetchall()
    meta = {r[0]: r[1] for r in rows}
    configured = bool(meta.get(_KEY_TOKEN) and meta.get(_KEY_QUERY_ID))
    return {
        "configured": configured,
        "query_id": meta.get(_KEY_QUERY_ID, ""),
        "last_sync": meta.get(_KEY_LAST_SYNC),
        "last_error": meta.get(_KEY_LAST_ERROR),
    }


# ------------------------------------------------------------------
# IBKR Flex Web Service client
# ------------------------------------------------------------------

class IbkrFlexError(Exception):
    """Raised when the IBKR Flex Web Service returns an error."""


def _send_request(token: str, query_id: str, timeout: int = 30) -> str:
    """Step 1: request report generation. Returns the polling URL."""
    resp = requests.get(
        SEND_REQUEST_URL,
        params={"t": token, "q": query_id, "v": "3"},
        timeout=timeout,
    )
    resp.raise_for_status()

    root = etree.fromstring(resp.content)
    status_el = root.find("Status")
    status = status_el.text.strip() if status_el is not None else ""

    if status != "Success":
        err_el = root.find("ErrorMessage")
        msg = err_el.text.strip() if err_el is not None else "Unknown error"
        raise IbkrFlexError(f"IBKR SendRequest failed: {msg}")

    url_el = root.find("Url")
    if url_el is None or not url_el.text:
        ref_el = root.find("ReferenceCode")
        ref = ref_el.text.strip() if ref_el is not None else ""
        raise IbkrFlexError(f"IBKR response missing Url (ref={ref})")

    return url_el.text.strip()


def _fetch_statement(url: str, timeout: int = 60) -> bytes:
    """Step 2: poll until the statement is ready, then return the XML bytes."""
    for attempt in range(MAX_RETRIES):
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()

        content = resp.content
        try:
            root = etree.fromstring(content)
        except etree.XMLSyntaxError:
            raise IbkrFlexError("IBKR returned non-XML response")

        local_tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag

        # FlexQueryResponse is the actual data
        if local_tag == "FlexQueryResponse":
            return content

        # FlexStatementResponse indicates pending or error
        status_el = root.find("Status")
        status = status_el.text.strip() if status_el is not None else ""

        if status == "Processing":
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            raise IbkrFlexError("IBKR report still processing after maximum retries")

        err_el = root.find("ErrorMessage")
        msg = err_el.text.strip() if err_el is not None else "Unknown error"
        raise IbkrFlexError(f"IBKR GetStatement failed: {msg}")

    raise IbkrFlexError("Max retries exceeded fetching IBKR statement")


# ------------------------------------------------------------------
# Import orchestration
# ------------------------------------------------------------------

def fetch_and_import(
    conn: sqlite3.Connection,
    token: str,
    query_id: str,
    portfolio_id: int = 1,
) -> dict:
    """Fetch the IBKR Flex report and import new transactions.

    Returns a dict with keys: rows_new, rows_skipped, rows_total, error (if any).
    """
    from .importer import import_csv

    try:
        poll_url = _send_request(token, query_id)
        xml_bytes = _fetch_statement(poll_url)
    except Exception as exc:
        return {"rows_new": 0, "rows_skipped": 0, "rows_total": 0, "error": str(exc)}

    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tf:
        tf.write(xml_bytes)
        tmp_path = tf.name

    try:
        result = import_csv(conn, tmp_path, portfolio_id=portfolio_id)
        return {
            "rows_new": result.new,
            "rows_skipped": result.skipped,
            "rows_total": result.total,
            "error": None,
        }
    except Exception as exc:
        return {"rows_new": 0, "rows_skipped": 0, "rows_total": 0, "error": str(exc)}
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def sync_ibkr(conn: sqlite3.Connection, portfolio_id: int = 1) -> dict:
    """High-level entry point: read stored credentials and run fetch_and_import.

    Persists last_sync / last_error in metadata for status display.
    Returns same dict as fetch_and_import.
    """
    from datetime import datetime, timezone

    token, query_id = get_credentials(conn)
    if not token or not query_id:
        return {
            "rows_new": 0,
            "rows_skipped": 0,
            "rows_total": 0,
            "error": "IBKR credentials not configured",
        }

    result = fetch_and_import(conn, token, query_id, portfolio_id=portfolio_id)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if result["error"]:
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            (_KEY_LAST_ERROR, f"{now}: {result['error']}"),
        )
    else:
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            (_KEY_LAST_SYNC, now),
        )
        conn.execute("DELETE FROM metadata WHERE key = ?", (_KEY_LAST_ERROR,))
    conn.commit()

    return result
