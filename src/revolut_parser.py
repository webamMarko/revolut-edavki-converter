"""Parser for Revolut transaction exports."""

import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path
from collections import defaultdict
import re


class RevolutTransaction:
    """Represents a single Revolut transaction."""
    
    def __init__(self, row: pd.Series):
        """Initialize transaction from a pandas Series."""
        # Handle both old and new Revolut export formats
        self.type = row.get('Type', '')
        self.product = row.get('Product', '')
        self.started_date = self._parse_date(row.get('Started Date', ''))
        self.completed_date = self._parse_date(row.get('Completed Date', '') or row.get('Date', ''))
        self.description = row.get('Description', '')
        self.amount = self._parse_amount(row.get('Amount', 0) or row.get('Total Amount', 0))
        self.fee = self._parse_amount(row.get('Fee', 0))
        self.currency = row.get('Currency', '')
        self.state = row.get('State', 'COMPLETED')  # New format doesn't have State
        self.balance = self._parse_amount(row.get('Balance', 0))
        
        # Stock-specific fields (new format)
        self.ticker = row.get('Ticker', '')
        self.quantity = self._parse_amount(row.get('Quantity', 0))
        self.price_per_share = self._parse_amount(row.get('Price per share', 0))
        self.fx_rate = self._parse_amount(row.get('FX Rate', 1.0))
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string to datetime object."""
        if pd.isna(date_str) or not date_str:
            return None
        try:
            return pd.to_datetime(date_str)
        except:
            return None
    
    def _parse_amount(self, amount) -> float:
        """Parse amount to float."""
        if pd.isna(amount):
            return 0.0
        try:
            # Handle amounts like "USD 32" or "32"
            if isinstance(amount, str):
                # Remove currency prefix
                amount = re.sub(r'^[A-Z]{3}\s+', '', amount)
            return float(amount)
        except:
            return 0.0
    
    def is_stock_transaction(self) -> bool:
        """Check if this is a stock buy/sell/split transaction."""
        return bool(self.ticker and ('BUY' in self.type or 'SELL' in self.type or 'STOCK SPLIT' in self.type))
    
    def is_buy(self) -> bool:
        """Check if this is a buy transaction."""
        return 'BUY' in self.type
    
    def is_sell(self) -> bool:
        """Check if this is a sell transaction."""
        return 'SELL' in self.type
    
    def is_stock_split(self) -> bool:
        """Check if this is a stock split."""
        return 'STOCK SPLIT' in self.type
    
    def to_dict(self) -> Dict:
        """Convert transaction to dictionary."""
        return {
            'type': self.type,
            'product': self.product,
            'started_date': self.started_date,
            'completed_date': self.completed_date,
            'description': self.description,
            'amount': self.amount,
            'fee': self.fee,
            'currency': self.currency,
            'state': self.state,
            'balance': self.balance,
            'ticker': self.ticker,
            'quantity': self.quantity,
            'price_per_share': self.price_per_share,
            'fx_rate': self.fx_rate
        }


class RevolutParser:
    """Parser for Revolut transaction export files."""
    
    def __init__(self, file_path: str):
        """Initialize parser with file path."""
        self.file_path = Path(file_path)
        self.transactions: List[RevolutTransaction] = []
    
    def parse(self) -> List[RevolutTransaction]:
        """Parse the Revolut export file."""
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")
        
        # Determine file type and parse accordingly
        if self.file_path.suffix.lower() == '.csv':
            df = pd.read_csv(self.file_path)
        elif self.file_path.suffix.lower() in ['.xlsx', '.xls']:
            df = pd.read_excel(self.file_path)
        else:
            raise ValueError(f"Unsupported file format: {self.file_path.suffix}")
        
        # Parse each row into a transaction
        self.transactions = [RevolutTransaction(row) for _, row in df.iterrows()]
        
        return self.transactions
    
    def filter_completed(self) -> List[RevolutTransaction]:
        """Return only completed transactions."""
        return [t for t in self.transactions if t.state == 'COMPLETED']
    
    def filter_by_date_range(self, start_date: datetime, end_date: datetime) -> List[RevolutTransaction]:
        """Filter transactions by date range."""
        return [
            t for t in self.transactions
            if t.completed_date and start_date <= t.completed_date <= end_date
        ]
    
    def filter_by_currency(self, currency: str) -> List[RevolutTransaction]:
        """Filter transactions by currency."""
        return [t for t in self.transactions if t.currency == currency]
    
    def filter_stock_transactions(self) -> List[RevolutTransaction]:
        """Return only stock buy/sell transactions."""
        return [t for t in self.transactions if t.is_stock_transaction()]
    
    def group_by_ticker(self, transactions: List[RevolutTransaction] = None) -> Dict[str, List[RevolutTransaction]]:
        """Group transactions by ticker symbol."""
        if transactions is None:
            transactions = self.transactions
        
        grouped = defaultdict(list)
        for t in transactions:
            if t.ticker:
                grouped[t.ticker].append(t)
        return dict(grouped)
