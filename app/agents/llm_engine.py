"""LLM Engine for Payroll Risk Analysis - Supports OpenAI and Toqan."""
import json
import logging
import re
import time
import requests
from typing import Dict, Any, Optional, Callable
from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime

from app.config import config
from app.agents.models import PayrollRiskResult, HealthStatus, DetectionTier, Scenario, Evidence

logger = logging.getLogger(__name__)

# Prompt storage directory
PROMPTS_DIR = Path("prompts/sent")
PROMPTS_DIR.mkdir(parents=True, exist_ok=True)


class BaseLLMEngine(ABC):
    """Base class for LLM engines."""
    
    def __init__(self):
        self.prompt_template = self._load_prompt_template()
    
    def _load_prompt_template(self) -> str:
        """Load the payroll risk prompt template."""
        import os
        # Try multiple possible paths
        possible_paths = [
            "prompts/payrollEarlyWarning.txt",
            "../prompts/payrollEarlyWarning.txt",
            os.path.join(os.path.dirname(__file__), "../../prompts/payrollEarlyWarning.txt"),
        ]
        
        for path in possible_paths:
            try:
                full_path = os.path.abspath(path)
                if os.path.exists(full_path):
                    with open(full_path, "r") as f:
                        content = f.read()
                        if content.strip():  # Check if file has content
                            logger.info(f"Loaded prompt from {full_path}")
                            return content
            except Exception as e:
                logger.debug(f"Could not load prompt from {path}: {str(e)}")
                continue
        
        logger.warning("Prompt file not found, using default prompt")
        return self._get_default_prompt()
    
    def _get_default_prompt(self) -> str:
        """Default prompt if file not found."""
        return """You are a financial risk analysis agent for US SMBs. Determine if projected cash will cover the next payroll, and explain risks and actions.

IMPORTANT: Many organizations use external payroll systems (ADP, Gusto, Paychex, etc.) and record payroll via manual journal entries rather than Xero Payroll. Manual journals with descriptions like "Bi-weekly Payroll", "Payroll", "Wages", "Salaries" are a VALID source of payroll data. Always check manual journals for payroll patterns even if Xero Payroll module is not available.

Analyze the provided Xero data and return a JSON object with the following structure:
- model_version: "1.0.0"
- org_id: organization ID
- as_of_utc: current timestamp
- payroll_date: next payroll date (ISO format)
- payroll_amount_net: net payroll amount
- payroll_employer_costs: employer taxes/benefits (or null)
- payroll_amount_with_buffer: payroll amount including safety buffer
- current_cash_available: current cash in bank/cash accounts
- projected_cash_on_payroll_date: projected cash on payroll date
- payroll_coverage_ratio: coverage ratio (projected_cash / payroll_amount_with_buffer)
- health_status: "Green" (≥1.20), "Yellow" (1.00-1.19), or "Red" (<1.00)
- near_miss: boolean (true if 1.00-1.05)
- detection_tier: 0-4 (0=highest confidence, 4=lowest)
- detection_confidence: "High", "Medium", "Low", or "VeryLow"
- forecast_confidence: 0-100
- data_completeness_score: 0-100
- key_risk_drivers: array of strings
- assumptions: array of strings
- scenarios: {base: {projected_cash, coverage_ratio}, optimistic: {...}, pessimistic: {...}}
- evidence: {bank_transactions: [], invoices_ar: [], bills_ap: [], ...}
- used_endpoints: array of strings
- warnings: array of strings
- missing_data: array of strings (if blocking data missing)
- recommended_actions: array of strings

Then provide an advisory_narrative (≤140 words) explaining the assessment."""
    
    @abstractmethod
    async def analyze_payroll_risk(
        self,
        data: Dict[str, Any],
        org_id: str,
        base_currency: str,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> PayrollRiskResult:
        """Analyze payroll risk using LLM reasoning."""
        pass
    
    def _prepare_data_summary(self, data: Dict[str, Any]) -> str:
        """Prepare a summary of collected data for LLM."""
        summary_parts = []
        error_count = 0
        
        # Organization - extract from text content
        if data.get("organisation"):
            org = data["organisation"]
            org_text = self._extract_text_from_content(org)
            if org_text:
                # Check for errors in organization data
                if any(indicator in org_text.lower() for indicator in ["error", "401", "unauthorized", "failed"]):
                    error_count += 1
                    summary_parts.append("⚠️ Organization Details: ERROR - Authentication/Authorization failure")
                else:
                    # Extract key fields from text
                    org_name = self._extract_field_from_text(org_text, "Name:")
                    base_currency = self._extract_field_from_text(org_text, "Base Currency:")
                    timezone = self._extract_field_from_text(org_text, "Timezone:")
                    org_id = self._extract_field_from_text(org_text, "Organisation ID:")
                    
                    summary_parts.append(f"Organization ID: {org_id or 'Unknown'}")
                    summary_parts.append(f"Organization Name: {org_name or 'Unknown'}")
                    summary_parts.append(f"Base Currency: {base_currency or 'Unknown'}")
                    summary_parts.append(f"Timezone: {timezone or 'Unknown'}")
        
        # Accounts - count and summarize, identify bank accounts
        bank_accounts = []
        if data.get("accounts"):
            accounts = data["accounts"]
            account_text = self._extract_text_from_content(accounts)
            if account_text:
                # Count accounts from text
                account_count = account_text.count("Account:")
                summary_parts.append(f"Total Accounts: {account_count}")
                # Extract bank account details
                lines = account_text.split("\n")
                current_account = {}
                for line in lines:
                    if line.startswith("Account:"):
                        if current_account.get("Type") in ["BANK", "CURRENT"]:
                            bank_accounts.append(current_account)
                        current_account = {"Name": line.replace("Account:", "").strip()}
                    elif "Code:" in line:
                        current_account["Code"] = self._extract_field_from_text(line, "Code:")
                    elif "Type:" in line:
                        current_account["Type"] = self._extract_field_from_text(line, "Type:")
                    elif "ID:" in line and "Account" not in line:
                        current_account["ID"] = self._extract_field_from_text(line, "ID:")
                # Check last account
                if current_account.get("Type") in ["BANK", "CURRENT"]:
                    bank_accounts.append(current_account)
                
                if bank_accounts:
                    summary_parts.append(f"Bank/Cash Accounts: {len(bank_accounts)}")
                    for bank_acc in bank_accounts[:5]:  # Show first 5
                        acc_name = bank_acc.get("Name", "Unknown")
                        acc_code = bank_acc.get("Code", "")
                        summary_parts.append(f"  - {acc_name} (Code: {acc_code})")
        
        # Count records for each data type
        data_types = [
            ("bank_transactions", "Bank Transactions (Bank Feeds)"),
            ("manual_journals", "Manual Journals"),
            ("invoices", "Invoices (Type ACCREC = Accounts Receivable, Type ACCPAY = Accounts Payable)"),
            ("payments", "Payments"),
            ("credit_notes", "Credit Notes"),
            ("contacts", "Contacts"),
        ]
        
        for key, label in data_types:
            if data.get(key):
                items = data[key]
                if isinstance(items, list):
                    # Check for errors in data
                    items_text = str(items).lower()
                    has_error = any(indicator in items_text for indicator in ["error", "401", "unauthorized", "failed", "status code"])
                    
                    if has_error:
                        error_count += 1
                        summary_parts.append(f"⚠️ {label}: ERROR - Authentication/Authorization failure")
                    else:
                        # Count text items
                        count = len([item for item in items if isinstance(item, dict) and item.get("type") == "text"])
                        if count > 0:
                            summary_parts.append(f"{label}: {count} records")
                            
                            # Special handling for manual journals - check for duplicates and extract payroll info
                            if key == "manual_journals":
                                # Extract journal IDs and dates to detect duplicates
                                journal_ids = set()
                                journal_dates = {}
                                for item in items:
                                    if isinstance(item, dict) and item.get("type") == "text":
                                        text = item.get("text", "")
                                        # Look for Manual Journal ID
                                        import re
                                        id_match = re.search(r'Manual Journal ID[:\s]+([a-f0-9-]+)', text, re.IGNORECASE)
                                        date_match = re.search(r'Date[:\s]+([^\n]+)', text, re.IGNORECASE)
                                        desc_match = re.search(r'Bi-weekly Payroll[^\n]*', text, re.IGNORECASE)
                                        if id_match:
                                            journal_id = id_match.group(1)
                                            if journal_id in journal_ids:
                                                summary_parts.append(f"  ⚠️ WARNING: Duplicate journal ID detected: {journal_id[:8]}...")
                                            journal_ids.add(journal_id)
                                        if date_match and desc_match:
                                            date_str = date_match.group(1).strip()
                                            desc = desc_match.group(0)
                                            if date_str in journal_dates:
                                                if journal_dates[date_str] == desc:
                                                    summary_parts.append(f"  ⚠️ WARNING: Possible duplicate payroll entry for {date_str}: {desc}")
                                            else:
                                                journal_dates[date_str] = desc
                                
                                # Add payroll information if available
                                if data.get("payroll_info"):
                                    payroll_info = data["payroll_info"]
                                    summary_parts.append(f"\n💰 Payroll Information (from Manual Journals - POSTED entries only):")
                                    summary_parts.append(f"  - Cadence: {payroll_info.get('cadence', 'Unknown')}")
                                    summary_parts.append(f"  - Highest of last 4 payrolls: ${payroll_info.get('highest_amount', 0):.2f}")
                                    summary_parts.append(f"  - Average of last 4 payrolls: ${payroll_info.get('average_amount', 0):.2f}")
                                    if payroll_info.get('next_payroll_date'):
                                        summary_parts.append(f"  - Next payroll date (predicted): {payroll_info['next_payroll_date']}")
                                    else:
                                        summary_parts.append(f"  - Next payroll date: Not predicted (insufficient data)")
                                    summary_parts.append(f"  - Total POSTED payroll entries found: {payroll_info.get('total_entries_found', 0)}")
                                    summary_parts.append(f"  - Last 4 payroll amounts:")
                                    for entry in payroll_info.get('last_4_payroll_entries', [])[:4]:
                                        summary_parts.append(f"    • {entry.get('date', 'Unknown')}: ${entry.get('amount', 0):.2f}")
                                else:
                                    summary_parts.append(f"\n⚠️ Payroll Information: No POSTED payroll journals found. Only POSTED (not VOIDED or DRAFT) journals are used for payroll analysis.")
        
        # Add error summary at the end
        if error_count > 0:
            summary_parts.append(f"\n⚠️ WARNING: {error_count} data source(s) failed with authentication errors (401). Analysis may be limited.")
        
        # Reports - Extract bank balances from Balance Sheet
        if data.get("balance_sheet"):
            balance_sheet = data["balance_sheet"]
            balance_sheet_text = self._extract_text_from_content(balance_sheet)
            if balance_sheet_text and not any(indicator in balance_sheet_text.lower() for indicator in ["error", "401", "unauthorized", "failed"]):
                summary_parts.append("✓ Balance Sheet Report: Available")
                # Extract bank account balances from balance sheet
                import json
                import re
                # Try to find JSON in balance sheet text
                json_match = re.search(r'\[.*\]', balance_sheet_text, re.DOTALL)
                if json_match:
                    try:
                        bs_data = json.loads(json_match.group(0))
                        # Look for Bank section
                        for section in bs_data:
                            if isinstance(section, dict):
                                if section.get("title") == "Bank" or (section.get("rowType") == "Section" and "Bank" in str(section.get("title", ""))):
                                    rows = section.get("rows", [])
                                    for row in rows:
                                        if isinstance(row, dict) and row.get("rowType") == "Row":
                                            cells = row.get("cells", [])
                                            if len(cells) >= 2:
                                                account_name = cells[0].get("value", "")
                                                balance = cells[1].get("value", "")
                                                if account_name and balance and balance.replace(".", "").replace("-", "").isdigit():
                                                    summary_parts.append(f"  Bank Balance - {account_name}: {balance}")
                    except:
                        pass
                # Also try text-based extraction
                bank_balance_lines = re.findall(r'(Business Bank Account|Business Savings Account|.*Bank.*Account).*?(\d+\.\d{2})', balance_sheet_text, re.IGNORECASE)
                for bank_name, balance in bank_balance_lines[:5]:  # Limit to 5
                    summary_parts.append(f"  Bank Balance - {bank_name.strip()}: {balance}")
            else:
                summary_parts.append("✗ Balance Sheet Report: Error or missing")
        else:
            summary_parts.append("✗ Balance Sheet Report: Not fetched")
            
        if data.get("profit_loss"):
            profit_loss = data["profit_loss"]
            profit_loss_text = self._extract_text_from_content(profit_loss)
            if profit_loss_text and not any(indicator in profit_loss_text.lower() for indicator in ["error", "401", "unauthorized", "failed"]):
                summary_parts.append("✓ Profit & Loss Report: Available")
            else:
                summary_parts.append("✗ Profit & Loss Report: Error or missing")
        else:
            summary_parts.append("✗ Profit & Loss Report: Not fetched")
            
        if data.get("trial_balance"):
            trial_balance = data["trial_balance"]
            trial_balance_text = self._extract_text_from_content(trial_balance)
            if trial_balance_text and not any(indicator in trial_balance_text.lower() for indicator in ["error", "401", "unauthorized", "failed"]):
                summary_parts.append("✓ Trial Balance Report: Available")
            else:
                summary_parts.append("✗ Trial Balance Report: Error or missing")
        else:
            summary_parts.append("✗ Trial Balance Report: Not fetched")
        
        # Aged receivables and payables
        if data.get("aged_receivables"):
            aged_ar = data["aged_receivables"]
            if isinstance(aged_ar, list) and len(aged_ar) > 0:
                summary_parts.append(f"✓ Aged Receivables: Available for {len(aged_ar)} contacts")
            else:
                summary_parts.append("✗ Aged Receivables: Empty or missing")
        else:
            summary_parts.append("✗ Aged Receivables: Not fetched")
            
        if data.get("aged_payables"):
            aged_ap = data["aged_payables"]
            if isinstance(aged_ap, list) and len(aged_ap) > 0:
                summary_parts.append(f"✓ Aged Payables: Available for {len(aged_ap)} contacts")
            else:
                summary_parts.append("✗ Aged Payables: Empty or missing")
        else:
            summary_parts.append("✗ Aged Payables: Not fetched")
        
        return "\n".join(summary_parts) if summary_parts else "No data available"
    
    def _prepare_full_data_content(self, data: Dict[str, Any]) -> str:
        """Prepare full data content for LLM analysis."""
        content_parts = []
        
        # Include key data sources with their full text
        key_sources = [
            ("organisation", "Organization Details"),
            ("accounts", "Chart of Accounts"),
            ("bank_transactions", "Bank Transactions (Bank Feeds)"),
            ("manual_journals", "Manual Journal Entries"),
            ("invoices", "Invoices (Type ACCREC = Accounts Receivable, Type ACCPAY = Accounts Payable)"),
            ("payments", "Payments"),
            ("credit_notes", "Credit Notes"),
            ("contacts", "Contacts/Vendors"),
            ("balance_sheet", "Balance Sheet Report"),
            ("profit_loss", "Profit & Loss Report"),
            ("trial_balance", "Trial Balance Report"),
            ("aged_receivables", "Aged Receivables by Contact"),
            ("aged_payables", "Aged Payables by Contact"),
            ("payroll_info", "Payroll Information (Extracted from Manual Journals)"),
        ]
        
        for key, label in key_sources:
            if data.get(key):
                items = data[key]
                
                # Special handling for payroll_info (it's already a dict, not a list)
                if key == "payroll_info":
                    import json
                    payroll_info_str = json.dumps(items, indent=2)
                    content_parts.append(f"\n=== {label} ===\n{payroll_info_str}\n")
                else:
                    text_content = self._extract_text_from_content(items)
                    if text_content:
                        # Limit text length to avoid token limits
                        if len(text_content) > 5000:
                            text_content = text_content[:5000] + "\n... (truncated)"
                        content_parts.append(f"\n=== {label} ===\n{text_content}\n")
        
        return "\n".join(content_parts) if content_parts else "No detailed data available"
    
    def _extract_text_from_content(self, content: Any) -> str:
        """Extract text from MCP content array."""
        # Handle aged receivables/payables structure (list of {contactId, data})
        if isinstance(content, list) and len(content) > 0:
            first_item = content[0]
            if isinstance(first_item, dict) and "contactId" in first_item and "data" in first_item:
                # This is aged receivables/payables structure
                texts = []
                for item in content:
                    contact_id = item.get("contactId", "Unknown")
                    data = item.get("data", [])
                    contact_text = self._extract_text_from_content(data)
                    if contact_text:
                        texts.append(f"Contact ID: {contact_id}\n{contact_text}\n")
                return "\n".join(texts)
        
        # Handle standard MCP content array
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
    
    def _extract_field_from_text(self, text: str, field_name: str) -> Optional[str]:
        """Extract a field value from text (e.g., 'Name: ABC Corp' -> 'ABC Corp')."""
        if not text or not field_name:
            return None
        
        for line in text.split("\n"):
            if field_name in line:
                # Extract value after the field name
                parts = line.split(field_name, 1)
                if len(parts) > 1:
                    value = parts[1].strip()
                    # Remove any trailing separators
                    value = value.split("||")[0].strip() if "||" in value else value
                    return value if value else None
        return None
    
    def _save_prompt_to_file(self, prompt: str, org_id: str):
        """Save the prompt to a file for offline review."""
        try:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            # Sanitize org_id for filename
            safe_org_id = "".join(c for c in org_id if c.isalnum() or c in ('-', '_'))[:50]
            filename = f"prompt_{timestamp}_{safe_org_id}.txt"
            filepath = PROMPTS_DIR / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Timestamp: {datetime.utcnow().isoformat()}\n")
                f.write(f"Organization ID: {org_id}\n")
                f.write(f"LLM Provider: {config.LLM_PROVIDER}\n")
                f.write("=" * 80 + "\n\n")
                f.write(prompt)
            
            logger.info(f"Prompt saved to {filepath}")
        except Exception as e:
            logger.warning(f"Failed to save prompt to file: {e}")
    
    def _parse_llm_response(self, content: str) -> PayrollRiskResult:
        """Parse LLM response into PayrollRiskResult."""
        try:
            logger.info("=" * 80)
            logger.info("PARSING LLM RESPONSE")
            logger.info("=" * 80)
            logger.info(f"Content type: {type(content)}")
            logger.info(f"Content length: {len(content) if content else 0}")
            
            if not content or not content.strip():
                logger.error("Empty content received from LLM")
                raise ValueError("Empty response from LLM")
            
            # Log first and last parts of content
            logger.info(f"First 1000 chars: {content[:1000]}")
            logger.info(f"Last 1000 chars: {content[-1000:] if len(content) > 1000 else content}")
            
            # Try to extract JSON (might be mixed with narrative)
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            
            logger.info(f"JSON search: json_start={json_start}, json_end={json_end}")
            
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                logger.info(f"Extracted JSON string length: {len(json_str)}")
                logger.info(f"Extracted JSON (first 500 chars): {json_str[:500]}")
                logger.info(f"Extracted JSON (last 500 chars): {json_str[-500:] if len(json_str) > 500 else json_str}")
                
                try:
                    data = json.loads(json_str)
                    logger.info(f"Successfully parsed JSON! Keys: {list(data.keys())}")
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error at position {e.pos}: {e.msg}")
                    logger.error(f"JSON string around error (pos {e.pos}): {json_str[max(0, e.pos-100):e.pos+100]}")
                    logger.error(f"Full JSON string for debugging: {json_str}")
                    raise
                
                # Extract narrative (after JSON)
                narrative = content[json_end:].strip()
                if narrative:
                    data["advisory_narrative"] = narrative
            else:
                # Try parsing entire content as JSON
                logger.info(f"No JSON braces found, trying to parse entire content as JSON (length: {len(content)})")
                try:
                    data = json.loads(content)
                    logger.info(f"Successfully parsed entire content as JSON! Keys: {list(data.keys())}")
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e.msg} at position {e.pos}")
                    logger.error(f"Content around error (pos {e.pos}): {content[max(0, e.pos-200):e.pos+200]}")
                    
                    # Try to find JSON in markdown code blocks
                    logger.info("Trying to find JSON in markdown code blocks...")
                    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
                    if json_match:
                        logger.info(f"Found JSON in code block! Length: {len(json_match.group(1))}")
                        logger.info(f"Code block JSON (first 500 chars): {json_match.group(1)[:500]}")
                        data = json.loads(json_match.group(1))
                    else:
                        # Try to find any JSON object in the content (more flexible)
                        logger.info("Trying flexible JSON extraction...")
                        # Look for JSON object that might be embedded in text
                        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
                        json_matches = re.findall(json_pattern, content, re.DOTALL)
                        logger.info(f"Found {len(json_matches)} potential JSON matches")
                        for i, match in enumerate(json_matches[:3]):  # Try first 3 matches
                            logger.info(f"  Match {i+1} (length {len(match)}): {match[:200]}...")
                            try:
                                data = json.loads(match)
                                logger.info(f"  ✓ Successfully parsed match {i+1}!")
                                break
                            except json.JSONDecodeError:
                                logger.info(f"  ✗ Match {i+1} failed to parse")
                                continue
                        else:
                            logger.error("All JSON extraction attempts failed")
                            # If no JSON found, check if this is an error message we can parse
                            if "401" in content or "authentication" in content.lower() or "authorization" in content.lower():
                                logger.warning("LLM returned error message instead of JSON. Creating error result from text.")
                                # Extract error information from text response
                                error_result = self._create_error_result_from_text(content)
                                return error_result
                            else:
                                raise ValueError(f"Could not extract valid JSON from response. Content starts with: {content[:200]}")
            
            # Convert to PayrollRiskResult
            result = PayrollRiskResult()
            
            # Map fields
            result.model_version = data.get("model_version", "1.0.0")
            result.org_id = data.get("org_id", "")
            result.as_of_utc = data.get("as_of_utc", self._get_current_utc())
            result.payroll_date = data.get("payroll_date", "")
            result.payroll_amount_net = float(data.get("payroll_amount_net", 0))
            result.payroll_employer_costs = data.get("payroll_employer_costs")
            if result.payroll_employer_costs is not None:
                result.payroll_employer_costs = float(result.payroll_employer_costs)
            result.payroll_amount_with_buffer = float(data.get("payroll_amount_with_buffer", 0))
            result.current_cash_available = float(data.get("current_cash_available", 0))
            result.projected_cash_on_payroll_date = float(data.get("projected_cash_on_payroll_date", 0))
            result.payroll_coverage_ratio = float(data.get("payroll_coverage_ratio", 0))
            
            # Health status
            health_str = data.get("health_status", "Red")
            try:
                result.health_status = HealthStatus[health_str.upper()]
            except KeyError:
                result.health_status = HealthStatus.RED
            
            result.near_miss = bool(data.get("near_miss", False))
            
            # Detection
            tier_val = data.get("detection_tier", 4)
            try:
                result.detection_tier = DetectionTier(tier_val)
            except ValueError:
                result.detection_tier = DetectionTier.TIER_4
            
            result.detection_confidence = data.get("detection_confidence", "VeryLow")
            result.forecast_confidence = int(data.get("forecast_confidence", 0))
            result.data_completeness_score = int(data.get("data_completeness_score", 0))
            
            # Lists
            result.key_risk_drivers = data.get("key_risk_drivers", [])
            result.assumptions = data.get("assumptions", [])
            result.recommended_actions = data.get("recommended_actions", [])
            result.warnings = data.get("warnings", [])
            result.used_endpoints = data.get("used_endpoints", [])
            result.missing_data = data.get("missing_data")
            
            # Scenarios
            scenarios_data = data.get("scenarios", {})
            for scenario_name, scenario_data in scenarios_data.items():
                result.scenarios[scenario_name] = Scenario(
                    projected_cash=float(scenario_data.get("projected_cash", 0)),
                    coverage_ratio=float(scenario_data.get("coverage_ratio", 0))
                )
            
            # Evidence
            evidence_data = data.get("evidence", {})
            result.evidence = Evidence(
                bank_transactions=evidence_data.get("bank_transactions", []),
                bank_transfers=evidence_data.get("bank_transfers", []),
                invoices_ar=evidence_data.get("invoices_ar", []),
                bills_ap=evidence_data.get("bills_ap", []),
                credit_notes=evidence_data.get("credit_notes", []),
                journals=evidence_data.get("journals", []),
                payroll_objects=evidence_data.get("payroll_objects", []),
                report_refs=evidence_data.get("report_refs", []),
                fx_rates=evidence_data.get("fx_rates", [])
            )
            
            # Narrative
            result.advisory_narrative = data.get("advisory_narrative", "")
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON response: {str(e)}")
            return self._create_error_result(f"Invalid JSON response from LLM: {str(e)}")
        except Exception as e:
            logger.error(f"Error parsing LLM response: {str(e)}", exc_info=True)
            return self._create_error_result(f"Error parsing response: {str(e)}")
    
    def _create_error_result(self, error_message: str) -> PayrollRiskResult:
        """Create an error result."""
        result = PayrollRiskResult()
        result.health_status = HealthStatus.RED
        result.warnings = [f"Analysis error: {error_message}"]
        result.missing_data = [error_message]
        result.advisory_narrative = f"Unable to complete payroll risk analysis: {error_message}"
        return result
    
    def _create_error_result_from_text(self, text_response: str) -> PayrollRiskResult:
        """Create an error result from LLM text response (when JSON is not returned)."""
        result = PayrollRiskResult()
        result.health_status = HealthStatus.RED
        
        # Extract key information from text response
        warnings = []
        missing_data = []
        
        # Check for authentication errors
        if "401" in text_response or "authentication" in text_response.lower():
            warnings.append("Xero API authentication failed (401 errors)")
            missing_data.append("All Xero data sources failed due to authentication errors")
        
        # Extract the main message (first paragraph or section)
        lines = text_response.split('\n')
        main_message = ""
        for line in lines[:10]:  # Get first 10 lines
            if line.strip() and not line.strip().startswith('#'):
                main_message = line.strip()
                break
        
        if not main_message:
            main_message = text_response[:200]  # Fallback to first 200 chars
        
        result.warnings = warnings if warnings else ["LLM returned text response instead of JSON"]
        result.missing_data = missing_data if missing_data else ["Unable to parse LLM response"]
        result.advisory_narrative = f"{main_message}\n\nFull response: {text_response[:500]}..."
        
        logger.info(f"Created error result from text response. Warnings: {warnings}, Missing data: {missing_data}")
        return result
    
    def _get_current_utc(self) -> str:
        """Get current UTC timestamp as ISO string."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


class OpenAILLMEngine(BaseLLMEngine):
    """OpenAI LLM engine for payroll risk reasoning."""
    
    def __init__(self, model: str = "gpt-4o"):
        """
        Initialize OpenAI LLM engine.
        
        Args:
            model: OpenAI model to use (default: gpt-4o)
        """
        super().__init__()
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=config.OPENAI_API_KEY)
            self.model = model
        except ImportError:
            raise ImportError("OpenAI package not installed. Install with: pip install openai")
    
    async def analyze_payroll_risk(
        self,
        data: Dict[str, Any],
        org_id: str,
        base_currency: str,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> PayrollRiskResult:
        """
        Analyze payroll risk using OpenAI.
        
        Args:
            data: Collected Xero data
            org_id: Organization ID
            base_currency: Base currency code
            progress_callback: Optional callback for progress updates
            
        Returns:
            PayrollRiskResult with analysis
        """
        logger.info("Starting OpenAI LLM analysis for payroll risk")
        
        if progress_callback:
            progress_callback(70, "🧠 Preparing data for AI analysis...")
        
        # Prepare data summary and full content for LLM
        data_summary = self._prepare_data_summary(data)
        data_content = self._prepare_full_data_content(data)
        
        if progress_callback:
            progress_callback(75, "💭 AI is analyzing your financial data...")
        
        # Build prompt with strict JSON requirement
        prompt = f"""{self.prompt_template}

