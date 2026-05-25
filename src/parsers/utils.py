"""Shared parsing utilities for all broker adapters.

Extracted from importer.py so every adapter can import a single source of truth.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pandas as pd


def _parse_amount(value) -> float | None:
    """Parse an amount string like 'USD 32' or '32' to float."""
    if pd.isna(value) or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    s = re.sub(r"^[A-Z]{3}\s+", "", s)
    try:
        return float(s)
    except ValueError:
        return None


def _parse_eur_amount(value) -> float | None:
    """Parse a currency amount like '€100.00', '$5.00', '€8,636.57' or '1.30 PLN' to float."""
    if pd.isna(value) or value == "":
        return None
    s = str(value).strip()
    # Remove currency prefix symbols (€, $, £, etc.)
    s = s.lstrip("€$£¥").strip()
    # Remove thousands separators
    s = s.replace(",", "")
    # Remove currency suffix like ' PLN'
    s = re.sub(r"\s+[A-Z]{2,4}$", "", s)
    try:
        return float(s)
    except ValueError:
        return None


def normalize_date(date_val) -> str | None:
    """Normalize any date value to YYYY-MM-DD.

    Handles:
    - 'YYYY-MM-DD'                     → returned as-is
    - 'YYYY-MM-DD HH:MM:SS'            → truncated to date part
    - 'YYYY-MM-DDTHH:MM:SS...'         → truncated to date part (ISO 8601)
    - 'Apr 1, 2026, 12:24:31 PM'       → parsed (localized Revolut format)
    - 'Apr 1, 2026, 0:22:14'           → parsed (localized, 24h variant)
    Returns None if the date cannot be parsed.
    """
    if not date_val:
        return None
    s = str(date_val).strip()
    # Fast path: already YYYY-MM-DD or starts with it (ISO timestamp or datetime)
    if len(s) >= 10 and s[4] == '-' and s[7] == '-':
        return s[:10]
    # Slow path: localized format
    result = _parse_crypto_date(s)
    return result[:10] if result else None


def _parse_crypto_date(date_str: str) -> str | None:
    """Parse crypto date format like 'Feb 21, 2020, 9:00:16 AM' to ISO format."""
    from datetime import datetime as dt
    if pd.isna(date_str) or not date_str:
        return None
    # Replace narrow no-break space (U+202F) used by newer Revolut exports before AM/PM
    s = str(date_str).strip().strip('"').replace(' ', ' ')
    for fmt in ("%b %d, %Y, %I:%M:%S %p", "%b %d, %Y, %H:%M:%S"):
        try:
            return dt.strptime(s, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return None


def _file_hash(file_path: str) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _row_hash_fields(date: str, ticker: str | None, tx_type: str,
                     quantity: float | None, total_amount: float | None,
                     currency: str) -> str:
    """Compute deterministic dedup hash for a parsed transaction row."""
    raw = f"{date}|{ticker}|{tx_type}|{quantity}|{total_amount}|{currency}"
    return hashlib.sha256(raw.encode()).hexdigest()
