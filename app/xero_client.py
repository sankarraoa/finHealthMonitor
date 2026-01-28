"""Xero API client for OAuth 2.0 authentication and API calls."""
import requests
from typing import Dict, Optional, Any
from urllib.parse import urlencode, parse_qs
import base64
from app.config import config


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
        
        params = {
            "response_type": "code",
            "client_id": self.client_id.strip() if self.client_id else "",  # Ensure no whitespace
            "redirect_uri": redirect_uri,
            "scope": self.scopes,
            "state": state or "default"
        }
        
        # Log for debugging (without exposing full credentials)
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Generating OAuth URL with client_id: {self.client_id[:10] if self.client_id else 'EMPTY'}... (length: {len(self.client_id) if self.client_id else 0})")
        logger.info(f"Redirect URI (final): {redirect_uri}")
        logger.info(f"Auth URL: {self.auth_url}")
        logger.info(f"Scopes: {self.scopes}")
        
        # Build URL manually to ensure proper encoding
        auth_url = f"{self.auth_url}?{urlencode(params, safe='')}"
        logger.info(f"Generated OAuth URL (first 200 chars): {auth_url[:200]}...")
        logger.info(f"Full URL length: {len(auth_url)}")
        
        # Verify client_id is in the URL
        if "client_id=" not in auth_url:
            logger.error("ERROR: client_id parameter is missing from OAuth URL!")
            raise ValueError("client_id parameter is missing from OAuth URL")
        
        # Verify redirect_uri is in the URL
        if "redirect_uri=" not in auth_url:
            logger.error("ERROR: redirect_uri parameter is missing from OAuth URL!")
            raise ValueError("redirect_uri parameter is missing from OAuth URL")
        
        return auth_url
    
    def get_access_token(self, authorization_code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access token.
        
        Args:
            authorization_code: The authorization code from OAuth callback
            
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
        
        response = requests.post(self.token_url, headers=headers, data=data)
        response.raise_for_status()
        return response.json()
    
    def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh an expired access token.
        
        Args:
            refresh_token: The refresh token from previous authentication
            
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
        
        response = requests.post(self.token_url, headers=headers, data=data)
        response.raise_for_status()
        return response.json()
    
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
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    
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
            response = requests.delete(url, headers=headers)
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

