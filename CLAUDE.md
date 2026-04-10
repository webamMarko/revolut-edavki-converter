# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Converts Revolut stock trading CSV/Excel exports into eDavki Doh_KDVP XML format for Slovenian capital gains tax reporting. Only stock transactions (BUY/SELL/STOCK SPLIT) are included in the XML output — non-stock transactions are filtered out.

## Commands

```bash
# Install dependencies (use venv)
pip install -r requirements.txt

# Run the converter
python -m src.cli input_file.csv output.xml --year 2023

# Run tests (not yet implemented)
python -m pytest tests/
```

## Architecture

The pipeline is: **CLI (`cli.py`) -> Parser (`revolut_parser.py`) -> Generator (`edavki_generator.py`) -> XML file**

### Key Concepts

- **RevolutTransaction** (`revolut_parser.py`): Data class wrapping a pandas Series row. Handles both old Revolut format (Type/Product/Started Date/State columns) and new format (Ticker/Quantity/Price per share/FX Rate columns). Amounts may have currency prefixes like "USD 32" that get stripped.

- **FIFO matching** (`edavki_generator.py:_filter_by_sales_in_year_with_fifo`): The most complex logic. For a given tax year, it finds securities with sales in that year, then walks the full transaction history to FIFO-match purchases to sales. Only purchases consumed by target-year sales appear in output. Tracks consumption in original (pre-split) terms using `_quantity_output_orig` and `_split_ratio_final` private attributes set directly on transaction objects.

- **Stock splits**: Handled by adjusting the split ratio on existing FIFO lots. The split transaction's `quantity` field is the absolute change in shares (e.g., +300 means you gained 300 additional shares). The ratio is calculated as `(held + change) / held`.

- **XML schema**: Follows `Doh_KDVP_9.xsd` with `EDP-Common-1.xsd` namespaces. Each ticker becomes a `KDVPItem` containing a `Securities` element with `Row` entries. Purchases use `F1`-`F4` fields, sales use `F6`/`F7`/`F9`. `F8` is running balance. All prices are converted from USD to EUR using the transaction's FX rate.

### Dependencies

- **pandas**: CSV/Excel parsing
- **lxml**: XML generation
- **openpyxl**: Excel file support
