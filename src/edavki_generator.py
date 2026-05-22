"""Generator for eDavki XML import format."""

from __future__ import annotations

from lxml import etree
from typing import List, Dict
from collections import defaultdict
from .revolut_parser import RevolutTransaction


class EDavkiGenerator:
    """Generator for eDavki-compliant XML files."""

    # Namespace definitions
    NSMAP = {
        None: "http://edavki.durs.si/Documents/Schemas/Doh_KDVP_9.xsd",
        'edp': "http://edavki.durs.si/Documents/Schemas/EDP-Common-1.xsd"
    }

    def __init__(self):
        """Initialize the generator."""
        self.root = None
        self.securities_by_ticker = {}

    def generate_xml(self, transactions: List[RevolutTransaction], tax_year: int) -> etree.Element:
        """
        Generate eDavki XML from Revolut transactions.

        Args:
            transactions: List of Revolut transactions
            tax_year: Tax year for the report

        Returns:
            XML element tree
        """
        # Filter only stock transactions
        stock_transactions = [t for t in transactions if t.is_stock_transaction()]

        # Filter to only include securities with sales in tax_year and their related purchases (FIFO)
        stock_transactions = self._filter_by_sales_in_year_with_fifo(stock_transactions, tax_year)

        # Group by ticker
        self.securities_by_ticker = self._group_by_ticker(stock_transactions)

        # Create root Envelope element
        self.root = etree.Element("Envelope", nsmap=self.NSMAP)

        # Add Header (from EDP-Common)
        self._add_header()

        # Add Signatures (from EDP-Common)
        self._add_signatures()

        # Add body
        body = etree.SubElement(self.root, "body")

        # Add bodyContent (from EDP-Common)
        self._add_body_content(body)

        # Add Doh_KDVP
        doh_kdvp = etree.SubElement(body, "Doh_KDVP")

        # Add KDVP metadata section
        self._add_kdvp_metadata(doh_kdvp, tax_year)

        # Add KDVPItem elements for each security
        self._add_kdvp_items(doh_kdvp)

        return self.root

    def _filter_by_sales_in_year_with_fifo(self, transactions: List[RevolutTransaction], tax_year: int) -> List[RevolutTransaction]:
        """Filter to only include transactions related to sales in the specified year using FIFO."""
        # Group by ticker first
        by_ticker = defaultdict(list)
        for t in transactions:
            if t.ticker:
                by_ticker[t.ticker].append(t)

        result = []

        for ticker, ticker_transactions in by_ticker.items():
            # Sort by date
            sorted_transactions = sorted(ticker_transactions, key=lambda t: t.completed_date)

            # Filter out transactions after the tax year
            sorted_transactions = [t for t in sorted_transactions
                                  if t.completed_date and t.completed_date.year <= tax_year]

            # Check if this ticker has any sales in the tax year
            has_sales_in_year = any(t.is_sell() and t.completed_date and t.completed_date.year == tax_year
                                   for t in sorted_transactions)

            if not has_sales_in_year:
                continue

            # Apply FIFO: track purchases and match with sales
            purchases_queue = []  # (transaction, remaining_quantity)
            relevant_transactions = []
            current_quantity = 0.0  # Track total quantity for split ratio calculation

            for t in sorted_transactions:
                if t.is_buy():
                    # Add to queue
                    purchases_queue.append((t, t.quantity))
                    relevant_transactions.append(t)
                    current_quantity += t.quantity

                elif t.is_stock_split():
                    # Handle stock split
                    # The quantity represents the ABSOLUTE change in shares
                    # E.g., if you have 100 shares and get +300, that's a 4-for-1 split (ratio = 400/100 = 4)
                    # E.g., if you have 120.7 shares and get -119.7, that's a 1-for-120.7 split (ratio = 1/120.7)
                    if current_quantity > 0:
                        split_ratio = (current_quantity + t.quantity) / current_quantity
                    else:
                        split_ratio = 1.0

                    new_queue = []
                    for purchase, qty in purchases_queue:
                        new_queue.append((purchase, qty * split_ratio))
                    purchases_queue = new_queue
                    current_quantity = current_quantity * split_ratio
                    # Include split in relevant transactions so balance is calculated correctly
                    relevant_transactions.append(t)

                elif t.is_sell():
                    # Match with purchases using FIFO (always, regardless of year)
                    remaining_to_sell = t.quantity
                    temp_queue = []

                    for purchase, available_qty in purchases_queue:
                        if remaining_to_sell <= 0:
                            temp_queue.append((purchase, available_qty))
                        elif available_qty <= remaining_to_sell:
                            # This purchase is fully consumed
                            remaining_to_sell -= available_qty
                        else:
                            # Partial consumption
                            temp_queue.append((purchase, available_qty - remaining_to_sell))
                            remaining_to_sell = 0

                    purchases_queue = temp_queue
                    current_quantity -= t.quantity

                    # Include ALL sales for balance tracking, mark if they should be output
                    t._output_in_report = (t.completed_date and t.completed_date.year == tax_year)
                    relevant_transactions.append(t)

            # Find the last sale in the target year
            last_sale_in_year = None
            for t in reversed(relevant_transactions):
                if t.is_sell() and getattr(t, '_output_in_report', False):
                    last_sale_in_year = t
                    break

            if last_sale_in_year:
                # Remove all transactions after the last sale date
                last_sale_date = last_sale_in_year.completed_date
                cutoff_transactions = [t for t in relevant_transactions if t.completed_date <= last_sale_date]

                # Build split-aware FIFO lots up to cutoff
                # Key: track consumption in ORIGINAL (pre-split) terms to avoid split application bugs
                # Each lot tracks the cumulative split ratio from ALL splits AFTER it was purchased
                lots = []  # each: {'tx': buy_tx, 'base_qty': q_original, 'consumed_orig': 0.0, 'consumed_orig_in_year': 0.0, 'split_ratio': 1.0}

                for t in cutoff_transactions:
                    if t.is_buy():
                        lots.append({'tx': t, 'base_qty': t.quantity, 'consumed_orig': 0.0, 'consumed_orig_in_year': 0.0, 'split_ratio': 1.0, 'purchase_date': t.completed_date})
                    elif t.is_stock_split():
                        # Calculate current holdings in adjusted terms
                        held_adj = sum((lot['base_qty'] - lot['consumed_orig']) * lot['split_ratio'] for lot in lots)
                        if held_adj > 0:
                            r = (held_adj + t.quantity) / held_adj
                            # Update ONLY lots purchased BEFORE this split
                            for lot in lots:
                                if lot['purchase_date'] < t.completed_date:
                                    lot['split_ratio'] *= r
                    elif t.is_sell():
                        qty_to_consume_adj = t.quantity
                        # consume FIFO in original terms
                        for lot in lots:
                            if qty_to_consume_adj <= 1e-12:
                                break
                            # Available in original terms
                            avail_orig = lot['base_qty'] - lot['consumed_orig']
                            if avail_orig <= 1e-12:
                                continue
                            # Convert to adjusted terms
                            avail_adj = avail_orig * lot['split_ratio']
                            # Take what we can
                            take_adj = min(avail_adj, qty_to_consume_adj)
                            take_orig = take_adj / lot['split_ratio']

                            lot['consumed_orig'] += take_orig
                            if t.completed_date.year == tax_year:
                                lot['consumed_orig_in_year'] += take_orig
                            qty_to_consume_adj -= take_adj
                        # If qty_to_consume_adj remains due to data issues, it will reflect as negative balance later

                # Prepare final output transactions: only include buys that were consumed in target year, and target-year sells
                final_transactions = []
                for t in cutoff_transactions:
                    if t.is_buy():
                        # find its lot
                        lot = next((lot_item for lot_item in lots if lot_item['tx'] is t), None)
                        if lot and lot['consumed_orig_in_year'] > 1e-12:
                            # mark fields for output
                            t._include_in_output = True
                            t._quantity_output_orig = lot['consumed_orig_in_year']  # in original terms
                            t._split_ratio_final = lot['split_ratio']  # final cumulative ratio
                            final_transactions.append(t)
                    elif t.is_sell() and t.completed_date.year == tax_year:
                        final_transactions.append(t)
                    else:
                        # skip splits and non-target-year sells
                        pass

                # Sort final list chronologically
                final_transactions.sort(key=lambda x: x.completed_date)
                result.extend(final_transactions)
            else:
                result.extend(relevant_transactions)

        return result

    def _group_by_ticker(self, transactions: List[RevolutTransaction]) -> Dict[str, List[RevolutTransaction]]:
        """Group transactions by ticker."""
        grouped = defaultdict(list)
        for t in transactions:
            if t.ticker:
                grouped[t.ticker].append(t)
        return dict(grouped)

    def _add_header(self):
        """Add EDP Header element."""
        header = etree.SubElement(self.root, "{%s}Header" % self.NSMAP['edp'])
        # taxpayer element (empty - to be filled by user)
        etree.SubElement(header, "{%s}taxpayer" % self.NSMAP['edp'])

    def _add_signatures(self):
        """Add EDP Signatures element."""
        etree.SubElement(self.root, "{%s}Signatures" % self.NSMAP['edp'])

    def _add_body_content(self, body: etree.Element):
        """Add EDP bodyContent element."""
        etree.SubElement(body, "{%s}bodyContent" % self.NSMAP['edp'])

    def _add_kdvp_metadata(self, doh_kdvp: etree.Element, tax_year: int):
        """Add KDVP metadata section."""
        kdvp = etree.SubElement(doh_kdvp, "KDVP")

        # DocumentWorkflowID - required field for document type
        etree.SubElement(kdvp, "DocumentWorkflowID").text = "O"

        # Year
        etree.SubElement(kdvp, "Year").text = str(tax_year)

        # Period dates
        etree.SubElement(kdvp, "PeriodStart").text = f"{tax_year}-01-01"
        etree.SubElement(kdvp, "PeriodEnd").text = f"{tax_year}-12-31"

        # Resident
        etree.SubElement(kdvp, "IsResident").text = "true"

        # Counts - using Securities (PLVP) for full reporting
        etree.SubElement(kdvp, "SecurityCount").text = str(len(self.securities_by_ticker))
        etree.SubElement(kdvp, "SecurityShortCount").text = "0"
        etree.SubElement(kdvp, "SecurityWithContractCount").text = "0"
        etree.SubElement(kdvp, "SecurityWithContractShortCount").text = "0"
        etree.SubElement(kdvp, "ShareCount").text = "0"
        etree.SubElement(kdvp, "SecurityCapitalReductionCount").text = "0"

    def _add_kdvp_items(self, doh_kdvp: etree.Element):
        """Add KDVPItem elements for each security."""
        item_id = 1

        for ticker, transactions in sorted(self.securities_by_ticker.items()):
            kdvp_item = etree.SubElement(doh_kdvp, "KDVPItem")

            # ItemID
            etree.SubElement(kdvp_item, "ItemID").text = str(item_id)

            # InventoryListType - using PLVP (full form)
            etree.SubElement(kdvp_item, "InventoryListType").text = "PLVP"

            # Name
            etree.SubElement(kdvp_item, "Name").text = ticker

            # Foreign tax - set to false for now
            etree.SubElement(kdvp_item, "HasForeignTax").text = "false"

            # Add Securities element
            self._add_securities(kdvp_item, ticker, transactions)

            item_id += 1

    def _add_securities(self, kdvp_item: etree.Element, ticker: str, transactions: List[RevolutTransaction]):
        """Add Securities element with purchase/sale rows."""
        securities = etree.SubElement(kdvp_item, "Securities")

        # Code (ticker symbol) - max 10 characters
        ticker_code = ticker[:10] if len(ticker) > 10 else ticker
        etree.SubElement(securities, "Code").text = ticker_code

        # Name
        etree.SubElement(securities, "Name").text = ticker

        # IsFond - false for stocks
        etree.SubElement(securities, "IsFond").text = "false"

        # Calculate total split ratio by processing all splits that affected output transactions
        # We need to track quantity to calculate ratios correctly
        total_split_ratio = 1.0
        running_qty = 0.0
        for t in sorted(transactions, key=lambda x: x.completed_date):
            if t.is_buy():
                # Only include purchases that are in output
                if not getattr(t, '_include_in_output', False):
                    continue
                # Get the consumed quantity in original terms
                original_consumed = getattr(t, '_quantity_output_orig', t.quantity)
                running_qty += original_consumed
            elif t.is_sell():
                running_qty -= t.quantity
            elif t.is_stock_split():
                # Split ratio = (qty_before + qty_change) / qty_before
                if running_qty > 0:
                    split_ratio = (running_qty + t.quantity) / running_qty
                    total_split_ratio *= split_ratio
                    running_qty = running_qty + t.quantity
                else:
                    # No shares held, split doesn't affect anything
                    pass

        # Add rows for each transaction
        running_balance = 0.0
        row_id = 1

        for transaction in sorted(transactions, key=lambda t: t.completed_date):
            # For buys: only output if marked by FIFO logic
            if transaction.is_buy():
                if not getattr(transaction, '_include_in_output', False):
                    continue

                # Get consumed quantity in original terms and convert to split-adjusted for balance
                original_consumed = getattr(transaction, '_quantity_output_orig', transaction.quantity)
                lot_split_ratio = getattr(transaction, '_split_ratio_final', 1.0)
                adjusted_consumed = original_consumed * lot_split_ratio
                running_balance += adjusted_consumed

                row = etree.SubElement(securities, "Row")
                etree.SubElement(row, "ID").text = str(row_id)

                purchase = etree.SubElement(row, "Purchase")
                if transaction.completed_date:
                    etree.SubElement(purchase, "F1").text = transaction.completed_date.strftime("%Y-%m-%d")
                etree.SubElement(purchase, "F2").text = "B"

                # Get the lot-specific split ratio
                lot_split_ratio = getattr(transaction, '_split_ratio_final', 1.0)

                # F3: quantity in final split-adjusted terms
                adjusted_quantity = original_consumed * lot_split_ratio
                etree.SubElement(purchase, "F3").text = f"{adjusted_quantity:.8f}"

                # F4: price adjusted for splits and converted to EUR
                adjusted_price_usd = transaction.price_per_share / lot_split_ratio if lot_split_ratio > 0 else transaction.price_per_share
                # Convert USD to EUR using FX rate (EUR = USD / fx_rate)
                fx_rate = transaction.fx_rate if transaction.fx_rate > 0 else 1.0
                adjusted_price_eur = adjusted_price_usd / fx_rate
                etree.SubElement(purchase, "F4").text = f"{adjusted_price_eur:.8f}"

                etree.SubElement(row, "F8").text = f"{running_balance:.8f}"
                row_id += 1

            elif transaction.is_sell():
                running_balance -= transaction.quantity

                row = etree.SubElement(securities, "Row")
                etree.SubElement(row, "ID").text = str(row_id)

                sale = etree.SubElement(row, "Sale")
                if transaction.completed_date:
                    etree.SubElement(sale, "F6").text = transaction.completed_date.strftime("%Y-%m-%d")
                etree.SubElement(sale, "F7").text = f"{transaction.quantity:.8f}"
                # Convert sell price to EUR
                fx_rate = transaction.fx_rate if transaction.fx_rate > 0 else 1.0
                price_eur = transaction.price_per_share / fx_rate
                etree.SubElement(sale, "F9").text = f"{price_eur:.8f}"

                etree.SubElement(row, "F8").text = f"{running_balance:.8f}"
                row_id += 1

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
