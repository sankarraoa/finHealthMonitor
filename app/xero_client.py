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
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.scopes,
            "state": state or "default"
        }
        return f"{self.auth_url}?{urlencode(params)}"
    
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

