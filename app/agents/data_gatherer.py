"""Data gathering module for Payroll Risk Assessment."""
import asyncio
import logging
import re
from typing import Dict, Any, List, Tuple, Optional, Callable
from datetime import datetime, timedelta

from app.mcp_client import XeroMCPClient
from app.agents.cache import DataCache
from app.xero_client import XeroClient

logger = logging.getLogger(__name__)


class DataGatherer:
    """
    Iteratively collects all data needed for payroll risk assessment.
    Continues until all data sources are exhausted or sufficient.
    """
    
    # Required data sources (in priority order)
    DATA_SOURCES = [
        # Critical (blocking if missing)
        ("organisation", "list-organisation-details", {}),
        ("accounts", "list-accounts", {}),
        
        # Cash position - will paginate
        ("bank_transactions", "list-bank-transactions", {"page": 1}),
        
        # Manual journals (payroll entries, adjustments, etc.)
        ("manual_journals", "list-manual-journals", {}),
        
        # AR/AP for cash forecast - will paginate
        ("invoices", "list-invoices", {"page": 1}),
        ("payments", "list-payments", {"page": 1}),
        ("credit_notes", "list-credit-notes", {"page": 1}),
        
        # Reports
        ("balance_sheet", "list-report-balance-sheet", {}),
        ("profit_loss", "list-profit-and-loss", {}),
        ("trial_balance", "list-trial-balance", {}),
        
        # Contacts (needed for aged receivables/payables) - will paginate
        ("contacts", "list-contacts", {"page": 1}),
        
        # Aged receivables and payables - fetched per contact after contacts are gathered
        # These tools require contactId parameter, so they're handled separately in _gather_aged_reports_by_contact()
        # They are NOT called directly from DATA_SOURCES loop, but are tracked here for completeness
        ("aged_receivables", "list-aged-receivables-by-contact", {}),  # Fetched per contact (requires contactId)
        ("aged_payables", "list-aged-payables-by-contact", {}),  # Fetched per contact (requires contactId)
        
        # Tracking (optional)
        ("tracking_categories", "list-tracking-categories", {}),
    ]
    
    # Paginated endpoints (need to fetch all pages)
    PAGINATED_ENDPOINTS = {
        "list-bank-transactions",
        "list-manual-journals",
        "list-invoices",
        "list-payments",
        "list-credit-notes",
        "list-contacts",
    }
    
    # Aged receivables/payables will be fetched per contact after contacts are loaded
    AGED_REPORTS_REQUIRE_CONTACTS = True
    
    def __init__(self, mcp_client: XeroMCPClient, use_cache: bool = True):
        self.mcp_client = mcp_client
        self.collected_data: Dict[str, Any] = {}
        self.data_completeness: Dict[str, bool] = {}
        self.use_cache = use_cache
        self.cache = DataCache() if use_cache else None
        self.progress_callback: Optional[Callable[[int, str], None]] = None
        
    def set_progress_callback(self, callback: Callable[[int, str], None]):
        """Set progress callback for data gathering."""
        self.progress_callback = callback
        
    async def gather_all(self) -> Tuple[Dict[str, Any], int]:
        """
        Exhaustively gather all data, handling pagination.
        
        Returns:
            Tuple of (collected_data, data_completeness_score)
        """
        logger.info("=" * 80)
        logger.info("Starting data gathering for payroll risk assessment")
        logger.info("=" * 80)
        
        # Fun messages for different data sources
        fun_messages = {
            "organisation": "🏢 Getting to know your organization...",
            "accounts": "📊 Scanning your chart of accounts...",
            "bank_transactions": "💰 Counting the cash (this might take a moment)...",
            "manual_journals": "📝 Reading through your journal entries...",
            "invoices": "📄 Checking who owes you money...",
            "payments": "💳 Tracking incoming payments...",
            "credit_notes": "📋 Reviewing credit notes...",
            "balance_sheet": "⚖️ Balancing the books...",
            "profit_loss": "📈 Calculating profit and loss...",
            "trial_balance": "🔍 Running trial balance check...",
            "contacts": "👥 Loading your contact list...",
            "tracking_categories": "🏷️ Organizing tracking categories...",
        }
        
        total_sources = len([s for s in self.DATA_SOURCES if s[0] not in ["aged_receivables", "aged_payables"]])
        completed_sources = 0
        data_gathering_progress_base = 5  # Start at 5%
        data_gathering_progress_max = 60  # Data gathering takes up to 60% of total progress
        
        if self.progress_callback:
            self.progress_callback(data_gathering_progress_base, "🚀 Starting data collection from Xero...")
        
        for source_name, tool_name, params in self.DATA_SOURCES:
            # Skip aged receivables/payables - they're fetched per contact after contacts are gathered
            if source_name in ["aged_receivables", "aged_payables"]:
                logger.debug(f"Skipping {source_name} - will be fetched per contact after contacts are gathered")
                continue
                
            try:
                # Update progress
                progress_pct = data_gathering_progress_base + int((completed_sources / total_sources) * (data_gathering_progress_max - data_gathering_progress_base))
                fun_message = fun_messages.get(source_name, f"📦 Fetching {source_name}...")
                if self.progress_callback:
                    self.progress_callback(progress_pct, fun_message)
                
                logger.info(f"\n{'='*80}")
                logger.info(f"Processing data source: {source_name}")
                logger.info(f"Tool: {tool_name}")
                logger.info(f"Parameters: {params}")
                logger.info(f"{'='*80}")
                
                # Check cache first
                if self.use_cache and self.cache:
                    cached_data = self.cache.get(source_name)
                    if cached_data is not None:
                        logger.info(f"✓ Using cached data for {source_name}")
                        data = cached_data.get("data") if isinstance(cached_data, dict) else cached_data
                        # Mark as complete if we have cached data
                        if data:
                            self.collected_data[source_name] = data
                            self.data_completeness[source_name] = True
                            completed_sources += 1
                            logger.info(f"✓ Successfully loaded {source_name} from cache: {len(data) if isinstance(data, list) else 1} items")
                            if self.progress_callback:
                                progress_pct = data_gathering_progress_base + int((completed_sources / total_sources) * (data_gathering_progress_max - data_gathering_progress_base))
                                self.progress_callback(progress_pct, f"✅ {fun_message} (cached)")
                        else:
                            self.collected_data[source_name] = None
                            self.data_completeness[source_name] = False
                            logger.warning(f"✗ Cached data for {source_name} is empty")
                        continue
                
                logger.info(f"Fetching {source_name} using {tool_name}...")
                
                if tool_name in self.PAGINATED_ENDPOINTS:
                    # Handle pagination
                    logger.info(f"Using paginated gathering for {tool_name}")
                    data = await self._gather_paginated(tool_name, params)
                else:
                    # Single call
                    logger.info(f"Using single call gathering for {tool_name}")
                    data = await self._gather_single(tool_name, params)
                
                # Log raw response for debugging
                logger.info(f"Raw response type: {type(data)}")
                if isinstance(data, dict):
                    logger.info(f"Response keys: {list(data.keys())}")
                elif isinstance(data, list):
                    logger.info(f"Response list length: {len(data)}")
                    if len(data) > 0:
                        logger.info(f"First item type: {type(data[0])}")
                        if isinstance(data[0], dict):
                            logger.info(f"First item keys: {list(data[0].keys())[:10]}")
                else:
                    logger.info(f"Response value (first 500 chars): {str(data)[:500]}")
                
                # Cache the data after fetching
                if self.use_cache and self.cache and data is not None:
                    self.cache.set(source_name, data)
                    logger.info(f"✓ Cached data for {source_name}")
                
                # Check if data contains error messages
                if data:
                    # Check if the data contains error indicators
                    data_text = str(data).lower()
                    has_error = any(indicator in data_text for indicator in [
                        "error", "401", "unauthorized", "authentication", "failed", "status code"
                    ])
                    
                    if has_error:
                        logger.warning(f"✗ {source_name} contains error indicators")
                        logger.warning(f"Error preview: {str(data)[:500]}")
                        self.collected_data[source_name] = data  # Still store it so LLM can see the error
                        self.data_completeness[source_name] = False
                    else:
                        self.collected_data[source_name] = data
                        self.data_completeness[source_name] = True
                        completed_sources += 1
                        item_count = len(data) if isinstance(data, list) else 1
                        logger.info(f"✓ Successfully gathered {source_name}: {item_count} items")
                        if self.progress_callback:
                            progress_pct = data_gathering_progress_base + int((completed_sources / total_sources) * (data_gathering_progress_max - data_gathering_progress_base))
                            self.progress_callback(progress_pct, f"✅ {fun_message}")
                else:
                    self.collected_data[source_name] = None
                    self.data_completeness[source_name] = False
                    logger.warning(f"✗ No data returned for {source_name}")
                    
            except Exception as e:
                logger.error(f"✗ Error gathering {source_name}: {str(e)}", exc_info=True)
                self.collected_data[source_name] = None
                self.data_completeness[source_name] = False
        
        # After gathering contacts, fetch aged receivables and payables for each contact
        # Check cache first for aged reports
        need_to_fetch_aged_reports = True
        if self.use_cache and self.cache:
            cached_ar = self.cache.get("aged_receivables")
            cached_ap = self.cache.get("aged_payables")
            
            # Load from cache if available
            if cached_ar is not None:
                logger.info("✓ Using cached aged receivables data")
                self.collected_data["aged_receivables"] = cached_ar.get("data") if isinstance(cached_ar, dict) else cached_ar
                if self.collected_data["aged_receivables"]:
                    self.data_completeness["aged_receivables"] = True
                    logger.info(f"✓ Loaded aged receivables from cache: {len(self.collected_data['aged_receivables']) if isinstance(self.collected_data['aged_receivables'], list) else 0} contacts")
                else:
                    self.data_completeness["aged_receivables"] = False
            
            if cached_ap is not None:
                logger.info("✓ Using cached aged payables data")
                self.collected_data["aged_payables"] = cached_ap.get("data") if isinstance(cached_ap, dict) else cached_ap
                if self.collected_data["aged_payables"]:
                    self.data_completeness["aged_payables"] = True
                    logger.info(f"✓ Loaded aged payables from cache: {len(self.collected_data['aged_payables']) if isinstance(self.collected_data['aged_payables'], list) else 0} contacts")
                else:
                    self.data_completeness["aged_payables"] = False
            
            # Only skip fetching if BOTH are in cache
            if cached_ar is not None and cached_ap is not None:
                need_to_fetch_aged_reports = False
        
        # Fetch from MCP if not in cache or cache disabled
        if need_to_fetch_aged_reports and self.collected_data.get("contacts"):
            if self.progress_callback:
                self.progress_callback(55, "📊 Analyzing receivables and payables by contact...")
            logger.info(f"\n{'='*80}")
            logger.info("Fetching aged receivables and payables for contacts")
            logger.info(f"{'='*80}")
            await self._gather_aged_reports_by_contact()
            if self.progress_callback:
                self.progress_callback(58, "✅ Finished analyzing receivables and payables")
        elif not self.collected_data.get("contacts"):
            logger.warning("No contacts available - cannot fetch aged receivables/payables")
            self.collected_data["aged_receivables"] = None
            self.collected_data["aged_payables"] = None
            self.data_completeness["aged_receivables"] = False
            self.data_completeness["aged_payables"] = False
        
        # Extract and calculate payroll amounts from manual journals
        if self.progress_callback:
            self.progress_callback(58, "🔍 Hunting for payroll patterns in your journals...")
        logger.info(f"\n{'='*80}")
        logger.info("Extracting payroll information from manual journals")
        logger.info(f"{'='*80}")
        payroll_info = await self._extract_payroll_amounts_from_journals()
        if payroll_info:
            self.collected_data["payroll_info"] = payroll_info
            logger.info(f"✓ Extracted payroll information: {payroll_info}")
            if self.progress_callback:
                self.progress_callback(60, "✅ Found payroll patterns!")
        else:
            logger.warning("✗ Could not extract payroll information from manual journals")
            if self.progress_callback:
                self.progress_callback(60, "⚠️ No clear payroll patterns found")
        
        # Calculate completeness score
        completeness_score = int((completed_sources / total_sources) * 100)
        logger.info(f"\n{'='*80}")
        logger.info(f"Data gathering complete. Completeness: {completeness_score}% ({completed_sources}/{total_sources})")
        logger.info(f"{'='*80}")
        
        if self.progress_callback:
            self.progress_callback(60, "✅ Data collection complete! Time to analyze...")
        
        return self.collected_data, completeness_score
    
    async def _gather_single(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """Gather data from a single API call."""
        try:
            logger.debug(f"Calling MCP tool: {tool_name} with params: {params}")
            result = await self.mcp_client.call_tool(tool_name, params)
            logger.debug(f"MCP tool {tool_name} returned result type: {type(result)}")
            
            # Parse text response if needed
            if isinstance(result, dict):
                logger.debug(f"Result is dict with keys: {list(result.keys())}")
                if "content" in result:
                    content = result["content"]
                    logger.debug(f"Content type: {type(content)}, length: {len(content) if isinstance(content, list) else 'N/A'}")
                    if isinstance(content, list) and len(content) > 0:
                        # Log first content item for debugging
                        if len(content) > 0:
                            first_item = content[0]
                            logger.debug(f"First content item type: {type(first_item)}")
                            if isinstance(first_item, dict):
                                logger.debug(f"First content item keys: {list(first_item.keys())}")
                                if "text" in first_item:
                                    text_preview = str(first_item["text"])[:200]
                                    logger.debug(f"First content item text preview: {text_preview}")
                        # Return the content array for further processing
                        return content
                    return result
                else:
                    logger.debug(f"No 'content' key in result, returning full result")
                    return result
            
            logger.debug(f"Result is not a dict, returning as-is: {type(result)}")
            return result
        except Exception as e:
            logger.error(f"Error in single gather for {tool_name}: {str(e)}", exc_info=True)
            return None
    
    async def _gather_paginated(self, tool_name: str, initial_params: Dict[str, Any]) -> List[Any]:
        """Gather data from paginated endpoints."""
        all_items = []
        page = initial_params.get("page", 1)
        max_pages = 100  # Safety limit
        
        try:
            while page <= max_pages:
                # For manual journals, page is optional - only include if > 1
                params = {**initial_params}
                if tool_name == "list-manual-journals":
                    # Manual journals supports optional page parameter
                    if page > 1:
                        params["page"] = page
                else:
                    # Other endpoints require page parameter
                    params["page"] = page
                
                logger.debug(f"Fetching {tool_name} page {page}")
                
                result = await self.mcp_client.call_tool(tool_name, params)
                
                # Parse response
                items = self._parse_paginated_response(result)
                
                if not items:
                    logger.debug(f"No items on page {page}, stopping pagination")
                    break
                
                all_items.extend(items)
                
                # If we got less than expected (typically 10-100 per page), we're done
                if len(items) < 10:
                    logger.debug(f"Got {len(items)} items on page {page}, assuming last page")
                    break
                
                page += 1
            
            logger.info(f"Collected {len(all_items)} total items from {tool_name} across {page-1} pages")
            return all_items
            
        except Exception as e:
            logger.error(f"Error in paginated gather for {tool_name}: {str(e)}")
            return all_items  # Return what we have so far
    
    def _parse_paginated_response(self, result: Any) -> List[Any]:
        """Parse paginated response from MCP server."""
        if not isinstance(result, dict):
            return []
        
        if "content" in result:
            content = result["content"]
            if isinstance(content, list):
                # Filter out summary messages
                items = [
                    item for item in content
                    if isinstance(item, dict) and item.get("type") == "text"
                ]
                return items
        
        return []
    
    async def _gather_aged_reports_by_contact(self):
        """Gather aged receivables and payables for all contacts."""
        contacts = self.collected_data.get("contacts")
        if not contacts:
            logger.warning("No contacts available, skipping aged reports")
            return
        
        # Extract contact IDs from contacts
        contact_ids = []
        import re
        for contact_item in contacts:
            if isinstance(contact_item, dict):
                # Try to extract contact ID from various possible formats
                contact_id = None
                if "ContactID" in contact_item:
                    contact_id = contact_item["ContactID"]
                elif "contactId" in contact_item:
                    contact_id = contact_item["contactId"]
                elif "id" in contact_item:
                    contact_id = contact_item["id"]
                elif "text" in contact_item:
                    # Parse from text if needed
                    text = contact_item["text"]
                    # Try multiple patterns to find Contact ID
                    # Pattern 1: "ID: xxxxx"
                    match = re.search(r'ID[:\s]+([a-f0-9-]{36})', text, re.IGNORECASE)
                    if match:
                        contact_id = match.group(1)
                    else:
                        # Pattern 2: "ContactID: xxxxx"
                        match = re.search(r'ContactID[:\s]+([a-f0-9-]+)', text, re.IGNORECASE)
                        if match:
                            contact_id = match.group(1)
                        else:
                            # Pattern 3: "Contact: Name (xxxxx)"
                            match = re.search(r'Contact[:\s]+[^(]+\(([a-f0-9-]{36})\)', text, re.IGNORECASE)
                            if match:
                                contact_id = match.group(1)
                
                if contact_id:
                    contact_ids.append(contact_id)
                    logger.debug(f"Extracted contact ID: {contact_id[:8]}...")
        
        logger.info(f"Found {len(contact_ids)} contact IDs from {len(contacts)} contacts")
        
        if not contact_ids:
            logger.warning("Could not extract any contact IDs, skipping aged reports")
            return
        
        # Limit to first 50 contacts to avoid too many API calls
        if len(contact_ids) > 50:
            logger.info(f"Limiting to first 50 contacts (out of {len(contact_ids)})")
            contact_ids = contact_ids[:50]
        
        # Gather aged receivables
        aged_receivables_all = []
        aged_payables_all = []
        
        for i, contact_id in enumerate(contact_ids, 1):
            try:
                # Add delay between requests to avoid rate limiting
                if i > 1:
                    await asyncio.sleep(0.5)  # 500ms delay between contacts (increased from 150ms)
                
                # Fetch aged receivables with retry logic
                logger.info(f"Fetching aged receivables for contact {i}/{len(contact_ids)}: {contact_id[:8]}...")
                ar_result = await self._fetch_with_retry("list-aged-receivables-by-contact", {"contactId": contact_id})
                if ar_result and not self._is_error_response(ar_result):
                    aged_receivables_all.append({
                        "contactId": contact_id,
                        "data": ar_result
                    })
                    logger.info(f"✓ Got aged receivables for contact {contact_id[:8]}...")
                else:
                    # Store error response for debugging
                    if ar_result:
                        aged_receivables_all.append({
                            "contactId": contact_id,
                            "data": ar_result
                        })
                        logger.warning(f"✗ Error in aged receivables for contact {contact_id[:8]}...")
                    else:
                        logger.warning(f"✗ No aged receivables data for contact {contact_id[:8]}...")
                
                # Delay between receivables and payables for same contact
                await asyncio.sleep(0.3)  # 300ms delay (increased from 100ms)
                
                # Fetch aged payables with retry logic
                logger.info(f"Fetching aged payables for contact {i}/{len(contact_ids)}: {contact_id[:8]}...")
                ap_result = await self._fetch_with_retry("list-aged-payables-by-contact", {"contactId": contact_id})
                if ap_result and not self._is_error_response(ap_result):
                    aged_payables_all.append({
                        "contactId": contact_id,
                        "data": ap_result
                    })
                    logger.info(f"✓ Got aged payables for contact {contact_id[:8]}...")
                else:
                    # Store error response for debugging
                    if ap_result:
                        aged_payables_all.append({
                            "contactId": contact_id,
                            "data": ap_result
                        })
                        logger.warning(f"✗ Error in aged payables for contact {contact_id[:8]}...")
                    else:
                        logger.warning(f"✗ No aged payables data for contact {contact_id[:8]}...")
                    
            except Exception as e:
                logger.error(f"Error fetching aged reports for contact {contact_id[:8]}...: {str(e)}")
                # Add longer delay on error to avoid rapid retries
                await asyncio.sleep(1.0)  # 1 second delay on error (increased from 200ms)
                continue
        
        # Store aggregated results and cache them
        if aged_receivables_all:
            self.collected_data["aged_receivables"] = aged_receivables_all
            self.data_completeness["aged_receivables"] = True
            # Cache the aged receivables data
            if self.use_cache and self.cache:
                self.cache.set("aged_receivables", aged_receivables_all)
                logger.info(f"✓ Cached aged receivables data")
            logger.info(f"✓ Collected aged receivables for {len(aged_receivables_all)} contacts")
        else:
            self.collected_data["aged_receivables"] = None
            self.data_completeness["aged_receivables"] = False
            logger.warning("✗ No aged receivables collected")
        
        if aged_payables_all:
            self.collected_data["aged_payables"] = aged_payables_all
            self.data_completeness["aged_payables"] = True
            # Cache the aged payables data
            if self.use_cache and self.cache:
                self.cache.set("aged_payables", aged_payables_all)
                logger.info(f"✓ Cached aged payables data")
            logger.info(f"✓ Collected aged payables for {len(aged_payables_all)} contacts")
        else:
            self.collected_data["aged_payables"] = None
            self.data_completeness["aged_payables"] = False
            logger.warning("✗ No aged payables collected")
    
    def _is_error_response(self, result: Any) -> bool:
        """Check if the response contains an error (e.g., HTTP 429 rate limit)."""
        if not result:
            return False
        
        # Check if result is a list of content items
        if isinstance(result, list):
            for item in result:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    # Check for error messages
                    if "Error listing" in text or "statusCode\":429" in text or "rate-limit-problem" in text:
                        return True
        
        # Check if result is a dict with error
        if isinstance(result, dict):
            if "error" in result:
                return True
            # Check content array for errors
            if "content" in result:
                content = result["content"]
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text = item.get("text", "")
                            if "Error listing" in text or "statusCode\":429" in text or "rate-limit-problem" in text:
                                return True
        
        return False
    
    def _extract_retry_after(self, result: Any) -> int:
        """Extract retry-after value from error response (in seconds)."""
        if not result:
            return 0
        
        import re
        import json
        
        # Search for retry-after in the response text
        text_to_search = ""
        if isinstance(result, list):
            for item in result:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_to_search += item.get("text", "") + "\n"
        elif isinstance(result, dict):
            if "content" in result:
                content = result["content"]
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text_to_search += item.get("text", "") + "\n"
        
        # Try to parse retry-after from JSON error response
        try:
            # Look for retry-after in the error JSON
            match = re.search(r'"retry-after":\s*"(\d+)"', text_to_search, re.IGNORECASE)
            if match:
                return int(match.group(1))
            
            # Also try to parse the full error JSON
            error_match = re.search(r'\{[^}]*"retry-after"[^}]*\}', text_to_search, re.IGNORECASE | re.DOTALL)
            if error_match:
                error_json = error_match.group(0)
                error_data = json.loads(error_json)
                if "retry-after" in error_data:
                    return int(error_data["retry-after"])
        except (json.JSONDecodeError, ValueError, KeyError):
            pass
        
        return 0
    
    async def _fetch_with_retry(self, tool_name: str, params: Dict[str, Any], max_retries: int = 3) -> Any:
        """Fetch data with retry logic that handles rate limiting."""
        
        for attempt in range(max_retries):
            try:
                result = await self._gather_single(tool_name, params)
                
                # Check if result contains a rate limit error
                if result and self._is_error_response(result):
                    # Extract retry-after value
                    retry_after = self._extract_retry_after(result)
                    
                    if retry_after > 0:
                        # Wait for the specified retry-after time, plus some buffer
                        wait_time = retry_after + 1  # Add 1 second buffer
                        logger.warning(f"Rate limit detected (429), waiting {wait_time}s before retry (attempt {attempt + 1}/{max_retries})...")
                        await asyncio.sleep(wait_time)
                        
                        # Retry the request
                        if attempt < max_retries - 1:
                            continue
                        else:
                            # Max retries reached, return the error response
                            logger.error(f"Rate limit error persisted after {max_retries} attempts")
                            return result
                    else:
                        # Rate limit error but no retry-after header, use exponential backoff
                        wait_time = (2 ** attempt) + 1  # 2s, 3s, 5s
                        logger.warning(f"Rate limit detected (429) but no retry-after header, waiting {wait_time}s before retry (attempt {attempt + 1}/{max_retries})...")
                        await asyncio.sleep(wait_time)
                        
                        if attempt < max_retries - 1:
                            continue
                        else:
                            logger.error(f"Rate limit error persisted after {max_retries} attempts")
                            return result
                
                # No error, return result
                return result
                
            except Exception as e:
                logger.error(f"Error fetching {tool_name} (attempt {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + 1  # Exponential backoff
                    logger.info(f"Waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Failed to fetch {tool_name} after {max_retries} attempts")
                    return None
        
        return None
    
    def _extract_text_from_content(self, content: Any) -> str:
        """Extract text from MCP content array (helper for payroll extraction)."""
        if isinstance(content, list):
            texts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    texts.append(item.get("text", ""))
            return "\n".join(texts)
        return str(content) if content else ""
    
    async def _extract_journal_lines_from_xero_api(
        self, 
        manual_journal_id: str
    ) -> List[Dict[str, Any]]:
        """
        Fetch journal line items directly from Xero API to bypass MCP server bug.
        
        Args:
            manual_journal_id: The manual journal ID to fetch
            
        Returns:
            List of journal line items with accountCode, lineAmount, description, taxType
        """
        journal_lines = []
        
        try:
            # Get access token from MCP client
            access_token = getattr(self.mcp_client, 'bearer_token', None)
            if not access_token:
                logger.warning("No bearer token available for Xero API call")
                return journal_lines
            
            # Get tenant_id from MCP client first, fall back to extracting from collected data
            tenant_id = getattr(self.mcp_client, 'tenant_id', None)
            if not tenant_id:
                tenant_id = self._extract_tenant_id_from_collected_data()
            if not tenant_id:
                logger.warning("No tenant ID available for Xero API call")
                return journal_lines
            
            xero_client = XeroClient()
            
            # Fetch manual journal directly from Xero API
            result = xero_client.get_manual_journal(access_token, tenant_id, manual_journal_id)
            
            # Extract journal lines from Xero API response
            if isinstance(result, dict) and "ManualJournals" in result:
                manual_journals = result["ManualJournals"]
                if manual_journals and len(manual_journals) > 0:
                    journal = manual_journals[0]
                    if "JournalLines" in journal:
                        for line in journal["JournalLines"]:
                            line_data = {
                                "lineAmount": float(line.get("LineAmount", 0)),
                                "accountCode": line.get("AccountCode", ""),
                                "description": line.get("Description", ""),
                                "taxType": line.get("TaxType", "NONE")
                            }
                            journal_lines.append(line_data)
                            logger.debug(f"Extracted line: Account {line_data['accountCode']}, Amount {line_data['lineAmount']}")
            
            logger.info(f"Fetched {len(journal_lines)} journal lines from Xero API for journal {manual_journal_id[:8]}...")
            
        except Exception as e:
            logger.error(f"Error fetching journal from Xero API: {str(e)}", exc_info=True)
        
        return journal_lines
    
    def _extract_tenant_id_from_collected_data(self) -> Optional[str]:
        """Extract tenant/organization ID from collected organisation data."""
        org_data = self.collected_data.get("organisation")
        if not org_data:
            return None
        
        if isinstance(org_data, list):
            # Text response from MCP
            for item in org_data:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    if "Organisation ID:" in text:
                        # Extract ID from text
                        lines = text.split("\n")
                        for line in lines:
                            if "Organisation ID:" in line:
                                org_id = line.split("Organisation ID:")[-1].strip()
                                # Remove any trailing text after the ID
                                org_id = org_id.split("||")[0].strip()
                                return org_id
        elif isinstance(org_data, dict):
            return org_data.get("organisationID", "")
        
        return None
    
    def _extract_journal_lines_from_content(self, manual_journals: List[Any], current_index: int, journal_id: str) -> List[Dict[str, Any]]:
        """
        Extract journal line items from the content array when [object Object] is found.
        Looks at surrounding items in the array to find the actual line item data.
        
        Args:
            manual_journals: The full manual journals content array
            current_index: Index of the current journal item
            journal_id: The journal ID we're looking for
            
        Returns:
            List of journal line items with account codes and amounts
        """
        journal_lines = []
        
        # Look ahead in the array for journal line items related to this journal
        # The MCP server may have placed them as separate content items
        for i in range(current_index + 1, min(current_index + 10, len(manual_journals))):
            item = manual_journals[i]
            if isinstance(item, dict) and item.get("type") == "text":
                line_text = item.get("text", "")
                
                # Check if this looks like a journal line item
                if "Line Amount:" in line_text or "Account Code:" in line_text:
                    # Parse the line item
                    line_data = {}
                    
                    # Extract line amount
                    amount_match = re.search(r'Line Amount[:\s]+([-]?\d+\.?\d*)', line_text, re.IGNORECASE)
                    if amount_match:
                        try:
                            line_data["lineAmount"] = float(amount_match.group(1))
                        except ValueError:
                            pass
                    
                    # Extract account code
                    account_match = re.search(r'Account Code[:\s]+(\d+)', line_text, re.IGNORECASE)
                    if account_match:
                        line_data["accountCode"] = account_match.group(1)
                    
                    # Extract description
                    desc_match = re.search(r'Description[:\s]+([^\n]+)', line_text, re.IGNORECASE)
                    if desc_match:
                        line_data["description"] = desc_match.group(1).strip()
                    
                    if line_data:
                        journal_lines.append(line_data)
                elif "Manual Journal ID:" in line_text:
                    # We've hit the next journal, stop looking
                    break
        
        return journal_lines
    
    async def _extract_payroll_amounts_from_journals(self) -> Optional[Dict[str, Any]]:
        """
        Extract payroll amounts from manual journal entries.
        Returns the highest of the last 4 payroll amounts.
        """
        manual_journals = self.collected_data.get("manual_journals")
        if not manual_journals:
            logger.warning("No manual journals available for payroll extraction")
            return None
        
        import re
        
        payroll_entries = []
        
        # Parse manual journals to find payroll entries
        for idx, item in enumerate(manual_journals):
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                
                # Check if this is a payroll journal entry
                if "Bi-weekly Payroll" in text or "Payroll" in text or "Wages" in text or "Salaries" in text:
                    # Extract journal ID
                    journal_id_match = re.search(r'Manual Journal ID[:\s]+([a-f0-9-]+)', text, re.IGNORECASE)
                    if not journal_id_match:
                        continue
                    
                    journal_id = journal_id_match.group(1)
                    
                    # Extract date
                    date_match = re.search(r'Date[:\s]+([^\n]+)', text, re.IGNORECASE)
                    if not date_match:
                        continue
                    
                    date_str = date_match.group(1).strip()
                    
                    # Extract status (only POSTED entries)
                    status_match = re.search(r'Status[:\s]+(POSTED|VOIDED|DRAFT)', text, re.IGNORECASE)
                    if not status_match or status_match.group(1).upper() != "POSTED":
                        logger.debug(f"Skipping journal {journal_id[:8]}... - status is not POSTED")
                        continue
                    
                    # Extract description
                    desc_match = re.search(r'Description[:\s]+([^\n]+)', text, re.IGNORECASE)
                    description = desc_match.group(1).strip() if desc_match else ""
                    
                    # Try to extract line amounts from the text or surrounding content
                    journal_lines = []
                    if "[object Object]" in text:
                        # The MCP server has a bug where journal lines are objects that get stringified to [object Object]
                        # First, try to fetch directly from Xero API (bypasses MCP server bug)
                        logger.info(f"Found [object Object] in journal {journal_id[:8]}..., fetching from Xero API to get line items...")
                        try:
                            # Try Xero API first
                            journal_lines = await self._extract_journal_lines_from_xero_api(journal_id)
                            
                            if journal_lines:
                                logger.info(f"✓ Successfully fetched {len(journal_lines)} journal lines from Xero API for {journal_id[:8]}...")
                            else:
                                # Fallback to MCP server (though it likely has the same bug)
                                logger.warning(f"Xero API returned no lines, trying MCP server as fallback for {journal_id[:8]}...")
                                detailed_result = await self._gather_single("list-manual-journals", {"manualJournalId": journal_id})
                                if detailed_result:
                                    # First, check if journal lines are separate content items in the array
                                    if isinstance(detailed_result, list):
                                        for detail_item in detailed_result:
                                            if isinstance(detail_item, dict) and detail_item.get("type") == "text":
                                                detail_text = detail_item.get("text", "")
                                                # Check if this is a journal line item (has both Line Amount and Account Code)
                                                if "Line Amount:" in detail_text and "Account Code:" in detail_text:
                                                    line_data = {}
                                                    amount_match = re.search(r'Line Amount[:\s]+([-]?\d+\.?\d*)', detail_text, re.IGNORECASE)
                                                    account_match = re.search(r'Account Code[:\s]+(\d+)', detail_text, re.IGNORECASE)
                                                    if amount_match and account_match:
                                                        try:
                                                            line_data["lineAmount"] = float(amount_match.group(1))
                                                            line_data["accountCode"] = account_match.group(1)
                                                            # Extract description if available
                                                            desc_match = re.search(r'Description[:\s]+([^\n]+)', detail_text, re.IGNORECASE)
                                                            if desc_match:
                                                                line_data["description"] = desc_match.group(1).strip()
                                                            journal_lines.append(line_data)
                                                        except ValueError:
                                                            pass
                                    
                                    # If we didn't find lines in separate content items, parse from the combined text
                                    if not journal_lines:
                                        detailed_text = self._extract_text_from_content(detailed_result)
                                        
                                        if detailed_text:
                                            # Extract journal lines from the detailed text
                                            # The format should be multiple lines with "Line Amount:" and "Account Code:"
                                            lines = detailed_text.split("\n")
                                            current_line_data = {}
                                            
                                            for line in lines:
                                                # Look for Line Amount
                                                amount_match = re.search(r'Line Amount[:\s]+([-]?\d+\.?\d*)', line, re.IGNORECASE)
                                                if amount_match:
                                                    try:
                                                        current_line_data["lineAmount"] = float(amount_match.group(1))
                                                    except ValueError:
                                                        pass
                                                
                                                # Look for Account Code
                                                account_match = re.search(r'Account Code[:\s]+(\d+)', line, re.IGNORECASE)
                                                if account_match:
                                                    current_line_data["accountCode"] = account_match.group(1)
                                                
                                                # Look for Description
                                                desc_match = re.search(r'Description[:\s]+([^\n]+)', line, re.IGNORECASE)
                                                if desc_match:
                                                    current_line_data["description"] = desc_match.group(1).strip()
                                                
                                                # If we have both amount and account code, we have a complete line item
                                                if "lineAmount" in current_line_data and "accountCode" in current_line_data:
                                                    journal_lines.append(current_line_data.copy())
                                                    current_line_data = {}  # Reset for next line item
                                        else:
                                            detailed_text = None
                                    else:
                                        # We found lines in content items, get the text for other fields
                                        detailed_text = self._extract_text_from_content(detailed_result)
                                    
                                    # Use the extracted data from MCP (fallback)
                                    if journal_lines:
                                        if detailed_text:
                                            text = detailed_text
                                        logger.info(f"✓ Extracted {len(journal_lines)} journal lines from MCP detailed entry for {journal_id[:8]}...")
                                    elif detailed_text:
                                        # Check if detailed text still has [object Object] - if so, the MCP server has the same bug
                                        if "[object Object]" in detailed_text:
                                            logger.warning(f"MCP detailed entry also contains [object Object] for journal {journal_id[:8]}... - MCP server bug persists")
                                            # Try to extract what we can from the text that's available
                                            text = detailed_text
                                        else:
                                            # Use the detailed text for parsing
                                            text = detailed_text
                                            logger.debug(f"Using MCP detailed text for parsing for {journal_id[:8]}...")
                                    else:
                                        logger.warning(f"MCP detailed entry returned no text content for journal {journal_id[:8]}...")
                                else:
                                    logger.warning(f"MCP detailed entry returned no result for journal {journal_id[:8]}...")
                        except Exception as e:
                            logger.warning(f"Could not fetch journal entry details for {journal_id[:8]}...: {str(e)}")
                            # Continue with original text - will try to parse what we can
                    
                    # Extract line amounts from journal lines or text
                    line_amounts = []
                    account_477_amount = None
                    
                    # First, try to use the extracted journal lines
                    if journal_lines:
                        for line in journal_lines:
                            if "lineAmount" in line:
                                amount = abs(float(line["lineAmount"]))
                                line_amounts.append(amount)
                                
                                # Check if this is account code 477 (Wages and Salaries)
                                if line.get("accountCode") == "477":
                                    account_477_amount = amount
                                    logger.debug(f"Found Account Code 477 with amount: ${account_477_amount:.2f}")
                    
                    # If we didn't get lines from structured data, parse from text
                    if not journal_lines:
                        # Parse line by line to find amounts and account codes
                        lines = text.split("\n")
                        current_line_amount = None
                        for line in lines:
                            # Look for "Line Amount:" pattern
                            amount_match = re.search(r'Line Amount[:\s]+([-]?\d+\.?\d*)', line, re.IGNORECASE)
                            if amount_match:
                                try:
                                    current_line_amount = float(amount_match.group(1))
                                    line_amounts.append(abs(current_line_amount))  # Use absolute value
                                except ValueError:
                                    continue
                            
                            # Look for Account Code 477 (Wages and Salaries) - this is the gross payroll
                            if current_line_amount is not None:
                                account_match = re.search(r'Account Code[:\s]+477', line, re.IGNORECASE)
                                if account_match:
                                    account_477_amount = abs(current_line_amount)
                                    logger.debug(f"Found Account Code 477 with amount: ${account_477_amount:.2f}")
                    
                    # If we found account 477 amount, use it (most reliable)
                    if account_477_amount and account_477_amount > 0:
                        gross_payroll = account_477_amount
                    elif line_amounts:
                        # Gross payroll is typically the largest positive amount (wages/salaries debit)
                        gross_payroll = max(line_amounts) if line_amounts else 0
                    else:
                        # Fallback: try to extract from account code 477 pattern (multiline)
                        wages_match = re.search(r'Account Code[:\s]+477[^\n]*\n[^\n]*Line Amount[:\s]+([-]?\d+\.?\d*)', text, re.IGNORECASE | re.MULTILINE)
                        if wages_match:
                            try:
                                gross_payroll = abs(float(wages_match.group(1)))
                            except ValueError:
                                gross_payroll = 0
                        else:
                            # Last resort: try to find any large positive amount (likely gross payroll)
                            # Look for amounts that are reasonable for payroll (e.g., > 100)
                            all_amounts = re.findall(r'[-]?\d+\.\d{2}', text)
                            if all_amounts:
                                try:
                                    amounts = [abs(float(a)) for a in all_amounts if abs(float(a)) > 50]  # Filter small amounts
                                    gross_payroll = max(amounts) if amounts else 0
                                except ValueError:
                                    gross_payroll = 0
                            else:
                                gross_payroll = 0
                    
                    if gross_payroll > 0:
                        # Parse date string to datetime for sorting
                        try:
                            # Try to parse the date string (format may vary)
                            # Common formats: "Wed Dec 31 2025 05:30:00 GMT+0530" or "2025-12-31"
                            if "GMT" in date_str or "(" in date_str:
                                # Extract just the date part before timezone
                                date_part = date_str.split("(")[0].strip() if "(" in date_str else date_str.split("GMT")[0].strip()
                                # Try parsing with common formats
                                parsed_date = None
                                for fmt in ["%a %b %d %Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]:
                                    try:
                                        parsed_date = datetime.strptime(date_part.strip(), fmt)
                                        break
                                    except ValueError:
                                        continue
                                if not parsed_date:
                                    # Fallback: use current date
                                    parsed_date = datetime.now()
                            else:
                                parsed_date = datetime.strptime(date_str.strip(), "%Y-%m-%d")
                            
                            payroll_entries.append({
                                "journal_id": journal_id,
                                "date": parsed_date,
                                "date_str": date_str,
                                "description": description,
                                "gross_payroll": gross_payroll
                            })
                            logger.info(f"Found payroll entry: {date_str} - ${gross_payroll:.2f}")
                        except Exception as e:
                            logger.warning(f"Could not parse date '{date_str}' for journal {journal_id[:8]}...: {str(e)}")
                            continue
        
        if not payroll_entries:
            logger.warning("No POSTED payroll entries found in manual journals (only POSTED journals are used, VOIDED and DRAFT are excluded)")
            return None
        
        # Sort by date (most recent first)
        payroll_entries.sort(key=lambda x: x["date"], reverse=True)
        
        # Get last 4 payroll entries
        last_4 = payroll_entries[:4]
        
        if not last_4:
            return None
        
        # Calculate highest amount
        highest_amount = max(entry["gross_payroll"] for entry in last_4)
        
        # Calculate average for reference
        avg_amount = sum(entry["gross_payroll"] for entry in last_4) / len(last_4)
        
        # Determine cadence (bi-weekly, monthly, etc.)
        cadence = "Unknown"
        if len(last_4) >= 2:
            # Calculate average days between payrolls
            days_between = []
            for i in range(len(last_4) - 1):
                delta = (last_4[i]["date"] - last_4[i+1]["date"]).days
                days_between.append(delta)
            
            if days_between:
                avg_days = sum(days_between) / len(days_between)
                if 13 <= avg_days <= 15:
                    cadence = "Bi-weekly"
                elif 28 <= avg_days <= 31:
                    cadence = "Monthly"
                elif 6 <= avg_days <= 8:
                    cadence = "Weekly"
                else:
                    cadence = f"Every {int(avg_days)} days"
        
        # Predict next payroll date (improved logic)
        next_payroll_date = None
        if len(last_4) >= 2:
            # Use the most recent date as base
            latest_date = last_4[0]["date"]
            
            # Calculate average interval from all available pairs for better accuracy
            intervals = []
            for i in range(len(last_4) - 1):
                delta = (last_4[i]["date"] - last_4[i+1]["date"]).days
                intervals.append(delta)
            
            if intervals:
                # Use average interval for prediction
                avg_interval = sum(intervals) / len(intervals)
                predicted_date = latest_date + timedelta(days=int(avg_interval))
                
                # Adjust to next business day if it falls on weekend
                # Simple adjustment: if Saturday (5) or Sunday (6), move to Monday
                weekday = predicted_date.weekday()
                if weekday == 5:  # Saturday
                    predicted_date += timedelta(days=2)
                elif weekday == 6:  # Sunday
                    predicted_date += timedelta(days=1)
                
                next_payroll_date = predicted_date.strftime("%Y-%m-%d")
                logger.info(f"Predicted next payroll date: {next_payroll_date} (based on {len(intervals)} intervals, avg {avg_interval:.1f} days)")
            else:
                # Fallback: use interval between last 2 entries
                previous_date = last_4[1]["date"]
                interval_days = (latest_date - previous_date).days
                predicted_date = latest_date + timedelta(days=interval_days)
                
                # Adjust for weekends
                weekday = predicted_date.weekday()
                if weekday == 5:  # Saturday
                    predicted_date += timedelta(days=2)
                elif weekday == 6:  # Sunday
                    predicted_date += timedelta(days=1)
                
                next_payroll_date = predicted_date.strftime("%Y-%m-%d")
                logger.info(f"Predicted next payroll date: {next_payroll_date} (based on last interval: {interval_days} days)")
        elif len(last_4) == 1:
            # Only one entry - use cadence hint from description or default to bi-weekly
            entry = last_4[0]
            desc = entry.get("description", "").lower()
            if "bi-weekly" in desc or "biweekly" in desc:
                predicted_date = entry["date"] + timedelta(days=14)
            elif "monthly" in desc:
                predicted_date = entry["date"] + timedelta(days=30)
            elif "weekly" in desc:
                predicted_date = entry["date"] + timedelta(days=7)
            else:
                # Default to bi-weekly if no hint
                predicted_date = entry["date"] + timedelta(days=14)
            
            # Adjust for weekends
            weekday = predicted_date.weekday()
            if weekday == 5:  # Saturday
                predicted_date += timedelta(days=2)
            elif weekday == 6:  # Sunday
                predicted_date += timedelta(days=1)
            
            next_payroll_date = predicted_date.strftime("%Y-%m-%d")
            logger.info(f"Predicted next payroll date: {next_payroll_date} (based on single entry and description hint)")
        
        result = {
            "last_4_payroll_entries": [
                {
                    "date": entry["date_str"],
                    "amount": entry["gross_payroll"],
                    "journal_id": entry["journal_id"]
                }
                for entry in last_4
            ],
            "highest_amount": highest_amount,
            "average_amount": avg_amount,
            "cadence": cadence,
            "next_payroll_date": next_payroll_date,
            "total_entries_found": len(payroll_entries)
        }
        
        logger.info(f"Payroll Analysis:")
        logger.info(f"  - Found {len(payroll_entries)} total payroll entries")
        logger.info(f"  - Last 4 amounts: {[f'${e["gross_payroll"]:.2f}' for e in last_4]}")
        logger.info(f"  - Highest amount: ${highest_amount:.2f}")
        logger.info(f"  - Average amount: ${avg_amount:.2f}")
        logger.info(f"  - Cadence: {cadence}")
        logger.info(f"  - Next payroll date (predicted): {next_payroll_date}")
        
        return result
    
    def get_missing_critical_data(self) -> List[str]:
        """Get list of missing critical data sources."""
        critical_sources = ["organisation", "accounts"]
        missing = [
            source for source in critical_sources
            if not self.data_completeness.get(source, False)
        ]
        return missing

