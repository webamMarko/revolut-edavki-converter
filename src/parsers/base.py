"""Base adapter interface and ParsedTrade data model for broker CSV/XML parsers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class UnknownFormatError(Exception):
    """Raised when no registered adapter can detect the file format."""


@dataclass
class ParsedTrade:
    """A single normalised transaction row from any broker's file.

    All amounts are stored in the original currency; importer converts to EUR
    using *fx_rate* at insert time.

    Mandatory fields
    ----------------
    date            – ISO-8601 string, at least YYYY-MM-DD (may include time)
    type            – BUY | SELL | DIVIDEND | SPLIT | MERGER_OUT | MERGER_IN |
                      SPINOFF_OUT | SPINOFF_IN | RIGHTS_ISSUE | FEE |
                      STAKING REWARD | LEARN REWARD | PAYMENT | RECEIVE |
                      STAKE | INTEREST PAID | SERVICE FEE | INTEREST REINVESTED
    currency        – 3-letter ISO 4217 code

    Optional fields default to None / 1.0 / empty where shown.
    """

    # Core required fields
    date: str
    type: str
    currency: str

    # Security identification
    ticker: str | None = None

    # Quantities and prices
    quantity: float | None = None
    price_per_share: float | None = None
    total_amount: float | None = None

    # FX conversion to EUR (1.0 means already in EUR)
    fx_rate: float = 1.0

    # Asset class (stock | cfd | crypto | savings)
    asset_class: str = "stock"

    # NEW fields (Phase 1)
    commission: float | None = None
    withholding_tax: float | None = None
    broker_source: str | None = None          # 'revolut', 'ibkr', 'ilirika', etc.
    correlation_id: str | None = None         # links MERGER_OUT + MERGER_IN pairs

    # Raw row from the source file (for debugging / audit)
    raw_row: dict[str, Any] = field(default_factory=dict)


class CsvAdapter(ABC):
    """Abstract base for CSV-format broker adapters."""

    @property
    @abstractmethod
    def broker_name(self) -> str:
        """Human-readable broker identifier, e.g. 'revolut_stock'."""

    @abstractmethod
    def detect(self, df) -> bool:  # df: pd.DataFrame
        """Return True if *df* (DataFrame of CSV headers+first rows) looks like
        this broker's format."""

    @abstractmethod
    def parse(self, file_path: str) -> list[ParsedTrade]:
        """Parse the file at *file_path* and return a list of ParsedTrade objects.

        Should return an empty list rather than raise if the file has no usable rows.
        """


class XmlAdapter(ABC):
    """Abstract base for XML-format broker adapters."""

    @property
    @abstractmethod
    def broker_name(self) -> str:
        """Human-readable broker identifier, e.g. 'ibkr_flex'."""

    @abstractmethod
    def detect(self, root_tag: str, namespaces: dict) -> bool:
        """Return True if the XML root tag / namespaces match this broker's schema."""

    @abstractmethod
    def parse(self, file_path: str) -> list[ParsedTrade]:
        """Parse the XML file at *file_path* and return a list of ParsedTrade objects."""
