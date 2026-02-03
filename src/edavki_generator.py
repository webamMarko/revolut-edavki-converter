"""Generator for eDavki XML import format."""

from lxml import etree
from typing import List
from datetime import datetime
from .revolut_parser import RevolutTransaction


class EDavkiGenerator:
    """Generator for eDavki-compliant XML files."""
    
    def __init__(self):
        """Initialize the generator."""
        self.root = None
    
    def generate_xml(self, transactions: List[RevolutTransaction], tax_year: int) -> etree.Element:
        """
        Generate eDavki XML from Revolut transactions.
        
        Args:
            transactions: List of Revolut transactions
            tax_year: Tax year for the report
            
        Returns:
            XML element tree
        """
        # Create root element with namespace
        self.root = etree.Element("Envelope", nsmap={
            None: "http://edavki.durs.si/Documents/Schemas/Doh_KDVP_9.xsd"
        })
        
        # Add header
        header = etree.SubElement(self.root, "Header")
        etree.SubElement(header, "taxpayer_id")  # To be filled by user
        etree.SubElement(header, "tax_year").text = str(tax_year)
        etree.SubElement(header, "report_type").text = "KDVP"
        
        # Add body
        body = etree.SubElement(self.root, "Body")
        kdvp = etree.SubElement(body, "KDVP")
        
        # Add each transaction
        for idx, transaction in enumerate(transactions, start=1):
            self._add_transaction(kdvp, transaction, idx)
        
        return self.root
    
    def _add_transaction(self, parent: etree.Element, transaction: RevolutTransaction, index: int):
        """Add a single transaction to the XML."""
        item = etree.SubElement(parent, "Item")
        etree.SubElement(item, "ItemID").text = str(index)
        
        # Transaction date
        if transaction.completed_date:
            date_str = transaction.completed_date.strftime("%Y-%m-%d")
            etree.SubElement(item, "Date").text = date_str
        
        # Description
        etree.SubElement(item, "Description").text = transaction.description or ""
        
        # Amount
        etree.SubElement(item, "Amount").text = f"{transaction.amount:.2f}"
        
        # Currency
        etree.SubElement(item, "Currency").text = transaction.currency
        
        # Transaction type
        etree.SubElement(item, "Type").text = transaction.type
        
        # Fee (if applicable)
        if transaction.fee != 0:
            etree.SubElement(item, "Fee").text = f"{transaction.fee:.2f}"
    
    def save_to_file(self, file_path: str, pretty_print: bool = True):
        """
        Save the generated XML to a file.
        
        Args:
            file_path: Path to save the XML file
            pretty_print: Whether to format the XML with indentation
        """
        if self.root is None:
            raise ValueError("No XML generated yet. Call generate_xml() first.")
        
        tree = etree.ElementTree(self.root)
        tree.write(
            file_path,
            pretty_print=pretty_print,
            xml_declaration=True,
            encoding='UTF-8'
        )
    
    def to_string(self, pretty_print: bool = True) -> str:
        """
        Convert the XML to a string.
        
        Args:
            pretty_print: Whether to format the XML with indentation
            
        Returns:
            XML as a string
        """
        if self.root is None:
            raise ValueError("No XML generated yet. Call generate_xml() first.")
        
        return etree.tostring(
            self.root,
            pretty_print=pretty_print,
            xml_declaration=True,
            encoding='UTF-8'
        ).decode('utf-8')
