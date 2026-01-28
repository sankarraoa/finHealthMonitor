"""Summarization Agent - Extracts structured summaries from raw Xero data."""
import logging
import re
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, date
from dateutil import parser as date_parser

from app.agents.agents.world_state import WorldState, CashPosition, PayrollProfile, ARProfile, APProfile, BankHistoryProfile, JournalProfile

logger = logging.getLogger(__name__)


class SummarizationAgent:
    """Extracts structured summaries from raw Xero MCP data."""
    
    def __init__(self, world_state: WorldState):
        self.world_state = world_state
    
    def summarize_all(self, raw_data: Dict[str, Any]) -> WorldState:
        """
        Process all raw data and populate world state with structured summaries.
        
        Args:
            raw_data: Raw data from DataGatherer
            
        Returns:
            Updated WorldState
        """
        logger.info("Starting data summarization...")
        
        # Extract organization info
        self._summarize_organization(raw_data.get("organisation"))
        
        # Summarize each domain
        self._summarize_cash_position(raw_data)
        self._summarize_payroll_profile(raw_data)
        self._summarize_ar_profile(raw_data)
        self._summarize_ap_profile(raw_data)
        self._summarize_bank_history(raw_data)
        self._summarize_journal_profile(raw_data)
        
        # Store available detail slices
        self._store_available_slices(raw_data)
        
        logger.info("Data summarization complete")
        return self.world_state
    
    def _summarize_organization(self, org_data: Any):
        """Extract organization details."""
        if not org_data:
            return
        
        org_text = self._extract_text_from_content(org_data)
        if not org_text:
            return
        
        # Extract fields
        self.world_state.org_id = self._extract_field(org_text, "Organisation ID:") or "unknown"
        self.world_state.org_name = self._extract_field(org_text, "Name:") or "Unknown"
        self.world_state.base_currency = self._extract_field(org_text, "Base Currency:") or "USD"
        self.world_state.timezone = self._extract_field(org_text, "Timezone:") or ""
        self.world_state.as_of_date = datetime.now().isoformat()
    
    def _summarize_cash_position(self, raw_data: Dict[str, Any]):
        """Extract cash position from Balance Sheet and bank accounts."""
        cash_pos = self.world_state.cash_position
        
        # Extract from Balance Sheet
        balance_sheet = raw_data.get("balance_sheet")
        if balance_sheet:
            self._extract_bank_balances_from_balance_sheet(balance_sheet, cash_pos)
        
        # Extract from accounts list
        accounts = raw_data.get("accounts")
        if accounts:
            self._extract_bank_accounts_from_list(accounts, cash_pos)
        
        cash_pos.last_update = datetime.now().isoformat()
    
    def _extract_bank_balances_from_balance_sheet(self, balance_sheet: Any, cash_pos: CashPosition):
        """Extract bank balances from Balance Sheet report."""
        text = self._extract_text_from_content(balance_sheet)
        if not text:
            return
        
        # Try to parse JSON from balance sheet
        json_match = re.search(r'\[.*\]', text, re.DOTALL)
        if json_match:
            try:
                bs_data = json.loads(json_match.group(0))
                for section in bs_data:
                    if isinstance(section, dict) and section.get("title") == "Bank":
                        rows = section.get("rows", [])
                        for row in rows:
                            if isinstance(row, dict) and row.get("rowType") == "Row":
                                cells = row.get("cells", [])
                                if len(cells) >= 2:
                                    account_name = cells[0].get("value", "")
                                    balance_str = cells[1].get("value", "")
                                    try:
                                        balance = float(balance_str)
                                        cash_pos.bank_accounts.append({
                                            "name": account_name,
                                            "balance": balance,
                                            "currency": self.world_state.base_currency
                                        })
                                        cash_pos.current_cash += balance
                                    except (ValueError, TypeError):
                                        pass
            except (json.JSONDecodeError, KeyError) as e:
                logger.debug(f"Could not parse balance sheet JSON: {e}")
    
    def _extract_bank_accounts_from_list(self, accounts: Any, cash_pos: CashPosition):
        """Extract bank account details from accounts list."""
        text = self._extract_text_from_content(accounts)
        if not text:
            return
        
        lines = text.split("\n")
        current_account = {}
        for line in lines:
            if line.startswith("Account:"):
                if current_account.get("Type") in ["BANK", "CURRENT"]:
                    # Add to list if not already present
                    account_name = current_account.get("Name", "")
                    if not any(acc["name"] == account_name for acc in cash_pos.bank_accounts):
                        cash_pos.bank_accounts.append({
                            "name": account_name,
                            "code": current_account.get("Code", ""),
                            "balance": 0.0,  # Will be updated from balance sheet
                            "currency": self.world_state.base_currency
                        })
                current_account = {"Name": line.replace("Account:", "").strip()}
            elif "Code:" in line:
                current_account["Code"] = self._extract_field(line, "Code:")
            elif "Type:" in line:
                current_account["Type"] = self._extract_field(line, "Type:")
    
    def _summarize_payroll_profile(self, raw_data: Dict[str, Any]):
        """Extract payroll information."""
        payroll_info = raw_data.get("payroll_info")
        if payroll_info:
            profile = self.world_state.payroll_profile
            profile.cadence = payroll_info.get("cadence", "Unknown")
            profile.next_payroll_date = payroll_info.get("next_payroll_date")
            profile.expected_net_payroll = payroll_info.get("highest_amount", 0.0)
            profile.last_4_runs = payroll_info.get("last_4_payroll_entries", [])
            profile.total_entries_found = payroll_info.get("total_entries_found", 0)
            
            # Set confidence based on data quality
            if profile.total_entries_found >= 4:
                profile.confidence = "High"
            elif profile.total_entries_found >= 2:
                profile.confidence = "Medium"
            else:
                profile.confidence = "Low"
    
    def _summarize_ar_profile(self, raw_data: Dict[str, Any]):
        """Extract Accounts Receivable summary."""
        ar_profile = self.world_state.ar_profile
        
        # Extract from invoices
        invoices = raw_data.get("invoices", [])
        ar_invoices = []
        total_ar = 0.0
        
        next_payroll_date = None
        if self.world_state.payroll_profile.next_payroll_date:
            try:
                next_payroll_date = date_parser.parse(self.world_state.payroll_profile.next_payroll_date).date()
            except:
                pass
        
        for invoice_item in invoices:
            if isinstance(invoice_item, dict) and invoice_item.get("type") == "text":
                text = invoice_item.get("text", "")
                if "Type: ACCREC" in text and ("Status: AUTHORISED" in text or "Status: PARTPAID" in text):
                    # Extract invoice details
                    invoice_id = self._extract_field(text, "Invoice ID:")
                    contact = self._extract_field(text, "Contact:")
                    amount_due_str = self._extract_field(text, "Amount Due:")
                    due_date_str = self._extract_field(text, "Due Date:")
                    
                    try:
                        amount_due = float(amount_due_str) if amount_due_str else 0.0
                        total_ar += amount_due
                        
                        invoice_data = {
                            "invoice_id": invoice_id or "unknown",
                            "contact": contact or "Unknown",
                            "amount": amount_due,
                            "due_date": due_date_str or "Unknown"
                        }
                        
                        # Check if due before payroll
                        if next_payroll_date and due_date_str:
                            try:
                                due_date = date_parser.parse(due_date_str).date()
                                if due_date <= next_payroll_date:
                                    ar_profile.due_before_payroll += amount_due
                            except:
                                pass
                        
                        ar_invoices.append(invoice_data)
                    except (ValueError, TypeError):
                        pass
        
        ar_profile.total_ar = total_ar
        ar_profile.total_count = len(ar_invoices)
        ar_profile.largest_5 = sorted(ar_invoices, key=lambda x: x.get("amount", 0), reverse=True)[:5]
    
    def _summarize_ap_profile(self, raw_data: Dict[str, Any]):
        """Extract Accounts Payable summary."""
        ap_profile = self.world_state.ap_profile
        
        # Extract from invoices
        invoices = raw_data.get("invoices", [])
        ap_invoices = []
        total_ap = 0.0
        
        next_payroll_date = None
        if self.world_state.payroll_profile.next_payroll_date:
            try:
                next_payroll_date = date_parser.parse(self.world_state.payroll_profile.next_payroll_date).date()
            except:
                pass
        
        for invoice_item in invoices:
            if isinstance(invoice_item, dict) and invoice_item.get("type") == "text":
                text = invoice_item.get("text", "")
                if "Type: ACCPAY" in text and ("Status: AUTHORISED" in text or "Status: PARTPAID" in text):
                    # Extract invoice details
                    invoice_id = self._extract_field(text, "Invoice ID:")
                    contact = self._extract_field(text, "Contact:")
                    amount_due_str = self._extract_field(text, "Amount Due:")
                    due_date_str = self._extract_field(text, "Due Date:")
                    
                    try:
                        amount_due = float(amount_due_str) if amount_due_str else 0.0
                        total_ap += amount_due
                        
                        invoice_data = {
                            "invoice_id": invoice_id or "unknown",
                            "contact": contact or "Unknown",
                            "amount": amount_due,
                            "due_date": due_date_str or "Unknown"
                        }
                        
                        # Check if due before payroll
                        if next_payroll_date and due_date_str:
                            try:
                                due_date = date_parser.parse(due_date_str).date()
                                if due_date <= next_payroll_date:
                                    ap_profile.due_before_payroll += amount_due
                            except:
                                pass
                        
                        ap_invoices.append(invoice_data)
                    except (ValueError, TypeError):
                        pass
        
        ap_profile.total_ap = total_ap
        ap_profile.total_count = len(ap_invoices)
        ap_profile.largest_5 = sorted(ap_invoices, key=lambda x: x.get("amount", 0), reverse=True)[:5]
    
    def _summarize_bank_history(self, raw_data: Dict[str, Any]):
        """Extract bank transaction history summary (last 90 days)."""
        bank_history = self.world_state.bank_history
        transactions = raw_data.get("bank_transactions", [])
        
        cutoff_date = datetime.now() - timedelta(days=90)
        recent_transactions = []
        total_inflow = 0.0
        total_outflow = 0.0
        bank_fees = 0.0
        
        for tx_item in transactions:
            if isinstance(tx_item, dict) and tx_item.get("type") == "text":
                text = tx_item.get("text", "")
                
                # Extract transaction details
                date_str = self._extract_field(text, "Date:")
                total_str = self._extract_field(text, "Total:")
                description = self._extract_field(text, "Description:") or ""
                
                try:
                    if date_str:
                        tx_date = date_parser.parse(date_str)
                        if tx_date >= cutoff_date:
                            amount = float(total_str) if total_str else 0.0
                            
                            # Determine if inflow or outflow
                            if amount > 0:
                                total_inflow += amount
                            else:
                                total_outflow += abs(amount)
                            
                            # Check for bank fees
                            if "fee" in description.lower() or "Fee" in description:
                                bank_fees += abs(amount)
                            
                            recent_transactions.append({
                                "date": date_str,
                                "amount": amount,
                                "description": description
                            })
                except (ValueError, TypeError, Exception) as e:
                    logger.debug(f"Error parsing transaction: {e}")
                    continue
        
        bank_history.last_90_days_count = len(recent_transactions)
        bank_history.total_inflow = total_inflow
        bank_history.total_outflow = total_outflow
        bank_history.net_flow = total_inflow - total_outflow
        bank_history.average_daily_flow = bank_history.net_flow / 90 if bank_history.last_90_days_count > 0 else 0.0
        bank_history.bank_fees_total = bank_fees
        bank_history.largest_transactions = sorted(recent_transactions, key=lambda x: abs(x.get("amount", 0)), reverse=True)[:10]
        
        # Update data quality
        self.world_state.data_quality["bank_history_days"] = str(bank_history.last_90_days_count)
    
    def _summarize_journal_profile(self, raw_data: Dict[str, Any]):
        """Extract manual journal entries summary (POSTED only)."""
        journal_profile = self.world_state.journal_profile
        journals = raw_data.get("manual_journals", [])
        
        payroll_journals = []
        other_journals = 0
        posted_count = 0
        voided_count = 0
        
        for journal_item in journals:
            if isinstance(journal_item, dict) and journal_item.get("type") == "text":
                text = journal_item.get("text", "")
                status = self._extract_field(text, "Status:")
                
                if status == "POSTED":
                    posted_count += 1
                    # Check if payroll-related
                    description = self._extract_field(text, "Description:") or ""
                    if any(keyword in description.lower() for keyword in ["payroll", "wages", "salary", "bi-weekly"]):
                        journal_id = self._extract_field(text, "Manual Journal ID:")
                        date_str = self._extract_field(text, "Date:")
                        payroll_journals.append({
                            "journal_id": journal_id or "unknown",
                            "date": date_str or "Unknown",
                            "description": description
                        })
                    else:
                        other_journals += 1
                elif status == "VOIDED":
                    voided_count += 1
        
        journal_profile.payroll_journals = payroll_journals
        journal_profile.other_journals_count = other_journals
        journal_profile.total_posted = posted_count
        journal_profile.total_voided = voided_count
    
    def _store_available_slices(self, raw_data: Dict[str, Any]):
        """Store available detail slices for planner to request."""
        # Store full invoice lists for detail requests
        if raw_data.get("invoices"):
            self.world_state.available_detail_slices["invoices_ar"] = [
                item for item in raw_data["invoices"]
                if isinstance(item, dict) and item.get("type") == "text"
                and "Type: ACCREC" in item.get("text", "")
            ]
            self.world_state.available_detail_slices["invoices_ap"] = [
                item for item in raw_data["invoices"]
                if isinstance(item, dict) and item.get("type") == "text"
                and "Type: ACCPAY" in item.get("text", "")
            ]
        
        # Store bank transactions
        if raw_data.get("bank_transactions"):
            self.world_state.available_detail_slices["bank_transactions"] = raw_data["bank_transactions"]
        
        # Store manual journals
        if raw_data.get("manual_journals"):
            self.world_state.available_detail_slices["manual_journals"] = raw_data["manual_journals"]
    
    def _extract_text_from_content(self, content: Any) -> str:
        """Extract text from MCP content array."""
        if isinstance(content, list):
            texts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    texts.append(item.get("text", ""))
            return "\n".join(texts)
        elif isinstance(content, dict):
            if "content" in content:
                return self._extract_text_from_content(content["content"])
            elif "text" in content:
                return content["text"]
        elif isinstance(content, str):
            return content
        return str(content) if content else ""
    
    def _extract_field(self, text: str, field_name: str) -> Optional[str]:
        """Extract a field value from text."""
        if not text or not field_name:
            return None
        
        for line in text.split("\n"):
            if field_name in line:
                parts = line.split(field_name, 1)
                if len(parts) > 1:
                    value = parts[1].strip()
                    # Remove trailing separators
                    value = value.split("||")[0].strip() if "||" in value else value
                    return value if value else None
        return None
