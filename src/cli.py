#!/usr/bin/env python3
"""Command-line interface for Revolut to eDavki converter."""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from .revolut_parser import RevolutParser
from .edavki_generator import EDavkiGenerator


def parse_date(date_string: str) -> datetime:
    """Parse date string in YYYY-MM-DD format."""
    try:
        return datetime.strptime(date_string, "%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date format: {date_string}. Use YYYY-MM-DD")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Convert Revolut transaction exports to eDavki XML format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s transactions.csv output.xml --year 2023
  %(prog)s transactions.xlsx output.xml --year 2023 --start-date 2023-01-01 --end-date 2023-12-31
  %(prog)s transactions.csv output.xml --year 2023 --currency EUR
        """
    )
    
    parser.add_argument(
        "input_file",
        help="Path to Revolut export file (CSV or Excel)"
    )
    
    parser.add_argument(
        "output_file",
        help="Path to output eDavki XML file"
    )
    
    parser.add_argument(
        "--year",
        type=int,
        required=True,
        help="Tax year for the report"
    )
    
    parser.add_argument(
        "--start-date",
        type=parse_date,
        help="Filter transactions from this date (YYYY-MM-DD)"
    )
    
    parser.add_argument(
        "--end-date",
        type=parse_date,
        help="Filter transactions until this date (YYYY-MM-DD)"
    )
    
    parser.add_argument(
        "--currency",
        help="Filter transactions by currency (e.g., EUR, USD)"
    )
    
    parser.add_argument(
        "--completed-only",
        action="store_true",
        help="Include only completed transactions"
    )
    
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    try:
        # Parse Revolut file
        if args.verbose:
            print(f"Parsing Revolut file: {args.input_file}")
        
        revolut_parser = RevolutParser(args.input_file)
        transactions = revolut_parser.parse()
        
        if args.verbose:
            print(f"Parsed {len(transactions)} transactions")
        
        # Apply filters
        if args.completed_only:
            transactions = revolut_parser.filter_completed()
            if args.verbose:
                print(f"Filtered to {len(transactions)} completed transactions")
        
        if args.start_date and args.end_date:
            transactions = revolut_parser.filter_by_date_range(args.start_date, args.end_date)
            if args.verbose:
                print(f"Filtered to {len(transactions)} transactions in date range")
        
        if args.currency:
            transactions = revolut_parser.filter_by_currency(args.currency)
            if args.verbose:
                print(f"Filtered to {len(transactions)} transactions in {args.currency}")
        
        if not transactions:
            print("Warning: No transactions to export after filtering", file=sys.stderr)
            sys.exit(1)
        
        # Generate eDavki XML
        if args.verbose:
            print("Generating eDavki XML...")
        
        generator = EDavkiGenerator()
        generator.generate_xml(transactions, args.year)
        
        # Save to file
        generator.save_to_file(args.output_file)
        
        print(f"Successfully generated {args.output_file} with {len(transactions)} transactions")
        
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
