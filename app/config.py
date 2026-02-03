"""Configuration management for the application."""
import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Application configuration loaded from environment variables."""
    
    # Xero OAuth 2.0 credentials
    XERO_CLIENT_ID: str = os.getenv("XERO_CLIENT_ID", "")
    XERO_CLIENT_SECRET: str = os.getenv("XERO_CLIENT_SECRET", "")
    XERO_REDIRECT_URI: str = os.getenv("XERO_REDIRECT_URI", "http://localhost:8000/callback")
    
    # Xero API endpoints
    XERO_AUTH_URL: str = "https://login.xero.com/identity/connect/authorize"
    XERO_TOKEN_URL: str = "https://identity.xero.com/connect/token"
    XERO_API_BASE_URL: str = "https://api.xero.com/api.xro/2.0"
    
    # QuickBooks OAuth 2.0 credentials
    QUICKBOOKS_CLIENT_ID: str = os.getenv("QUICKBOOKS_CLIENT_ID", "")
    QUICKBOOKS_CLIENT_SECRET: str = os.getenv("QUICKBOOKS_CLIENT_SECRET", "")
    QUICKBOOKS_REDIRECT_URI: str = os.getenv("QUICKBOOKS_REDIRECT_URI", "http://localhost:8000/quickbooks/callback")
    
    # QuickBooks MCP Server path
    QUICKBOOKS_MCP_SERVER_PATH: Optional[str] = os.getenv("QUICKBOOKS_MCP_SERVER_PATH", None)
    
    # Session configuration
    SECRET_KEY: str = os.getenv("SECRET_KEY", os.urandom(32).hex())
    SESSION_COOKIE_NAME: str = "finhealth_session"
    
    # Application settings
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    # LLM Provider configuration
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai").lower()  # "openai" or "toqan"
    
    # Architecture mode
    USE_AGENTIC_ARCHITECTURE: bool = os.getenv("USE_AGENTIC_ARCHITECTURE", "false").lower() == "true"
    
    # OpenAI API configuration
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    
    # Toqan API configuration
    TOQAN_API_KEY: str = os.getenv("TOQAN_API_KEY", "")
    TOQAN_API_BASE_URL: str = os.getenv("TOQAN_API_BASE_URL", "https://api.coco.prod.toqan.ai/api")
    
    @classmethod
    def validate(cls) -> None:
        """Validate that required configuration values are set."""
        if not cls.XERO_CLIENT_ID:
            raise ValueError("XERO_CLIENT_ID environment variable is required")
        if not cls.XERO_CLIENT_SECRET:
            raise ValueError("XERO_CLIENT_SECRET environment variable is required")
    
    @classmethod
    def get_scopes(cls) -> str:
        """Get the OAuth scopes required for the application."""
        return "accounting.transactions accounting.settings.read accounting.reports.read accounting.contacts accounting.attachments accounting.journals.read offline_access"
# Create a global config instance
config = Config()

