"""BrokerRegistry: two-stage auto-detection and dispatch of broker adapters."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .base import CsvAdapter, UnknownFormatError, XmlAdapter, ParsedTrade


class BrokerRegistry:
    """Holds registered CSV and XML adapters and dispatches parse requests.

    Two-stage detection:
    1. File extension (.csv / .xlsx / .xls → CSV adapters; .xml → XML adapters)
    2. Content sniffing (adapter.detect() against headers or root element)
    """

    def __init__(self):
        self._csv_adapters: list[CsvAdapter] = []
        self._xml_adapters: list[XmlAdapter] = []

    def register(self, adapter: CsvAdapter | XmlAdapter) -> None:
        """Register an adapter instance."""
        if isinstance(adapter, CsvAdapter):
            self._csv_adapters.append(adapter)
        elif isinstance(adapter, XmlAdapter):
            self._xml_adapters.append(adapter)
        else:
            raise TypeError(f"Expected CsvAdapter or XmlAdapter, got {type(adapter)}")

    def detect_and_parse(self, file_path: str) -> list[ParsedTrade]:
        """Detect the file format and delegate to the matching adapter.

        Raises
        ------
        UnknownFormatError
            If no registered adapter can handle the file.
        FileNotFoundError
            If the file does not exist.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        suffix = path.suffix.lower()

        if suffix == ".xml":
            return self._parse_xml(file_path)
        elif suffix in (".csv", ".xlsx", ".xls"):
            return self._parse_csv(file_path)
        else:
            raise UnknownFormatError(
                f"Unsupported file extension '{suffix}'. Expected .csv, .xlsx, .xls, or .xml."
            )

    def _parse_csv(self, file_path: str) -> list[ParsedTrade]:
        """Read the CSV/Excel into a DataFrame and find a matching CSV adapter."""
        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix in (".xlsx", ".xls"):
            df = pd.read_excel(path)
        else:
            df = pd.read_csv(path)
            # Retry with semicolon separator if single-column (Ilirika format)
            if len(df.columns) == 1 or (len(df.columns) < 3 and ";" in df.columns[0]):
                df = pd.read_csv(path, sep=";")

        for adapter in self._csv_adapters:
            if adapter.detect(df):
                return adapter.parse(file_path)

        raise UnknownFormatError(
            f"No CSV adapter matched the format of '{path.name}'. "
            f"Columns: {list(df.columns)}"
        )

    def _parse_xml(self, file_path: str) -> list[ParsedTrade]:
        """Parse the XML root and find a matching XML adapter."""
        from xml.etree import ElementTree as ET

        try:
            tree = ET.parse(file_path)
        except ET.ParseError as exc:
            raise UnknownFormatError(f"Could not parse XML file '{file_path}': {exc}") from exc

        root = tree.getroot()
        root_tag = root.tag

        # Extract namespace map
        namespaces: dict[str, str] = {}
        if root_tag.startswith("{"):
            # Clark notation: {namespace}LocalName
            ns_end = root_tag.index("}")
            namespaces[""] = root_tag[1:ns_end]

        for adapter in self._xml_adapters:
            if adapter.detect(root_tag, namespaces):
                return adapter.parse(file_path)

        raise UnknownFormatError(
            f"No XML adapter matched root tag '{root_tag}' in '{file_path}'."
        )

    @property
    def csv_adapters(self) -> list[CsvAdapter]:
        return list(self._csv_adapters)

    @property
    def xml_adapters(self) -> list[XmlAdapter]:
        return list(self._xml_adapters)
