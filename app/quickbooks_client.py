"""QuickBooks API client for OAuth 2.0 authentication and API calls."""
import requests
from typing import Dict, Optional, Any
from urllib.parse import urlencode
import base64
from app.config import config
import os


class QuickBooksClient:
    """Client for interacting with QuickBooks API using OAuth 2.0."""
    
    def __init__(self):
        # QuickBooks OAuth credentials (to be set in config)
        self.client_id = os.getenv("QUICKBOOKS_CLIENT_ID", "")
        self.client_secret = os.getenv("QUICKBOOKS_CLIENT_SECRET", "")
        self.redirect_uri = os.getenv("QUICKBOOKS_REDIRECT_URI", "http://localhost:8000/quickbooks/callback")
        self.environment = os.getenv("QUICKBOOKS_ENVIRONMENT", "sandbox").lower()
        
        # QuickBooks OAuth endpoints
        # For sandbox, use sandbox endpoints; for production, use production endpoints
        if self.environment == "sandbox":
            self.auth_url = "https://appcenter.intuit.com/connect/oauth2"
            self.token_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
            self.api_base_url = "https://sandbox-quickbooks.api.intuit.com"
        else:
            self.auth_url = "https://appcenter.intuit.com/connect/oauth2"
            self.token_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
            self.api_base_url = "https://quickbooks.api.intuit.com"
        
        # Scopes for QuickBooks
        self.scopes = "com.intuit.quickbooks.accounting"
    
    def get_authorization_url(self, state: Optional[str] = None) -> str:
        """
        Generate the OAuth 2.0 authorization URL for QuickBooks.
        
        Args:
            state: Optional state parameter for CSRF protection
            
        Returns:
            Authorization URL string
        """
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
        
        # Add environment parameter for sandbox
        if self.environment == "sandbox":
            params["environment"] = "sandbox"
        
        auth_url = f"{self.auth_url}?{urlencode(params)}"
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
        except requests.exceptions.HTTPError as e:
            error_detail = ""
            try:
                error_response = response.json()
                error_detail = f" - {error_response}"
            except:
                error_detail = f" - {response.text}"
            raise Exception(f"Failed to get QuickBooks access token: {str(e)}{error_detail}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to get QuickBooks access token: {str(e)}")
    
    def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh an expired access token.
        
        Args:
            refresh_token: The refresh token
            
        Returns:
            Dictionary containing new access_token, refresh_token, expires_in, etc.
        """
        # Create Basic Auth header
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
    
    def get_company_info(self, access_token: str, company_id: str) -> Dict[str, Any]:
        """
        Get company information from QuickBooks.
        
        Args:
            access_token: OAuth access token
            company_id: QuickBooks company ID
            
        Returns:
            Company information dictionary
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        url = f"{self.api_base_url}/v3/company/{company_id}/companyinfo/{company_id}"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to get QuickBooks company info: {str(e)}")