**Organization:** {org_id}
**Base Currency:** {base_currency}

**Data Summary:**
{data_summary}

**Full Xero Data (for detailed analysis):**
{data_content}

**CRITICAL: YOU MUST RETURN VALID JSON ONLY**

Even if data is missing or contains errors (like 401 authentication failures), you MUST return a valid JSON object with this exact structure:

{{
  "model_version": "1.0.0",
  "org_id": "{org_id}",
  "as_of_utc": "ISO timestamp",
  "payroll_date": "",
  "payroll_amount_net": 0,
  "payroll_employer_costs": null,
  "payroll_amount_with_buffer": 0,
  "current_cash_available": 0,
  "projected_cash_on_payroll_date": 0,
  "payroll_coverage_ratio": 0,
  "health_status": "Red",
  "near_miss": false,
  "detection_tier": 4,
  "detection_confidence": "VeryLow",
  "forecast_confidence": 0,
  "data_completeness_score": 0,
  "key_risk_drivers": ["List any issues"],
  "assumptions": ["List assumptions"],
  "scenarios": {{
    "base": {{"projected_cash": 0, "coverage_ratio": 0}},
    "optimistic": {{"projected_cash": 0, "coverage_ratio": 0}},
    "pessimistic": {{"projected_cash": 0, "coverage_ratio": 0}}
  }},
  "evidence": {{"bank_transactions": [], "invoices_ar": [], "bills_ap": [], "credit_notes": [], "journals": [], "payroll_objects": [], "report_refs": [], "fx_rates": []}},
  "used_endpoints": [],
  "warnings": ["Explain any errors or missing data here"],
  "missing_data": ["List missing data sources"],
  "recommended_actions": ["List actions"],
  "advisory_narrative": "Explain the situation in ≤140 words"
}}

