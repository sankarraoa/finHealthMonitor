"""MCP client for communicating with Xero MCP Server via stdio."""
import subprocess
import json
import asyncio
import os
from typing import Dict, Any, Optional, List
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class XeroMCPClient:
    """Client for interacting with Xero MCP Server via stdio."""
    
    def __init__(self, mcp_server_path: Optional[str] = None, bearer_token: Optional[str] = None):
        """
        Initialize MCP client.
        
        Args:
            mcp_server_path: Path to the MCP server executable
            bearer_token: Optional bearer token for authentication (takes precedence)
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
        
        logger.info(f"Initializing XeroMCPClient with server path: {self.mcp_server_path}")
        
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
    
    async def _send_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send a JSON-RPC request to the MCP server.
        
        Args:
            request: JSON-RPC request dictionary
            
        Returns:
            JSON-RPC response dictionary
        """
        if not self.process:
            raise RuntimeError("MCP server process not started")
        
        request_id = request.get("id", "unknown")
        method = request.get("method", "unknown")
        logger.debug(f"Sending MCP request (ID: {request_id}, Method: {method})")
        
        # Send request
        request_json = json.dumps(request) + "\n"
        try:
            self.process.stdin.write(request_json)
            self.process.stdin.flush()
            logger.debug(f"Request sent: {method}")
        except Exception as e:
            logger.error(f"Error writing to MCP server stdin: {str(e)}")
            raise RuntimeError(f"Failed to send request to MCP server: {str(e)}")
        
        # Read response (non-blocking)
        try:
            response_line = await asyncio.to_thread(self.process.stdout.readline)
            if not response_line:
                # Check if process is still alive
                if self.process.poll() is not None:
                    exit_code = self.process.returncode
                    logger.error(f"MCP server process exited with code: {exit_code}")
                    # Try to read stderr for error details
                    try:
                        stderr_output = self.process.stderr.read()
                        if stderr_output:
                            logger.error(f"MCP server stderr: {stderr_output}")
                    except Exception:
                        pass
                    raise RuntimeError(f"MCP server process exited unexpectedly with code {exit_code}")
                raise RuntimeError("No response from MCP server (process still running)")
            
            logger.debug(f"Response received (length: {len(response_line)} chars)")
            response = json.loads(response_line.strip())
            
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
            logger.error(f"Response line: {response_line[:200]}...")
            raise RuntimeError(f"Invalid JSON response from MCP server: {str(e)}")
        except Exception as e:
            logger.error(f"Error reading from MCP server: {str(e)}")
            raise
    
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
        
        response = await self._send_request(request)
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
                    if text and not text.startswith("Found"):  # Skip summary lines
                        logger.debug(f"Parsing invoice text (first 200 chars): {text[:200]}")
                        invoice = self._parse_invoice_text(text)
                        if invoice:
                            logger.debug(f"Successfully parsed invoice: {invoice.get('InvoiceNumber', 'Unknown')}")
                            invoices.append(invoice)
                        else:
                            logger.warning(f"Failed to parse invoice from text: {text[:200]}")
        
        logger.info(f"Parsed {len(invoices)} invoices from {len(content)} content items")
        return invoices
    
    async def get_invoices(self, where: Optional[str] = None, order: Optional[str] = None) -> List[Dict[str, Any]]:
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
            while page <= max_pages:
                # Call tool with page number (MCP server doesn't support 'where' parameter)
                arguments = {"page": page}
                logger.info(f"Fetching invoices page {page}...")
                
                result = await self.call_tool("list-invoices", arguments)
                
                # Log the raw result for debugging
                logger.debug(f"Raw result from list-invoices: {json.dumps(result, indent=2)[:1000]}")
                
                # Parse the text response from MCP server
                invoices = self._parse_invoice_content(result)
                
                # Check if this is the first page and we got no invoices
                if page == 1 and not invoices:
                    logger.warning("No invoices found on first page - this might indicate an issue")
                    # Still break to avoid infinite loop, but log a warning
                    break
                
                if not invoices:
                    logger.info(f"No invoices found on page {page}, stopping pagination")
                    break  # No more invoices
                
                logger.info(f"Parsed {len(invoices)} invoices from page {page}")
                all_invoices.extend(invoices)
                
                # If we got less than 10 invoices, we've reached the last page
                if len(invoices) < 10:
                    logger.info(f"Reached last page (got {len(invoices)} invoices, less than page size of 10)")
                    break
                
                page += 1
            
            logger.info(f"Fetched {len(all_invoices)} total invoices across {page} page(s)")
            
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
                    return filtered
            
            return all_invoices
            
        except Exception as e:
            logger.error(f"Error fetching invoices: {str(e)}", exc_info=True)
            return []
    
    async def get_outstanding_invoices(self) -> List[Dict[str, Any]]:
        """
        Get outstanding invoices (excluding voided and deleted).
        
        Returns:
            List of invoices that are not voided or deleted
        """
        logger.info("Getting outstanding invoices (excluding VOIDED and DELETED)")
        
        # Fetch all invoices with pagination
        all_invoices = await self.get_invoices()
        
        # Filter out voided and deleted invoices
        valid_statuses = ["DRAFT", "SUBMITTED", "AUTHORISED", "PAID"]
        outstanding = [
            inv for inv in all_invoices
            if inv.get("Status", "").upper() in valid_statuses
        ]
        
        logger.info(f"Filtered to {len(outstanding)} outstanding invoices (excluded VOIDED and DELETED)")
        return outstanding
    
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

