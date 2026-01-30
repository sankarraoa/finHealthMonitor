"""MCP client for communicating with Xero MCP Server via stdio."""
import subprocess
import json
import asyncio
import os
from typing import Dict, Any, Optional, List, Callable
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class XeroMCPClient:
    """Client for interacting with Xero MCP Server via stdio."""
    
    def __init__(self, mcp_server_path: Optional[str] = None, bearer_token: Optional[str] = None, tenant_id: Optional[str] = None):
        """
        Initialize MCP client.
        
        Args:
            mcp_server_path: Path to the MCP server executable
            bearer_token: Optional bearer token for authentication (takes precedence)
            tenant_id: Optional tenant/organization ID to use for API calls
        """
        # Default to the installed MCP server in the project
        if mcp_server_path is None:
            project_root = Path(__file__).parent.parent
            mcp_server_path = project_root / "xero-mcp-server" / "dist" / "index.js"
        
        self.mcp_server_path = str(mcp_server_path)
        self.process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._initialized = False
        self._env = os.environ.copy()
        self.bearer_token = bearer_token
        self.tenant_id = tenant_id
        
        logger.info(f"Initializing XeroMCPClient with server path: {self.mcp_server_path}")
        if tenant_id:
            logger.info(f"Using tenant_id: {tenant_id}")
        
        # Check if MCP server file exists
        if not os.path.exists(self.mcp_server_path):
            error_msg = (
                f"MCP server not found at: {self.mcp_server_path}. "
                "Please ensure the xero-mcp-server is built. "
                "Run 'npm run build' in the xero-mcp-server directory."
            )
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        logger.info(f"MCP server file exists: {os.path.exists(self.mcp_server_path)}")
        
        # Set Xero credentials from config
        from app.config import config
        if bearer_token:
            # Use bearer token if provided (for runtime auth)
            self._env["XERO_CLIENT_BEARER_TOKEN"] = bearer_token
            logger.info("Using bearer token for authentication")
        else:
            # Otherwise use client ID/secret (for custom connections)
            self._env["XERO_CLIENT_ID"] = config.XERO_CLIENT_ID
            self._env["XERO_CLIENT_SECRET"] = config.XERO_CLIENT_SECRET
            logger.info("Using client ID/secret for authentication")
        
        # Set tenant_id if provided
        if tenant_id:
            self._env["XERO_TENANT_ID"] = tenant_id
            logger.info(f"Set XERO_TENANT_ID environment variable: {tenant_id}")
    
    async def _ensure_initialized(self):
        """Ensure MCP server process is running."""
        if not self._initialized:
            await self.initialize()
    
    async def initialize(self):
        """Initialize connection to MCP server by starting the process."""
        if self._initialized:
            logger.debug("MCP server already initialized, skipping")
            return
        
        try:
            logger.info("Starting MCP server subprocess...")
            # Start the MCP server as a subprocess
            self.process = subprocess.Popen(
                ["node", self.mcp_server_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._env,
                text=True,
                bufsize=0
            )
            logger.info(f"MCP server process started with PID: {self.process.pid}")
            
            # Send initialize request
            logger.info("Sending initialize request to MCP server...")
            init_request = {
                "jsonrpc": "2.0",
                "id": self._get_next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {}
                    },
                    "clientInfo": {
                        "name": "finhealthmonitor",
                        "version": "1.0.0"
                    }
                }
            }
            
            init_response = await self._send_request(init_request)
            logger.info(f"Initialize response received: {init_response.get('result', {}).get('serverInfo', {})}")
            
            # Send initialized notification (notifications don't return responses)
            logger.info("Sending initialized notification...")
            initialized_notification = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }
            await self._send_notification(initialized_notification)
            logger.info("Initialized notification sent")
            
            self._initialized = True
            logger.info("MCP server initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize MCP server: {str(e)}", exc_info=True)
            # Log stderr if process exists
            if self.process and self.process.stderr:
                try:
                    stderr_output = self.process.stderr.read()
                    if stderr_output:
                        logger.error(f"MCP server stderr: {stderr_output}")
                except Exception:
                    pass
            raise
    
    def _get_next_id(self) -> int:
        """Get next request ID."""
        self._request_id += 1
        return self._request_id
    
    async def _check_and_restart_process(self) -> bool:
        """
        Check if the MCP server process is alive and restart it if needed.
        
        Returns:
            True if process was restarted, False if it was already alive
        """
        if not self.process:
            logger.warning("MCP server process not started, initializing...")
            await self.initialize()
            return True
        
        # Check if process is still alive
        if self.process.poll() is not None:
            exit_code = self.process.returncode
            logger.warning(f"MCP server process exited with code: {exit_code}, restarting...")
            
            # Try to read stderr for error details
            try:
                stderr_output = self.process.stderr.read()
                if stderr_output:
                    logger.error(f"MCP server stderr: {stderr_output}")
            except Exception:
                pass
            
            # Clean up old process
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                try:
                    self.process.kill()
                    self.process.wait(timeout=1)
                except Exception:
                    pass
            
            self.process = None
            self._initialized = False
            
            # Restart the process
            await self.initialize()
            return True
        
        return False
    
    async def _send_request(self, request: Dict[str, Any], max_retries: int = 3) -> Dict[str, Any]:
        """
        Send a JSON-RPC request to the MCP server with automatic retry and process restart.
        
        Args:
            request: JSON-RPC request dictionary
            max_retries: Maximum number of retry attempts (default: 3)
            
        Returns:
            JSON-RPC response dictionary
        """
        for attempt in range(max_retries):
            try:
                # Check and restart process if needed
                await self._check_and_restart_process()
                
                if not self.process:
                    raise RuntimeError("MCP server process not started")
                
                request_id = request.get("id", "unknown")
                method = request.get("method", "unknown")
                logger.debug(f"Sending MCP request (ID: {request_id}, Method: {method}, Attempt: {attempt + 1})")
                
                # Send request
                request_json = json.dumps(request) + "\n"
                try:
                    self.process.stdin.write(request_json)
                    self.process.stdin.flush()
                    logger.debug(f"Request sent: {method}")
                except (BrokenPipeError, OSError) as e:
                    error_str = str(e)
                    logger.warning(f"Broken pipe or OS error writing to MCP server (attempt {attempt + 1}/{max_retries}): {error_str}")
                    
                    # Check if process died
                    if self.process.poll() is not None:
                        logger.warning("Process died, will restart on next attempt")
                        self.process = None
                        self._initialized = False
                    
                    # Retry with exponential backoff
                    if attempt < max_retries - 1:
                        wait_time = 0.5 * (2 ** attempt)  # 0.5s, 1s, 2s
                        logger.info(f"Waiting {wait_time:.1f}s before retry...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        raise RuntimeError(f"Failed to send request to MCP server after {max_retries} attempts: {error_str}")
                except Exception as e:
                    logger.error(f"Unexpected error writing to MCP server stdin: {str(e)}")
                    raise RuntimeError(f"Failed to send request to MCP server: {str(e)}")
                
                # Read response (non-blocking)
                try:
                    logger.info(f"Waiting for response from MCP server (request ID: {request_id}, method: {method})...")
                    response_line = await asyncio.to_thread(self.process.stdout.readline)
                    logger.debug(f"Received response line (length: {len(response_line) if response_line else 0} chars)")
                    if not response_line:
                        # Check if process is still alive
                        if self.process.poll() is not None:
                            exit_code = self.process.returncode
                            logger.warning(f"MCP server process exited with code: {exit_code}")
                            # Try to read stderr for error details
                            try:
                                stderr_output = self.process.stderr.read()
                                if stderr_output:
                                    logger.error(f"MCP server stderr: {stderr_output}")
                            except Exception:
                                pass
                            
                            # Retry if we have attempts left
                            if attempt < max_retries - 1:
                                self.process = None
                                self._initialized = False
                                wait_time = 0.5 * (2 ** attempt)
                                logger.info(f"Process died, waiting {wait_time:.1f}s before retry...")
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                raise RuntimeError(f"MCP server process exited unexpectedly with code {exit_code}")
                        raise RuntimeError("No response from MCP server (process still running)")
                    
                    logger.info(f"Response received (length: {len(response_line)} chars, request ID: {request_id})")
                    logger.debug(f"Response preview: {response_line[:200] if len(response_line) > 200 else response_line}")
                    response = json.loads(response_line.strip())
                    response_id = response.get('id', 'N/A')
                    logger.info(f"Parsed response (ID: {response_id}, has result: {'result' in response}, has error: {'error' in response})")
                    
                    # Verify response ID matches request ID
                    if response_id != request_id:
                        logger.warning(f"Response ID {response_id} does not match request ID {request_id}")
                    
                    # Check for errors
                    if "error" in response:
                        error = response["error"]
                        error_msg = f"MCP error: {error.get('message', 'Unknown error')}"
                        error_code = error.get('code', 'unknown')
                        logger.error(f"MCP server returned error (code: {error_code}): {error_msg}")
                        raise RuntimeError(error_msg)
                    
                    return response
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse MCP server response: {str(e)}")
                    logger.error(f"Response line: {response_line[:200] if 'response_line' in locals() else 'N/A'}...")
                    
                    # Retry on JSON decode errors if we have attempts left
                    if attempt < max_retries - 1:
                        wait_time = 0.5 * (2 ** attempt)
                        logger.info(f"JSON decode error, waiting {wait_time:.1f}s before retry...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        raise RuntimeError(f"Invalid JSON response from MCP server: {str(e)}")
                except Exception as e:
                    logger.error(f"Error reading from MCP server: {str(e)}")
                    # Retry on other errors if we have attempts left
                    if attempt < max_retries - 1:
                        wait_time = 0.5 * (2 ** attempt)
                        logger.info(f"Read error, waiting {wait_time:.1f}s before retry...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        raise
            except RuntimeError as e:
                # If it's a process-related error and we have retries left, try again
                if "process" in str(e).lower() and attempt < max_retries - 1:
                    wait_time = 0.5 * (2 ** attempt)
                    logger.info(f"Process error, waiting {wait_time:.1f}s before retry...")
                    await asyncio.sleep(wait_time)
                    continue
                raise
        
        # Should never reach here, but just in case
        raise RuntimeError(f"Failed to send request to MCP server after {max_retries} attempts")
    
    async def _send_notification(self, notification: Dict[str, Any]) -> None:
        """
        Send a JSON-RPC notification to the MCP server.
        Notifications don't return responses, so we don't wait for one.
        
        Args:
            notification: JSON-RPC notification dictionary (no 'id' field)
        """
        if not self.process:
            raise RuntimeError("MCP server process not started")
        
        method = notification.get("method", "unknown")
        logger.debug(f"Sending MCP notification (Method: {method})")
        
        # Send notification
        notification_json = json.dumps(notification) + "\n"
        try:
            self.process.stdin.write(notification_json)
            self.process.stdin.flush()
            logger.debug(f"Notification sent: {method}")
        except Exception as e:
            logger.error(f"Error writing notification to MCP server stdin: {str(e)}")
            raise RuntimeError(f"Failed to send notification to MCP server: {str(e)}")
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available MCP tools."""
        await self._ensure_initialized()
        
        request = {
            "jsonrpc": "2.0",
            "id": self._get_next_id(),
            "method": "tools/list"
        }
        
        response = await self._send_request(request)
        return response.get("result", {}).get("tools", [])
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call an MCP tool.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments
            
        Returns:
            Tool execution result
        """
        logger.info(f"Calling MCP tool: {tool_name} with arguments: {arguments}")
        await self._ensure_initialized()
        
        request = {
            "jsonrpc": "2.0",
            "id": self._get_next_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        logger.info(f"Sending tool call request (ID: {request['id']})...")
        try:
            # Add timeout to prevent indefinite hanging (60 seconds for tool calls)
            response = await asyncio.wait_for(
                self._send_request(request),
                timeout=60.0
            )
            logger.info(f"Tool call request completed (ID: {request['id']})")
        except asyncio.TimeoutError:
            logger.error(f"Tool call {tool_name} timed out after 60 seconds")
            raise RuntimeError(f"Tool call {tool_name} timed out after 60 seconds. The MCP server may be unresponsive.")
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {str(e)}", exc_info=True)
            raise
        
        result = response.get("result", {})
        logger.info(f"Tool {tool_name} returned result (keys: {list(result.keys()) if isinstance(result, dict) else 'N/A'})")
        return result
    
    def _parse_invoice_text(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Parse a single invoice from formatted text returned by MCP server.
        
        Args:
            text: Formatted text string containing invoice data
            
        Returns:
            Dictionary with invoice data or None if parsing fails
        """
        if not text or not isinstance(text, str):
            logger.warning(f"Invalid text input for parsing: {type(text)}")
            return None
        
        invoice = {}
        lines_parsed = 0
        
        for line in text.split("\n"):
            line = line.strip()
            if not line:  # Skip empty lines
                continue
                
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                lines_parsed += 1
                
                # Map keys to match expected format
                if key == "Invoice ID":
                    invoice["InvoiceID"] = value
                elif key == "Invoice":
                    invoice["InvoiceNumber"] = value
                elif key == "Reference":
                    invoice["Reference"] = value
                elif key == "Type":
                    invoice["Type"] = value
                elif key == "Status":
                    invoice["Status"] = value
                elif key == "Contact":
                    # Format: "Contact Name (contact-id)"
                    if "(" in value and ")" in value:
                        contact_name = value.split("(")[0].strip()
                        contact_id = value.split("(")[1].rstrip(")")
                        invoice["Contact"] = {"Name": contact_name, "ContactID": contact_id}
                    else:
                        invoice["Contact"] = {"Name": value}
                elif key == "Date":
                    invoice["Date"] = value
                elif key == "Due Date":
                    invoice["DueDate"] = value
                elif key == "Line Amount Types":
                    invoice["LineAmountTypes"] = value
                elif key == "Sub Total":
                    try:
                        invoice["SubTotal"] = float(value.replace(",", ""))
                    except (ValueError, AttributeError):
                        invoice["SubTotal"] = 0.0
                elif key == "Total Tax":
                    try:
                        invoice["TotalTax"] = float(value.replace(",", ""))
                    except (ValueError, AttributeError):
                        invoice["TotalTax"] = 0.0
                elif key == "Total":
                    try:
                        invoice["Total"] = float(value.replace(",", ""))
                    except (ValueError, AttributeError):
                        invoice["Total"] = 0.0
                elif key == "Total Discount":
                    try:
                        invoice["TotalDiscount"] = float(value.replace(",", ""))
                    except (ValueError, AttributeError):
                        invoice["TotalDiscount"] = 0.0
                elif key == "Currency":
                    invoice["CurrencyCode"] = value
                elif key == "Currency Rate":
                    try:
                        invoice["CurrencyRate"] = float(value)
                    except (ValueError, AttributeError):
                        pass
                elif key == "Last Updated":
                    invoice["UpdatedDateUTC"] = value
                elif key == "Fully Paid On":
                    invoice["FullyPaidOnDate"] = value if value else None
                elif key == "Amount Due":
                    try:
                        invoice["AmountDue"] = float(value.replace(",", ""))
                    except (ValueError, AttributeError):
                        invoice["AmountDue"] = 0.0
                elif key == "Amount Paid":
                    try:
                        invoice["AmountPaid"] = float(value.replace(",", ""))
                    except (ValueError, AttributeError):
                        invoice["AmountPaid"] = 0.0
                elif key == "Amount Credited":
                    try:
                        invoice["AmountCredited"] = float(value.replace(",", ""))
                    except (ValueError, AttributeError):
                        invoice["AmountCredited"] = 0.0
                elif key == "Has Errors":
                    invoice["HasErrors"] = value == "Yes"
                elif key == "Is Discounted":
                    invoice["IsDiscounted"] = value == "Yes"
        
        # Only return invoice if we parsed at least some basic fields
        if invoice and ("InvoiceID" in invoice or "InvoiceNumber" in invoice):
            logger.debug(f"Parsed invoice with {lines_parsed} fields, InvoiceNumber: {invoice.get('InvoiceNumber', 'N/A')}")
            return invoice
        else:
            logger.warning(f"Failed to parse invoice - missing required fields. Parsed {lines_parsed} lines, invoice keys: {list(invoice.keys())}")
            return None
    
    def _parse_invoice_content(self, result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Parse the text-based invoice content returned by MCP server.
        
        Args:
            result: MCP tool result dictionary
            
        Returns:
            List of parsed invoice dictionaries
        """
        invoices = []
        
        logger.debug(f"Parsing invoice content, result type: {type(result)}, keys: {list(result.keys()) if isinstance(result, dict) else 'N/A'}")
        
        if not isinstance(result, dict):
            logger.warning(f"Result is not a dict: {type(result)}, value: {str(result)[:200]}")
            return invoices
        
        if "content" not in result:
            logger.warning(f"Result does not contain 'content' key. Available keys: {list(result.keys())}")
            logger.debug(f"Full result structure: {json.dumps(result, indent=2)[:500]}")
            return invoices
        
        content = result["content"]
        logger.debug(f"Content type: {type(content)}, length: {len(content) if isinstance(content, list) else 'N/A'}")
        
        if not isinstance(content, list):
            logger.warning(f"Content is not a list: {type(content)}, value: {str(content)[:200]}")
            return invoices
        
        if len(content) == 0:
            logger.warning("Content list is empty")
            return invoices
        
        logger.debug(f"Processing {len(content)} content items")
        
        # The first item is usually a summary message like "Found X invoices:"
        # Subsequent items contain invoice data as formatted text
        for idx, item in enumerate(content):
            logger.debug(f"Processing content item {idx}: type={type(item)}, is_dict={isinstance(item, dict)}")
            if isinstance(item, dict):
                logger.debug(f"Item keys: {list(item.keys())}, type field: {item.get('type')}")
                if item.get("type") == "text":
                    text = item.get("text", "")
                    logger.debug(f"Text content length: {len(text)}, starts with 'Found': {text.startswith('Found') if text else False}")
                    if text:
                        if text.startswith("Found"):
                            logger.debug(f"Skipping summary line: {text[:100]}")
                        else:
                            logger.debug(f"Parsing invoice text (first 200 chars): {text[:200]}")
                            invoice = self._parse_invoice_text(text)
                            if invoice:
                                logger.debug(f"Successfully parsed invoice: {invoice.get('InvoiceNumber', 'Unknown')}")
                                invoices.append(invoice)
                            else:
                                logger.warning(f"Failed to parse invoice from text (first 200 chars): {text[:200]}")
                    else:
                        logger.debug(f"Empty text content in item {idx}")
        
        logger.info(f"Parsed {len(invoices)} invoices from {len(content)} content items")
        return invoices
    
    async def get_invoices(self, where: Optional[str] = None, order: Optional[str] = None, progress_callback: Optional[Callable[[int, str], None]] = None) -> List[Dict[str, Any]]:
        """
        Get invoices from Xero via MCP server with pagination.
        
        Note: The MCP server doesn't support 'where' filtering, so we fetch all pages
        and filter client-side. The 'order' parameter is also ignored as the server
        uses a fixed sort order.
        
        Args:
            where: Optional filter clause (ignored - filter client-side instead)
            order: Optional sort order (ignored - server uses fixed sort)
            
        Returns:
            List of invoices
        """
        logger.info(f"Getting invoices (where: {where}, order: {order})")
        logger.info("Note: MCP server doesn't support 'where' or 'order' - will fetch all pages and filter client-side")
        
        all_invoices = []
        page = 1
        max_pages = 1000  # Safety limit to prevent infinite loops
        
        try:
            # Estimate total pages (we don't know upfront, so we'll estimate based on first page)
            estimated_total_pages = None
            
            while page <= max_pages:
                # Call tool with page number (MCP server doesn't support 'where' parameter)
                arguments = {"page": page}
                logger.info(f"Fetching invoices page {page}...")
                
                # Update progress: 10% for initialization, then 10-90% for pagination
                if progress_callback:
                    if estimated_total_pages:
                        # We have an estimate, calculate progress
                        progress = min(10 + int((page / estimated_total_pages) * 80), 90)
                    else:
                        # No estimate yet, show incremental progress
                        progress = min(10 + (page * 5), 85)
                    progress_callback(progress, f"Fetching page {page}...")
                
                result = await self.call_tool("list-invoices", arguments)
                
                # Log the raw result for debugging
                logger.debug(f"Raw result from list-invoices: {json.dumps(result, indent=2)[:1000]}")
                
                # Parse the text response from MCP server
                invoices = self._parse_invoice_content(result)
                
                # Check if this is the first page and we got no invoices
                if page == 1 and not invoices:
                    logger.warning("No invoices found on first page - this might indicate an issue")
                    # Still break to avoid infinite loop, but log a warning
                    if progress_callback:
                        progress_callback(100, "No invoices found")
                    break
                
                if not invoices:
                    logger.info(f"No invoices found on page {page}, stopping pagination")
                    if progress_callback:
                        progress_callback(95, "Processing invoices...")
                    break  # No more invoices
                
                logger.info(f"Parsed {len(invoices)} invoices from page {page}")
                all_invoices.extend(invoices)
                
                # If we got less than 10 invoices, we've reached the last page
                if len(invoices) < 10:
                    logger.info(f"Reached last page (got {len(invoices)} invoices, less than page size of 10)")
                    if progress_callback:
                        progress_callback(95, "Processing invoices...")
                    break
                
                # Estimate total pages based on first page size (rough estimate)
                if page == 1 and len(invoices) == 10:
                    # Assume there might be more pages, estimate conservatively
                    estimated_total_pages = max(5, len(invoices) // 10 + 2)
                
                page += 1
            
            logger.info(f"Fetched {len(all_invoices)} total invoices across {page} page(s)")
            
            if progress_callback:
                progress_callback(95, "Filtering invoices...")
            
            # Filter by status if requested (client-side filtering)
            if where and "Status" in where:
                # Extract status from where clause (e.g., 'Status=="AUTHORISED"')
                import re
                match = re.search(r'Status=="(\w+)"', where)
                if match:
                    target_status = match.group(1)
                    filtered = [
                        inv for inv in all_invoices 
                        if inv.get("Status", "").upper() == target_status.upper()
                    ]
                    logger.info(f"Filtered to {len(filtered)} invoices with status '{target_status}'")
                    if progress_callback:
                        progress_callback(100, "Complete")
                    return filtered
            
            if progress_callback:
                progress_callback(100, "Complete")
            
            return all_invoices
            
        except Exception as e:
            logger.error(f"Error fetching invoices: {str(e)}", exc_info=True)
            return []
    
    async def get_outstanding_invoices(self, progress_callback: Optional[Callable[[int, str], None]] = None) -> List[Dict[str, Any]]:
        """
        Get outstanding invoices (excluding voided and deleted).
        
        Args:
            progress_callback: Optional callback function(progress: int, message: str) for progress updates
        
        Returns:
            List of invoices that are not voided or deleted
        """
        logger.info("Getting outstanding invoices (excluding VOIDED and DELETED)")
        
        if progress_callback:
            progress_callback(0, "Initializing...")
        
        # Fetch all invoices with pagination
        all_invoices = await self.get_invoices(progress_callback=progress_callback)
        
        if progress_callback:
            progress_callback(98, "Filtering outstanding invoices...")
        
        # Filter out voided and deleted invoices
        valid_statuses = ["DRAFT", "SUBMITTED", "AUTHORISED", "PAID"]
        outstanding = [
            inv for inv in all_invoices
            if inv.get("Status", "").upper() in valid_statuses
        ]
        
        logger.info(f"Filtered to {len(outstanding)} outstanding invoices (excluded VOIDED and DELETED)")
        
        if progress_callback:
            progress_callback(100, "Complete")
        
        return outstanding
    
    async def get_manual_journals(
        self, 
        manual_journal_id: Optional[str] = None,
        modified_after: Optional[str] = None,
        page: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get manual journals from Xero via MCP server.
        
        Args:
            manual_journal_id: Optional ID of specific journal to retrieve
            modified_after: Optional date (YYYY-MM-DD) to filter journals modified after this date
            page: Optional page number for pagination
        
        Returns:
            List of manual journals
        """
        try:
            params = {}
            if manual_journal_id:
                params["manualJournalId"] = manual_journal_id
            if modified_after:
                params["modifiedAfter"] = modified_after
            if page:
                params["page"] = page
            
            result = await self.call_tool("list-manual-journals", params)
            
            # Parse the text response to extract journal data
            if isinstance(result, dict) and "content" in result:
                content = result["content"]
                journals = []
                
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text = item.get("text", "")
                        # Parse journal data from text format
                        if "Manual Journal ID:" in text:
                            journal_data = self._parse_manual_journal_text(text)
                            if journal_data:
                                journals.append(journal_data)
                
                logger.info(f"Retrieved {len(journals)} manual journals")
                return journals
            
            return []
            
        except Exception as e:
            logger.error(f"Error fetching manual journals: {str(e)}", exc_info=True)
            return []
    
    def _parse_manual_journal_text(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse manual journal data from MCP server text response."""
        try:
            journal = {}
            lines = text.split("\n")
            
            for line in lines:
                if "Manual Journal ID:" in line:
                    journal["manualJournalID"] = line.split(":")[1].strip()
                elif "Description:" in line:
                    journal["narration"] = line.split(":", 1)[1].strip()
                elif "Date:" in line:
                    journal["date"] = line.split(":", 1)[1].strip()
                elif "Status:" in line:
                    journal["status"] = line.split(":", 1)[1].strip()
                elif "Line Amount:" in line:
                    # This is part of journal lines - we'll collect them separately
                    pass
            
            return journal if journal else None
            
        except Exception as e:
            logger.error(f"Error parsing manual journal text: {str(e)}")
            return None
    
    async def get_bank_transactions(
        self,
        bank_account_id: Optional[str] = None,
        page: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Get bank transactions from Xero via MCP server.
        
        Args:
            bank_account_id: Optional ID of specific bank account to filter
            page: Page number for pagination (default: 1)
        
        Returns:
            List of bank transactions
        """
        try:
            params = {"page": page}
            if bank_account_id:
                params["bankAccountId"] = bank_account_id
            
            result = await self.call_tool("list-bank-transactions", params)
            
            # Parse the text response to extract transaction data
            if isinstance(result, dict) and "content" in result:
                content = result["content"]
                transactions = []
                
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text = item.get("text", "")
                        # Parse transaction data from text format
                        if "Bank Transaction ID:" in text:
                            transaction_data = self._parse_bank_transaction_text(text)
                            if transaction_data:
                                transactions.append(transaction_data)
                
                logger.info(f"Retrieved {len(transactions)} bank transactions (page {page})")
                return transactions
            
            return []
            
        except Exception as e:
            logger.error(f"Error fetching bank transactions: {str(e)}", exc_info=True)
            return []
    
    def _parse_bank_transaction_text(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse bank transaction data from MCP server text response."""
        try:
            transaction = {}
            lines = text.split("\n")
            
            for line in lines:
                if "Bank Transaction ID:" in line:
                    transaction["bankTransactionID"] = line.split(":")[1].strip()
                elif "Bank Account:" in line:
                    parts = line.split("(")
                    if len(parts) > 1:
                        transaction["bankAccountName"] = parts[0].split(":")[1].strip()
                        transaction["bankAccountID"] = parts[1].rstrip(")").strip()
                elif "Contact:" in line:
                    parts = line.split("(")
                    if len(parts) > 1:
                        transaction["contactName"] = parts[0].split(":")[1].strip()
                        transaction["contactID"] = parts[1].rstrip(")").strip()
                elif "Reference:" in line:
                    transaction["reference"] = line.split(":", 1)[1].strip()
                elif "Date:" in line:
                    transaction["date"] = line.split(":", 1)[1].strip()
                elif "Sub Total:" in line:
                    transaction["subTotal"] = line.split(":", 1)[1].strip()
                elif "Total Tax:" in line:
                    transaction["totalTax"] = line.split(":", 1)[1].strip()
                elif "Total:" in line:
                    transaction["total"] = line.split(":", 1)[1].strip()
                elif "Reconciled" in line or "Unreconciled" in line:
                    transaction["isReconciled"] = "Reconciled" in line
                elif "Currency Code:" in line:
                    transaction["currencyCode"] = line.split(":", 1)[1].strip()
            
            return transaction if transaction else None
            
        except Exception as e:
            logger.error(f"Error parsing bank transaction text: {str(e)}")
            return None
    
    async def get_accounts(self) -> List[Dict[str, Any]]:
        """
        Get chart of accounts from Xero via MCP server.
        
        Returns:
            List of accounts
        """
        result = await self.call_tool("list-accounts", {})
        
        if "content" in result:
            if isinstance(result["content"], list):
                return result["content"]
            elif isinstance(result["content"], str):
                try:
                    parsed = json.loads(result["content"])
                    if isinstance(parsed, list):
                        return parsed
                    elif isinstance(parsed, dict) and "Accounts" in parsed:
                        return parsed["Accounts"]
                except json.JSONDecodeError:
                    pass
        
        if isinstance(result, dict) and "Accounts" in result:
            return result["Accounts"]
        
        return []
    
    async def close(self):
        """Close connection to MCP server."""
        if self.process:
            logger.info(f"Closing MCP server connection (PID: {self.process.pid})")
            try:
                self.process.terminate()
                logger.debug("Sent terminate signal to MCP server process")
                self.process.wait(timeout=5)
                logger.info("MCP server process terminated successfully")
            except subprocess.TimeoutExpired:
                logger.warning("MCP server process did not terminate in time, killing...")
                self.process.kill()
                self.process.wait()
                logger.info("MCP server process killed")
            except Exception as e:
                logger.error(f"Error closing MCP server: {str(e)}", exc_info=True)
            finally:
                self.process = None
                self._initialized = False
                logger.info("MCP client closed")

