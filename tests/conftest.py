"""Shared test fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _no_paperclip_env(monkeypatch):
    """Prevent all tests from creating real Paperclip issues."""
    monkeypatch.delenv("PAPERCLIP_API_URL", raising=False)
    monkeypatch.delenv("PAPERCLIP_API_KEY", raising=False)
    monkeypatch.delenv("PAPERCLIP_COMPANY_ID", raising=False)
    monkeypatch.delenv("PAPERCLIP_AGENT_ID", raising=False)