**IMPORTANT**: 
- Return ONLY the JSON object, no text before or after
- If you see 401 errors, explain them in "warnings" and "missing_data" fields
- Always return valid JSON, never plain text explanations"""

        # Save prompt to file for offline review
        self._save_prompt_to_file(prompt, org_id)
        
        try:
            if progress_callback:
                progress_callback(80, "🤖 AI is thinking hard about your payroll risk...")
            
            # Call OpenAI API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a financial risk analysis expert. Always return valid JSON followed by a narrative."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.3,  # Lower temperature for more consistent analysis
                max_tokens=4000
            )
            
            if progress_callback:
                progress_callback(90, "📊 Processing AI insights...")
            
            # Parse response
            content = response.choices[0].message.content
            logger.debug(f"OpenAI response received: {content[:500]}...")
            
            # Extract JSON and narrative
            result = self._parse_llm_response(content)
            
            # Set metadata
            result.org_id = org_id
            result.as_of_utc = self._get_current_utc()
            
            logger.info(f"OpenAI LLM analysis complete. Health status: {result.health_status.value}")
            if progress_callback:
                progress_callback(95, "✨ Analysis complete! Finalizing results...")
            return result
            
        except Exception as e:
            logger.error(f"Error in OpenAI LLM analysis: {str(e)}", exc_info=True)
            # Return error result
            return self._create_error_result(str(e))


class ToqanLLMEngine(BaseLLMEngine):
    """Toqan LLM engine for payroll risk reasoning."""
    
    def __init__(self):
        """Initialize Toqan LLM engine."""
        super().__init__()
        self.api_key = config.TOQAN_API_KEY
        self.base_url = config.TOQAN_API_BASE_URL
        self.headers = {
            "accept": "*/*",
            "content-type": "application/json",
            "X-Api-Key": self.api_key
        }
        
        if not self.api_key:
            raise ValueError("TOQAN_API_KEY not set in environment variables")
    
    def _create_conversation(self, user_message: str) -> tuple[str, Any]:
        """
        Create a conversation with Toqan API.
        
        Returns:
            Tuple of (conversation_id, initial_response)
        """
        url = f"{self.base_url}/create_conversation"
        payload = {"user_message": user_message}
        
        logger.info(f"Creating Toqan conversation: {url}")
        response = requests.post(url, json=payload, headers=self.headers, timeout=60)
        response.raise_for_status()
        
        response_data = response.json()
        conversation_id = response_data.get("conversation_id")
        
        if not conversation_id:
            raise ValueError(f"No conversation_id in response: {response_data}")
        
        logger.info(f"Toqan conversation created: {conversation_id}")
        return conversation_id, response_data
    
    def _find_conversation(self, conversation_id: str, max_wait: int = 120) -> list:
        """
        Poll for conversation response until ready.
        
        Args:
            conversation_id: Conversation ID to check
            max_wait: Maximum wait time in seconds
            
        Returns:
            List of conversation messages
        """
        url = f"{self.base_url}/find_conversation"
        payload = {"conversation_id": conversation_id}
        
        start_time = time.time()
        poll_interval = 2  # Poll every 2 seconds
        
        logger.info(f"Polling for Toqan conversation response: {conversation_id}")
        
        while time.time() - start_time < max_wait:
            try:
                response = requests.post(url, json=payload, headers=self.headers, timeout=30)
                response.raise_for_status()
                
                conversations = response.json()
                
                # Response is ready when we have more than 1 message (user + AI)
                if isinstance(conversations, list) and len(conversations) > 1:
                    logger.info(f"Toqan conversation response ready: {len(conversations)} messages")
                    return conversations
                
                # Wait before next poll
                time.sleep(poll_interval)
                
            except requests.RequestException as e:
                logger.warning(f"Error polling conversation: {str(e)}, retrying...")
                time.sleep(poll_interval)
        
        raise TimeoutError(f"Conversation response not ready after {max_wait} seconds")
    
    def _clean_ai_message(self, ai_message: str) -> str:
        """
        Clean AI message by removing XML-like tags and extracting JSON.
        
        Args:
            ai_message: Raw AI message from Toqan
            
        Returns:
            Cleaned message with JSON extracted
        """
        import re
        
        if not ai_message or not ai_message.strip():
            raise ValueError("Empty AI message from Toqan")
        
        # Clean up the message - remove XML-like tags if present
        logger.info("Cleaning AI message...")
        original_length = len(ai_message)
        logger.info(f"Original message length: {original_length}")
        
        # Remove common XML/HTML-like tags that might wrap the response
        cleaned_message = ai_message
        
        # Handle <think> tags (most common in Toqan)
        # These tags wrap the LLM's reasoning, but the actual output should be after the closing tag
        if '<think>' in cleaned_message.lower():
            logger.info("Found <think> tags, processing...")
            
            # Strategy 1: Extract content AFTER the closing tag (this is the actual response)
            after_tag_match = re.search(r'</think>\s*(.*)', cleaned_message, re.DOTALL | re.IGNORECASE)
            if after_tag_match:
                content_after = after_tag_match.group(1).strip()
                if len(content_after) > 50:  # Meaningful content after tag
                    logger.info(f"✓ Found content after </think> tag, length: {len(content_after)}")
                    cleaned_message = content_after
                else:
                    logger.warning(f"Content after tag is too short ({len(content_after)} chars), checking inside tags...")
                    # Strategy 2: Check inside tags for JSON
                    inner_match = re.search(r'<think>(.*?)</think>', cleaned_message, re.DOTALL | re.IGNORECASE)
                    if inner_match:
                        inner_content = inner_match.group(1).strip()
                        logger.info(f"Content inside tags, length: {len(inner_content)}")
                        
                        # Look for JSON in the inner content - use a more robust pattern
                        # Try to find the largest JSON object
                        json_matches = list(re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', inner_content, re.DOTALL))
                        if json_matches:
                            # Get the largest match (most likely to be the full JSON)
                            json_match = max(json_matches, key=lambda m: len(m.group(0)))
                            logger.info("✓ Found JSON inside <think> tags, extracting...")
                            cleaned_message = json_match.group(0)
                            logger.info(f"Extracted JSON length: {len(cleaned_message)}")
                        else:
                            logger.warning("✗ No JSON found inside tags. LLM may have only returned reasoning.")
                            # This is a problem - the LLM didn't output JSON
                            raise ValueError(f"LLM response contains no JSON. The response was only reasoning wrapped in <think> tags. The LLM needs to output JSON after its reasoning. Inner content length: {len(inner_content)}")
            else:
                # No closing tag pattern, try to extract inner content directly
                logger.info("No closing tag found, extracting inner content...")
                inner_match = re.search(r'<think>(.*?)</think>', cleaned_message, re.DOTALL | re.IGNORECASE)
                if inner_match:
                    inner_content = inner_match.group(1).strip()
                    logger.info(f"Inner content length: {len(inner_content)}")
                    # Look for JSON
                    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', inner_content, re.DOTALL)
                    if json_match:
                        logger.info("✓ Found JSON in inner content, extracting...")
                        cleaned_message = json_match.group(0)
                    else:
                        logger.warning("✗ No JSON in inner content")
                        cleaned_message = inner_content
                else:
                    # Just remove the tags
                    logger.warning("Could not extract content, removing tags...")
                    cleaned_message = re.sub(r'<think>', '', cleaned_message, flags=re.IGNORECASE)
                    cleaned_message = re.sub(r'</think>', '', cleaned_message, flags=re.IGNORECASE)
                    cleaned_message = cleaned_message.strip()
        
        # Remove other common tags (but only if they're not already handled)
        if '<thinking>' in cleaned_message.lower() and '<think>' not in cleaned_message.lower():
            cleaned_message = re.sub(r'<thinking>.*?</thinking>', '', cleaned_message, flags=re.DOTALL | re.IGNORECASE)
        if '<reasoning>' in cleaned_message.lower() and '<think>' not in cleaned_message.lower():
            cleaned_message = re.sub(r'<reasoning>.*?</reasoning>', '', cleaned_message, flags=re.DOTALL | re.IGNORECASE)
        
        # Clean up extra whitespace
        cleaned_message = cleaned_message.strip()
        
        if len(cleaned_message) != original_length:
            logger.info(f"After cleaning: original length {original_length} -> cleaned length {len(cleaned_message)}")
        else:
            logger.info("No tags found or removed, using original message")
        
        # If cleaned message is too short, it might be that everything was in the reasoning tag
        if len(cleaned_message) < 50:
            logger.warning(f"Cleaned message is very short ({len(cleaned_message)} chars). Original might have been all reasoning.")
            # Try to find JSON in the original message even if it's in tags
            logger.info("Searching for JSON in original message...")
            # Use a more robust JSON extraction pattern
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', ai_message, re.DOTALL)
            if json_match:
                logger.info("Found JSON in original message despite tags, extracting...")
                cleaned_message = json_match.group(0)
                logger.info(f"Extracted JSON length: {len(cleaned_message)}")
            else:
                logger.error("No JSON found anywhere in the response. LLM may not have generated JSON.")
                # This is a critical error - the LLM didn't return JSON
                raise ValueError("LLM response contains no JSON. The response was likely only reasoning/thinking without actual output. The LLM needs to be instructed to output JSON after its reasoning.")
        
        return cleaned_message
    
    async def analyze_payroll_risk(
        self,
        data: Dict[str, Any],
        org_id: str,
        base_currency: str,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> PayrollRiskResult:
        """
        Analyze payroll risk using Toqan API.
        
        Args:
            data: Collected Xero data
            org_id: Organization ID
            base_currency: Base currency code
            progress_callback: Optional callback for progress updates
            
        Returns:
            PayrollRiskResult with analysis
        """
        logger.info("Starting Toqan LLM analysis for payroll risk")
        
        if progress_callback:
            progress_callback(70, "🧠 Preparing data for AI analysis...")
        
        # Prepare data summary and full content for LLM
        data_summary = self._prepare_data_summary(data)
        data_content = self._prepare_full_data_content(data)
        
        if progress_callback:
            progress_callback(75, "💭 AI is analyzing your financial data...")
        
        # Build prompt with strict JSON requirement
        prompt = f"""{self.prompt_template}

