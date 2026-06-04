"""Unit tests for IBKR Flex API integration (src/ibkr_sync.py)."""

from __future__ import annotations

import sqlite3
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def db():
    """In-memory SQLite DB with the metadata table."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    return conn


# ------------------------------------------------------------------
# Credential management
# ------------------------------------------------------------------

class TestCredentials:
    def test_get_empty(self, db):
        from src.ibkr_sync import get_credentials
        token, qid = get_credentials(db)
        assert token is None
        assert qid is None

    def test_save_and_get(self, db):
        from src.ibkr_sync import save_credentials, get_credentials
        save_credentials(db, "tok123", "456")
        token, qid = get_credentials(db)
        assert token == "tok123"
        assert qid == "456"

    def test_overwrite(self, db):
        from src.ibkr_sync import save_credentials, get_credentials
        save_credentials(db, "old", "1")
        save_credentials(db, "new", "2")
        token, qid = get_credentials(db)
        assert token == "new"
        assert qid == "2"

    def test_delete(self, db):
        from src.ibkr_sync import save_credentials, delete_credentials, get_credentials
        save_credentials(db, "tok", "q")
        delete_credentials(db)
        token, qid = get_credentials(db)
        assert token is None
        assert qid is None

    def test_delete_clears_sync_status(self, db):
        from src.ibkr_sync import save_credentials, delete_credentials, get_sync_status
        save_credentials(db, "tok", "q")
        db.execute("INSERT OR REPLACE INTO metadata VALUES ('ibkr_last_sync', '2024-01-01')")
        db.commit()
        delete_credentials(db)
        status = get_sync_status(db)
        assert not status["configured"]
        assert status["last_sync"] is None


# ------------------------------------------------------------------
# get_sync_status
# ------------------------------------------------------------------

class TestSyncStatus:
    def test_unconfigured(self, db):
        from src.ibkr_sync import get_sync_status
        s = get_sync_status(db)
        assert s["configured"] is False
        assert s["query_id"] == ""
        assert s["last_sync"] is None
        assert s["last_error"] is None

    def test_configured(self, db):
        from src.ibkr_sync import save_credentials, get_sync_status
        save_credentials(db, "tok", "789")
        s = get_sync_status(db)
        assert s["configured"] is True
        assert s["query_id"] == "789"


# ------------------------------------------------------------------
# _send_request / _fetch_statement — mocked
# ------------------------------------------------------------------

FLEX_SEND_RESPONSE_OK = b"""
<FlexStatementResponse timestamp="20240101">
  <Status>Success</Status>
  <ReferenceCode>REF001</ReferenceCode>
  <Url>https://example.com/GetStatement?q=REF001&amp;v=3</Url>
</FlexStatementResponse>
"""

FLEX_SEND_RESPONSE_ERR = b"""
<FlexStatementResponse timestamp="20240101">
  <Status>Fail</Status>
  <ErrorMessage>Invalid token</ErrorMessage>
</FlexStatementResponse>
"""

FLEX_DATA_XML = b"""<?xml version="1.0"?>
<FlexQueryResponse queryName="Test" type="AF">
  <FlexStatements count="0">
  </FlexStatements>
</FlexQueryResponse>
"""

FLEX_PROCESSING = b"""
<FlexStatementResponse timestamp="20240101">
  <Status>Processing</Status>
</FlexStatementResponse>
"""


class TestSendRequest:
    def test_success_returns_url(self):
        from src.ibkr_sync import _send_request
        mock_resp = MagicMock()
        mock_resp.content = FLEX_SEND_RESPONSE_OK
        mock_resp.raise_for_status = MagicMock()
        with patch("src.ibkr_sync.requests.get", return_value=mock_resp):
            url = _send_request("tok", "123")
        assert url == "https://example.com/GetStatement?q=REF001&v=3"

    def test_error_raises(self):
        from src.ibkr_sync import _send_request, IbkrFlexError
        mock_resp = MagicMock()
        mock_resp.content = FLEX_SEND_RESPONSE_ERR
        mock_resp.raise_for_status = MagicMock()
        with patch("src.ibkr_sync.requests.get", return_value=mock_resp):
            with pytest.raises(IbkrFlexError, match="Invalid token"):
                _send_request("bad_tok", "123")


class TestFetchStatement:
    def test_returns_data_on_success(self):
        from src.ibkr_sync import _fetch_statement
        mock_resp = MagicMock()
        mock_resp.content = FLEX_DATA_XML
        mock_resp.raise_for_status = MagicMock()
        with patch("src.ibkr_sync.requests.get", return_value=mock_resp):
            result = _fetch_statement("https://example.com/stmt")
        assert b"FlexQueryResponse" in result

    def test_retries_on_processing(self):
        from src.ibkr_sync import _fetch_statement
        processing = MagicMock()
        processing.content = FLEX_PROCESSING
        processing.raise_for_status = MagicMock()
        data = MagicMock()
        data.content = FLEX_DATA_XML
        data.raise_for_status = MagicMock()
        with patch("src.ibkr_sync.requests.get", side_effect=[processing, data]):
            with patch("src.ibkr_sync.time.sleep"):
                result = _fetch_statement("https://example.com/stmt")
        assert b"FlexQueryResponse" in result

    def test_max_retries_raises(self):
        from src.ibkr_sync import _fetch_statement, IbkrFlexError, MAX_RETRIES
        mock_resp = MagicMock()
        mock_resp.content = FLEX_PROCESSING
        mock_resp.raise_for_status = MagicMock()
        with patch("src.ibkr_sync.requests.get", return_value=mock_resp):
            with patch("src.ibkr_sync.time.sleep"):
                with pytest.raises(IbkrFlexError, match="processing"):
                    _fetch_statement("https://example.com/stmt")


# ------------------------------------------------------------------
# sync_ibkr — no credentials path
# ------------------------------------------------------------------

class TestSyncIbkr:
    def test_no_credentials_returns_error(self, db):
        from src.ibkr_sync import sync_ibkr
        result = sync_ibkr(db)
        assert result["error"] is not None
        assert "not configured" in result["error"]

    def test_persists_error_in_metadata(self, db):
        from src.ibkr_sync import save_credentials, sync_ibkr
        save_credentials(db, "tok", "q")
        with patch("src.ibkr_sync._send_request", side_effect=Exception("network fail")):
            result = sync_ibkr(db)
        assert result["error"] is not None
        row = db.execute("SELECT value FROM metadata WHERE key='ibkr_last_sync_error'").fetchone()
        assert row is not None
        assert "network fail" in row[0]
