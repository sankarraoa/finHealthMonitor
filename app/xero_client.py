"""Xero API client for OAuth 2.0 authentication and API calls."""
import requests
from typing import Dict, Optional, Any
from urllib.parse import urlencode, parse_qs, urlparse
import base64
import logging
import time
from app.config import config

logger = logging.getLogger(__name__)


class XeroClient:
    """Client for interacting with Xero API using OAuth 2.0."""
    
    def __init__(self):
        self.client_id = config.XERO_CLIENT_ID
        self.client_secret = config.XERO_CLIENT_SECRET
        self.redirect_uri = config.XERO_REDIRECT_URI
        self.auth_url = config.XERO_AUTH_URL
        self.token_url = config.XERO_TOKEN_URL
        self.api_base_url = config.XERO_API_BASE_URL
        self.scopes = config.get_scopes()
    
    def get_authorization_url(self, state: Optional[str] = None) -> str:
        """
        Generate the OAuth 2.0 authorization URL.
        
        Args:
            state: Optional state parameter for CSRF protection
            
        Returns:
            Authorization URL string
        """
        # Validate client_id is set
        if not self.client_id:
            raise ValueError("XERO_CLIENT_ID is not set. Please check your environment variables.")
        
        if not self.redirect_uri:
            raise ValueError("XERO_REDIRECT_URI is not set. Please check your environment variables.")
        
        # Ensure redirect_uri doesn't have trailing slash (Xero is strict about this)
        redirect_uri = self.redirect_uri.strip() if self.redirect_uri else ""
        if redirect_uri.endswith("/") and redirect_uri != "http://localhost:8000/":
            redirect_uri = redirect_uri.rstrip("/")
        
        # Validate and clean client_id
        client_id_clean = self.client_id.strip() if self.client_id else ""
        if not client_id_clean:
            raise ValueError("XERO_CLIENT_ID is empty after stripping whitespace. Please check your environment variables.")
        
        # Validate client_id format (should be 32 characters, alphanumeric)
        if len(client_id_clean) != 32:
            logger.warning(f"Client ID length is {len(client_id_clean)}, expected 32 characters")
        
        params = {
            "response_type": "code",
            "client_id": client_id_clean,
            "redirect_uri": redirect_uri,
            "scope": self.scopes,
            "state": state or "default",
            "prompt": "consent"  # Force Xero to show consent screen, bypassing cached session
        }
        
        # Log for debugging (without exposing full credentials)
        logger.info(f"Generating OAuth URL with client_id: {client_id_clean[:10]}... (length: {len(client_id_clean)})")
        logger.info(f"Redirect URI (final): {redirect_uri}")
        logger.info(f"Auth URL: {self.auth_url}")
        logger.info(f"Scopes: {self.scopes}")
        logger.info(f"State: {state[:20] + '...' if state and len(state) > 20 else state}")
        
        # Build URL manually to ensure proper encoding
        auth_url = f"{self.auth_url}?{urlencode(params, safe='')}"
        logger.info(f"Generated OAuth URL (first 200 chars): {auth_url[:200]}...")
        logger.info(f"Full URL length: {len(auth_url)}")
        
        # Verify client_id is in the URL and extract it to verify
        if "client_id=" not in auth_url:
            logger.error("ERROR: client_id parameter is missing from OAuth URL!")
            raise ValueError("client_id parameter is missing from OAuth URL")
        
        # Extract and verify client_id from URL
        try:
            parsed_url = urlparse(auth_url)
            query_params = parse_qs(parsed_url.query)
            url_client_id = query_params.get("client_id", [None])[0]
            url_redirect_uri = query_params.get("redirect_uri", [None])[0]
            
            logger.info(f"=== URL PARAMETER VERIFICATION ===")
            logger.info(f"Client ID from config: '{client_id_clean}' (length: {len(client_id_clean)})")
            logger.info(f"Client ID from URL: '{url_client_id}' (length: {len(url_client_id) if url_client_id else 0})")
            logger.info(f"Redirect URI from config: '{redirect_uri}'")
            logger.info(f"Redirect URI from URL: '{url_redirect_uri}'")
            
            # Character-by-character comparison of client_id
            if url_client_id:
                if len(url_client_id) != len(client_id_clean):
                    logger.error(f"Client ID length mismatch: config={len(client_id_clean)}, URL={len(url_client_id)}")
                else:
                    mismatches = []
                    for i, (c1, c2) in enumerate(zip(client_id_clean, url_client_id)):
                        if c1 != c2:
                            mismatches.append(f"Position {i}: '{c1}' != '{c2}'")
                    if mismatches:
                        logger.error(f"Client ID character mismatches: {', '.join(mismatches)}")
                    else:
                        logger.info("Client ID characters match exactly")
            
            if url_client_id != client_id_clean:
                logger.error(f"ERROR: Client ID mismatch! Original: '{client_id_clean}', URL: '{url_client_id}'")
                logger.error(f"Original bytes: {client_id_clean.encode('utf-8')}")
                logger.error(f"URL bytes: {url_client_id.encode('utf-8') if url_client_id else b'None'}")
                raise ValueError("Client ID mismatch in generated URL")
            logger.info(f"Verified client_id in URL matches: {url_client_id[:10]}...")
        except Exception as e:
            logger.warning(f"Could not verify client_id in URL: {str(e)}")
        
        # Verify redirect_uri is in the URL
        if "redirect_uri=" not in auth_url:
            logger.error("ERROR: redirect_uri parameter is missing from OAuth URL!")
            raise ValueError("redirect_uri parameter is missing from OAuth URL")
        
        # Log the full URL for debugging (be careful with this in production)
        logger.info(f"=== FULL OAUTH URL (for debugging) ===")
        logger.info(f"{auth_url}")
        
        return auth_url
    
    def get_access_token(self, authorization_code: str, max_retries: int = 3) -> Dict[str, Any]:
        """
        Exchange authorization code for access token with retry logic.
        
        Args:
            authorization_code: The authorization code from OAuth callback
            max_retries: Maximum number of retry attempts (default: 3)
            
        Returns:
            Dictionary containing access_token, refresh_token, expires_in, etc.
        """
        # Create Basic Auth header
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": self.redirect_uri
        }
        
        # Retry logic with exponential backoff
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                # Increase timeout to 30 seconds (Xero API can be slow)
                timeout = 30
                logger.info(f"=== TOKEN EXCHANGE ATTEMPT {attempt + 1}/{max_retries} ===")
                logger.info(f"Token URL: {self.token_url}")
                logger.info(f"Timeout: {timeout} seconds")
                logger.info(f"Authorization code length: {len(authorization_code) if authorization_code else 0}")
                logger.info(f"Redirect URI: {self.redirect_uri}")
                logger.info(f"Making POST request to Xero token endpoint...")
                
                import time as time_module
                start_time = time_module.time()
                response = requests.post(self.token_url, headers=headers, data=data, timeout=timeout)
                elapsed_time = time_module.time() - start_time
                
                logger.info(f"Response received in {elapsed_time:.2f} seconds")
                logger.info(f"Response status code: {response.status_code}")
                logger.info(f"Response headers: {dict(response.headers)}")
                
                response.raise_for_status()
                
                response_data = response.json()
                logger.info(f"Successfully exchanged authorization code for token on attempt {attempt + 1}")
                logger.info(f"Response keys: {list(response_data.keys()) if isinstance(response_data, dict) else 'Not a dict'}")
                logger.info(f"Access token present: {'access_token' in response_data if isinstance(response_data, dict) else False}")
                logger.info(f"Refresh token present: {'refresh_token' in response_data if isinstance(response_data, dict) else False}")
                
                return response_data
            except requests.exceptions.Timeout as e:
                last_exception = e
                wait_time = (2 ** attempt) * 2  # Exponential backoff: 2s, 4s, 8s
                if attempt < max_retries - 1:
                    logger.warning(f"Timeout exchanging authorization code (attempt {attempt + 1}/{max_retries}): Xero API did not respond within {timeout} seconds. Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Timeout exchanging authorization code after {max_retries} attempts: Xero API did not respond within {timeout} seconds")
                    raise Exception(f"Token exchange timed out after {max_retries} attempts. The Xero API may be experiencing issues. Please try again later.")
            except requests.exceptions.HTTPError as e:
                # HTTP errors (4xx, 5xx) should not be retried
                error_msg = f"HTTP error exchanging authorization code: {e.response.status_code}"
                if hasattr(e.response, 'text'):
                    error_msg += f" - {e.response.text[:200]}"
                logger.error(error_msg)
                raise Exception(f"Failed to exchange authorization code: {error_msg}")
            except requests.exceptions.RequestException as e:
                last_exception = e
                wait_time = (2 ** attempt) * 2  # Exponential backoff: 2s, 4s, 8s
                if attempt < max_retries - 1:
                    logger.warning(f"Request error exchanging authorization code (attempt {attempt + 1}/{max_retries}): {str(e)}. Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Request error exchanging authorization code after {max_retries} attempts: {str(e)}")
                    raise Exception(f"Failed to exchange authorization code after {max_retries} attempts: {str(e)}")
        
        # This should never be reached, but just in case
        if last_exception:
            raise Exception(f"Failed to exchange authorization code: {str(last_exception)}")
        else:
            raise Exception("Failed to exchange authorization code: Unknown error")
    
    def refresh_token(self, refresh_token: str, max_retries: int = 3) -> Dict[str, Any]:
        """
        Refresh an expired access token with retry logic.
        
        Args:
            refresh_token: The refresh token from previous authentication
            max_retries: Maximum number of retry attempts (default: 3)
            
        Returns:
            Dictionary containing new access_token, refresh_token, etc.
        """
        # Create Basic Auth header
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }
        
        # Retry logic with exponential backoff
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                # Increase timeout to 30 seconds (Xero API can be slow)
                timeout = 30
                logger.info(f"Attempting to refresh token (attempt {attempt + 1}/{max_retries})...")
                response = requests.post(self.token_url, headers=headers, data=data, timeout=timeout)
                response.raise_for_status()
                logger.info(f"Successfully refreshed token on attempt {attempt + 1}")
                return response.json()
            except requests.exceptions.Timeout as e:
                last_exception = e
                wait_time = (2 ** attempt) * 2  # Exponential backoff: 2s, 4s, 8s
                if attempt < max_retries - 1:
                    logger.warning(f"Timeout refreshing token (attempt {attempt + 1}/{max_retries}): Xero API did not respond within {timeout} seconds. Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Timeout refreshing token after {max_retries} attempts: Xero API did not respond within {timeout} seconds")
                    raise Exception(f"Token refresh timed out after {max_retries} attempts. The Xero API may be experiencing issues. Please try again later.")
            except requests.exceptions.HTTPError as e:
                # HTTP errors (4xx, 5xx) should not be retried
                error_msg = f"HTTP error refreshing token: {e.response.status_code}"
                if hasattr(e.response, 'text'):
                    error_msg += f" - {e.response.text[:200]}"
                logger.error(error_msg)
                raise Exception(f"Failed to refresh token: {error_msg}")
            except requests.exceptions.RequestException as e:
                last_exception = e
                wait_time = (2 ** attempt) * 2  # Exponential backoff: 2s, 4s, 8s
                if attempt < max_retries - 1:
                    logger.warning(f"Request error refreshing token (attempt {attempt + 1}/{max_retries}): {str(e)}. Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Request error refreshing token after {max_retries} attempts: {str(e)}")
                    raise Exception(f"Failed to refresh token after {max_retries} attempts: {str(e)}")
        
        # This should never be reached, but just in case
        if last_exception:
            raise Exception(f"Failed to refresh token: {str(last_exception)}")
        else:
            raise Exception("Failed to refresh token: Unknown error")
    
    def get_accounts(self, access_token: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetch chart of accounts from Xero.
        
        Args:
            access_token: Valid OAuth access token
            tenant_id: Optional tenant ID (Xero organization ID)
            
        Returns:
            Dictionary containing accounts data
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Xero-tenant-id": tenant_id or "",
            "Accept": "application/json"
        }
        
        url = f"{self.api_base_url}/Accounts"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    
    def get_connections(self, access_token: str) -> list:
        """
        Get connected Xero organizations (tenants).
        
        Args:
            access_token: Valid OAuth access token
            
        Returns:
            List of connected organizations
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        url = "https://api.xero.com/connections"
        try:
            # Add timeout to prevent hanging
            logger.info(f"=== GETTING XERO CONNECTIONS ===")
            logger.info(f"URL: {url}")
            logger.info(f"Access token length: {len(access_token) if access_token else 0}")
            logger.info(f"Access token preview: {access_token[:30] + '...' if access_token and len(access_token) > 30 else access_token}")
            logger.info(f"Timeout: 30 seconds")
            logger.info(f"Making GET request to Xero connections endpoint...")
            
            start_time = time.time()
            response = requests.get(url, headers=headers, timeout=30)
            elapsed_time = time.time() - start_time
            
            logger.info(f"Response received in {elapsed_time:.2f} seconds")
            logger.info(f"Response status code: {response.status_code}")
            logger.info(f"Response headers: {dict(response.headers)}")
            
            response.raise_for_status()
            
            response_data = response.json()
            logger.info(f"Successfully retrieved Xero connections")
            logger.info(f"Response type: {type(response_data)}")
            logger.info(f"Number of connections: {len(response_data) if isinstance(response_data, list) else 'Not a list'}")
            if isinstance(response_data, list) and len(response_data) > 0:
                logger.info(f"First connection keys: {list(response_data[0].keys()) if isinstance(response_data[0], dict) else 'Not a dict'}")
            
            return response_data
        except requests.exceptions.Timeout:
            logger.error("Timeout getting Xero connections: API did not respond within 30 seconds")
            raise Exception("Failed to get Xero connections: Request timed out. Please try again.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error getting Xero connections: {str(e)}")
            raise Exception(f"Failed to get Xero connections: {str(e)}")
    
    def disconnect_connection(self, access_token: str, connection_id: str) -> bool:
        """
        Disconnect a Xero connection by revoking access.
        
        Args:
            access_token: Valid OAuth access token
            connection_id: Xero connection ID (from get_connections() response, not tenant_id)
            
        Returns:
            True if disconnected successfully, False otherwise
        """
        import logging
        logger = logging.getLogger(__name__)
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        url = f"https://api.xero.com/connections/{connection_id}"
        logger.info(f"Attempting to disconnect Xero connection: connection_id={connection_id}, url={url}")
        
        try:
            # Add timeout to prevent hanging (10 seconds should be enough for API call)
            response = requests.delete(url, headers=headers, timeout=10)
            logger.info(f"Xero disconnect API response: status={response.status_code}, body={response.text[:200]}")
            
            if response.status_code == 204:
                # 204 No Content means successful deletion
                logger.info(f"Successfully disconnected Xero connection: {connection_id}")
                return True
            elif response.status_code == 200:
                # Some APIs return 200 OK for successful deletion
                logger.info(f"Successfully disconnected Xero connection: {connection_id}")
                return True
            else:
                # Log unexpected status codes
                logger.warning(f"Unexpected status code {response.status_code} when disconnecting connection {connection_id}: {response.text[:200]}")
                response.raise_for_status()
                return False
        except requests.exceptions.HTTPError as e:
            # Log detailed error information
            error_msg = f"HTTP error disconnecting Xero connection {connection_id}: {str(e)}"
            if hasattr(e.response, 'text'):
                error_msg += f" Response: {e.response.text[:200]}"
            logger.error(error_msg)
            return False
        except requests.exceptions.Timeout as e:
            # Log timeout errors specifically
            logger.error(f"Timeout error disconnecting Xero connection {connection_id}: {str(e)}")
            logger.error(f"The request took longer than 10 seconds. Xero API may be slow or unreachable.")
            return False
        except requests.exceptions.RequestException as e:
            # Log connection/network errors
            logger.error(f"Request error disconnecting Xero connection {connection_id}: {str(e)}")
            return False

    def get_manual_journal(self, access_token: str, tenant_id: str, manual_journal_id: str) -> Dict[str, Any]:
        """
        Fetch a specific manual journal with all line items from Xero API directly.
        This bypasses the MCP server bug where journal lines are returned as [object Object].
        
        Args:
            access_token: Valid OAuth access token
            tenant_id: Xero tenant/organization ID
            manual_journal_id: The manual journal ID to fetch
            
        Returns:
            Dictionary containing manual journal data with journal lines
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Xero-tenant-id": tenant_id,
            "Accept": "application/json"
        }
        
        url = f"{self.api_base_url}/ManualJournals/{manual_journal_id}"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