**Organization:** {org_id}
**Base Currency:** {base_currency}

**Data Summary:**
{data_summary}

**Full Xero Data (for detailed analysis):**
{data_content}

**CRITICAL: YOU MUST RETURN VALID JSON ONLY**

Even if data is missing or contains errors (like 401 authentication failures), you MUST return a valid JSON object with this exact structure:

{{
  "model_version": "1.0.0",
  "org_id": "{org_id}",
  "as_of_utc": "ISO timestamp",
  "payroll_date": "",
  "payroll_amount_net": 0,
  "payroll_employer_costs": null,
  "payroll_amount_with_buffer": 0,
  "current_cash_available": 0,
  "projected_cash_on_payroll_date": 0,
  "payroll_coverage_ratio": 0,
  "health_status": "Red",
  "near_miss": false,
  "detection_tier": 4,
  "detection_confidence": "VeryLow",
  "forecast_confidence": 0,
  "data_completeness_score": 0,
  "key_risk_drivers": ["List any issues"],
  "assumptions": ["List assumptions"],
  "scenarios": {{
    "base": {{"projected_cash": 0, "coverage_ratio": 0}},
    "optimistic": {{"projected_cash": 0, "coverage_ratio": 0}},
    "pessimistic": {{"projected_cash": 0, "coverage_ratio": 0}}
  }},
  "evidence": {{"bank_transactions": [], "invoices_ar": [], "bills_ap": [], "credit_notes": [], "journals": [], "payroll_objects": [], "report_refs": [], "fx_rates": []}},
  "used_endpoints": [],
  "warnings": ["Explain any errors or missing data here"],
  "missing_data": ["List missing data sources"],
  "recommended_actions": ["List actions"],
  "advisory_narrative": "Explain the situation in ≤140 words"
}}

