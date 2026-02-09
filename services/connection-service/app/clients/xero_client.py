"""Xero API client for OAuth 2.0 authentication and API calls."""
import requests
from typing import Dict, Optional
from urllib.parse import urlencode
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
        self.scopes = config.get_xero_scopes()
    
    def get_authorization_url(self, state: Optional[str] = None) -> str:
        """Generate the OAuth 2.0 authorization URL."""
        if not self.client_id:
            raise ValueError("XERO_CLIENT_ID is not set")
        if not self.redirect_uri:
            raise ValueError("XERO_REDIRECT_URI is not set")
        
        redirect_uri = self.redirect_uri.strip()
        if redirect_uri.endswith("/") and redirect_uri != "http://localhost:8000/":
            redirect_uri = redirect_uri.rstrip("/")
        
        params = {
            "response_type": "code",
            "client_id": self.client_id.strip(),
            "redirect_uri": redirect_uri,
            "scope": self.scopes,
            "state": state or "default",
            "prompt": "consent"
        }
        
        return f"{self.auth_url}?{urlencode(params, safe='')}"
    
    def get_access_token(self, authorization_code: str, max_retries: int = 3) -> Dict:
        """Exchange authorization code for access token."""
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
        
        for attempt in range(max_retries):
            try:
                response = requests.post(self.token_url, headers=headers, data=data, timeout=30)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.Timeout as e:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 2
                    logger.warning(f"Timeout exchanging token (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise Exception(f"Token exchange timed out after {max_retries} attempts")
            except requests.exceptions.HTTPError as e:
                error_msg = f"HTTP error: {e.response.status_code}"
                if hasattr(e.response, 'text'):
                    error_msg += f" - {e.response.text[:200]}"
                raise Exception(f"Failed to exchange authorization code: {error_msg}")
        
        raise Exception("Failed to exchange authorization code: Unknown error")
    
    def refresh_token(self, refresh_token: str, max_retries: int = 3) -> Dict:
        """Refresh an expired access token."""
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
        
        for attempt in range(max_retries):
            try:
                response = requests.post(self.token_url, headers=headers, data=data, timeout=30)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.Timeout as e:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 2
                    logger.warning(f"Timeout refreshing token (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise Exception(f"Token refresh timed out after {max_retries} attempts")
            except requests.exceptions.HTTPError as e:
                error_msg = f"HTTP error: {e.response.status_code}"
                if hasattr(e.response, 'text'):
                    error_msg += f" - {e.response.text[:200]}"
                raise Exception(f"Failed to refresh token: {error_msg}")
        
        raise Exception("Failed to refresh token: Unknown error")
    
    def get_connections(self, access_token: str) -> list:
        """Get connected Xero organizations (tenants)."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        url = "https://api.xero.com/connections"
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to get Xero connections: {str(e)}")
    
    def disconnect_connection(self, access_token: str, connection_id: str) -> bool:
        """Disconnect a Xero connection by revoking access."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        url = f"https://api.xero.com/connections/{connection_id}"
        try:
            response = requests.delete(url, headers=headers, timeout=10)
            return response.status_code in [200, 204]
        except requests.exceptions.RequestException:
            return False
