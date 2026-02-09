"""QuickBooks API client for OAuth 2.0 authentication and API calls."""
import requests
from typing import Dict, Optional
from urllib.parse import urlencode
import base64
import logging
from app.config import config

logger = logging.getLogger(__name__)


class QuickBooksClient:
    """Client for interacting with QuickBooks API using OAuth 2.0."""
    
    def __init__(self):
        self.client_id = config.QUICKBOOKS_CLIENT_ID
        self.client_secret = config.QUICKBOOKS_CLIENT_SECRET
        self.redirect_uri = config.QUICKBOOKS_REDIRECT_URI
        self.environment = config.QUICKBOOKS_ENVIRONMENT.lower()
        
        if self.environment == "sandbox":
            self.auth_url = "https://appcenter.intuit.com/connect/oauth2"
            self.token_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
            self.api_base_url = "https://sandbox-quickbooks.api.intuit.com"
        else:
            self.auth_url = "https://appcenter.intuit.com/connect/oauth2"
            self.token_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
            self.api_base_url = "https://quickbooks.api.intuit.com"
        
        self.scopes = "com.intuit.quickbooks.accounting"
    
    def get_authorization_url(self, state: Optional[str] = None) -> str:
        """Generate the OAuth 2.0 authorization URL for QuickBooks."""
        if not self.client_id:
            raise ValueError("QUICKBOOKS_CLIENT_ID is not set")
        if not self.redirect_uri:
            raise ValueError("QUICKBOOKS_REDIRECT_URI is not set")
        
        params = {
            "client_id": self.client_id,
            "scope": self.scopes,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "state": state or "default"
        }
        
        if self.environment == "sandbox":
            params["environment"] = "sandbox"
        
        return f"{self.auth_url}?{urlencode(params)}"
    
    def get_access_token(self, authorization_code: str) -> Dict:
        """Exchange authorization code for access token."""
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }
        
        data = {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": self.redirect_uri
        }
        
        try:
            response = requests.post(self.token_url, headers=headers, data=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to get QuickBooks access token: {str(e)}")
    
    def refresh_token(self, refresh_token: str) -> Dict:
        """Refresh an expired access token."""
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }
        
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }
        
        try:
            response = requests.post(self.token_url, headers=headers, data=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to refresh QuickBooks token: {str(e)}")