**CRITICAL INSTRUCTIONS FOR TOQAN LLM**: 
- DO NOT use <think>, <think>, or any reasoning tags
- DO NOT include any reasoning or explanation text outside the JSON
- Return ONLY the JSON object, nothing else
- The JSON must start with {{ and end with }}
- If you see 401 errors, explain them in "warnings" and "missing_data" fields
- Always return valid JSON, never plain text explanations or reasoning"""

        # Save prompt to file for offline review
        self._save_prompt_to_file(prompt, org_id)
        
        try:
            if progress_callback:
                progress_callback(80, "🤖 AI is thinking hard about your payroll risk...")
            
            # Create conversation
            conversation_id, _ = self._create_conversation(prompt)
            
            # Wait for response
            conversations = self._find_conversation(conversation_id)
            
            if progress_callback:
                progress_callback(85, "📊 Processing AI insights...")
            
            # Extract AI message (last message in conversation)
            if isinstance(conversations, list) and len(conversations) > 1:
                # Log full conversation structure for debugging
                logger.info(f"Toqan conversation has {len(conversations)} messages")
                for i, msg in enumerate(conversations):
                    logger.info(f"Message {i}: type={type(msg)}, content preview: {str(msg)[:200] if not isinstance(msg, dict) else list(msg.keys())}")
                
                # Get the last message (AI response)
                last_message = conversations[-1]
                logger.info(f"Last message type: {type(last_message)}")
                
                if isinstance(last_message, dict):
                    logger.info(f"Last message keys: {list(last_message.keys())}")
                    for key, value in last_message.items():
                        if isinstance(value, str):
                            logger.info(f"  {key}: {value[:200]}... (length: {len(value)})")
                        else:
                            logger.info(f"  {key}: {type(value)} = {str(value)[:200]}")
                
                # Try different possible message formats
                ai_message = ''
                if isinstance(last_message, dict):
                    # Try different possible keys
                    possible_keys = ['message', 'content', 'text', 'response', 'answer', 'body']
                    for key in possible_keys:
                        if key in last_message:
                            value = last_message[key]
                            if value:
                                ai_message = str(value)
                                logger.info(f"Found message in key '{key}', length: {len(ai_message)}")
                                break
                    
                    # If still empty, try to stringify the whole dict
                    if not ai_message:
                        ai_message = str(last_message)
                        logger.warning(f"No message found in expected keys, using stringified dict")
                elif isinstance(last_message, str):
                    ai_message = last_message
                    logger.info(f"Last message is string, length: {len(ai_message)}")
                else:
                    # Try to convert to string
                    ai_message = str(last_message)
                    logger.warning(f"Last message is unexpected type {type(last_message)}, converting to string")
                
                logger.info(f"Final ai_message length: {len(ai_message)}")
                logger.info(f"First 500 chars of ai_message: {ai_message[:500]}")
                logger.info(f"Last 500 chars of ai_message: {ai_message[-500:] if len(ai_message) > 500 else ai_message}")
                
                if not ai_message or not ai_message.strip():
                    logger.error(f"Empty AI message from Toqan. Full conversation: {conversations}")
                    raise ValueError("Empty response from Toqan API")
                
                # Clean up the message - remove XML-like tags if present
                cleaned_message = self._clean_ai_message(ai_message)
                
                if progress_callback:
                    progress_callback(90, "📊 Processing AI insights...")
                
                # Parse response
                result = self._parse_llm_response(cleaned_message)
                
                # Set metadata
                result.org_id = org_id
                result.as_of_utc = self._get_current_utc()
                
                logger.info(f"Toqan LLM analysis complete. Health status: {result.health_status.value}")
                if progress_callback:
                    progress_callback(95, "✨ Analysis complete! Finalizing results...")
                return result
            else:
                logger.error(f"Unexpected conversation format: {conversations}")
                raise ValueError(f"Unexpected conversation format: {type(conversations)}, length: {len(conversations) if isinstance(conversations, list) else 'N/A'}")
            
        except Exception as e:
            logger.error(f"Error in Toqan LLM analysis: {str(e)}", exc_info=True)
            # Return error result
            return self._create_error_result(str(e))


def create_llm_engine(model: Optional[str] = None, use_agentic: Optional[bool] = None) -> BaseLLMEngine:
    """
    Factory function to create the appropriate LLM engine based on configuration.
    
    Args:
        model: Optional model name (for OpenAI only)
        use_agentic: Optional flag to override config.USE_AGENTIC_ARCHITECTURE
        
    Returns:
        BaseLLMEngine instance
    """
    # Check if agentic architecture should be used
    use_agentic_flag = use_agentic if use_agentic is not None else config.USE_AGENTIC_ARCHITECTURE
    
    if use_agentic_flag:
        logger.info("Using Agentic LLM Engine architecture")
        from app.agents.agentic_llm_engine import AgenticLLMEngine
        
        # Create base engine first
        provider = config.LLM_PROVIDER.lower()
        if provider == "toqan":
            base_engine = ToqanLLMEngine()
        elif provider == "openai":
            model_name = model or config.OPENAI_MODEL
            base_engine = OpenAILLMEngine(model=model_name)
        else:
            raise ValueError(f"Unknown LLM provider: {provider}. Use 'openai' or 'toqan'.")
        
        return AgenticLLMEngine(base_llm_engine=base_engine)
    else:
        # Use traditional single-prompt approach
        provider = config.LLM_PROVIDER.lower()
        
        if provider == "toqan":
            logger.info("Using Toqan LLM engine (single-prompt)")
            return ToqanLLMEngine()
        elif provider == "openai":
            logger.info("Using OpenAI LLM engine (single-prompt)")
            model_name = model or config.OPENAI_MODEL
            return OpenAILLMEngine(model=model_name)
        else:
            raise ValueError(f"Unknown LLM provider: {provider}. Use 'openai' or 'toqan'.")


# Backward compatibility: LLMEngine alias
LLMEngine = create_llm_engine
