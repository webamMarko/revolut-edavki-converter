# Revolut to eDavki Converter

A Python tool to convert Revolut transaction exports (CSV/Excel) into eDavki-compliant XML format for Slovenian tax reporting.

## Features

- ✅ Parse Revolut CSV and Excel exports
- ✅ Generate eDavki XML format
- ✅ Filter transactions by date range
- ✅ Filter by currency
- ✅ Filter completed transactions only
- ✅ Command-line interface

## Installation

1. Clone the repository or download the source code
2. Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

```bash
python -m src.cli input_file.csv output.xml --year 2023
```

### With Filters

Filter by date range:
```bash
python -m src.cli transactions.csv output.xml --year 2023 \
  --start-date 2023-01-01 \
  --end-date 2023-12-31
```

Filter by currency:
```bash
python -m src.cli transactions.csv output.xml --year 2023 --currency EUR
```

Only completed transactions:
```bash
python -m src.cli transactions.csv output.xml --year 2023 --completed-only
```

Verbose output:
```bash
python -m src.cli transactions.csv output.xml --year 2023 -v
```

### Command-line Options

- `input_file` - Path to Revolut export file (CSV or Excel)
- `output_file` - Path to output eDavki XML file
- `--year` - Tax year for the report (required)
- `--start-date` - Filter transactions from this date (YYYY-MM-DD)
- `--end-date` - Filter transactions until this date (YYYY-MM-DD)
- `--currency` - Filter transactions by currency (e.g., EUR, USD)
- `--completed-only` - Include only completed transactions
- `--verbose, -v` - Verbose output

## Revolut Export Format

To export your Revolut transactions:

1. Open the Revolut app
2. Go to your account statements
3. Select the date range
4. Export as CSV or Excel

Expected columns in the export:
- Type
- Product
- Started Date
- Completed Date
- Description
- Amount
- Fee
- Currency
- State
- Balance

## eDavki XML Format

The generated XML follows the Slovenian eDavki tax reporting format. The XML includes:

- Transaction date
- Description
- Amount
- Currency
- Transaction type
- Fees (if applicable)

**Note:** You may need to manually adjust the generated XML to match your specific tax reporting requirements and eDavki schema version.

## Development

### Project Structure

```
revolut-edavki-converter/
├── src/
│   ├── __init__.py
│   ├── cli.py              # Command-line interface
│   ├── revolut_parser.py   # Revolut CSV/Excel parser
│   └── edavki_generator.py # eDavki XML generator
├── tests/                  # Unit tests (to be added)
├── examples/               # Example files
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

### Running Tests

```bash
# To be implemented
python -m pytest tests/
```

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

This project is provided as-is for personal use. Please ensure compliance with local tax regulations.

## Disclaimer

This tool is provided for convenience and may require adjustments to match your specific tax reporting needs. Always verify the generated XML against eDavki requirements before submission. Consult with a tax professional if needed.
