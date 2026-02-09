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
    
    # JWT configuration (for microservices)
    JWT_SECRET: str = os.getenv("JWT_SECRET", os.getenv("SECRET_KEY", os.urandom(32).hex()))
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))
    
    # User Service URL (for microservices)
    USER_SERVICE_URL: str = os.getenv("USER_SERVICE_URL", "http://localhost:8001")
    
    # LLM Provider configuration
    # Auto-detect provider if not explicitly set, based on which API key is present
    _llm_provider = os.getenv("LLM_PROVIDER", "").lower()
    if not _llm_provider:
        # Auto-detect: prefer Toqan if TOQAN_API_KEY is set, otherwise OpenAI
        if os.getenv("TOQAN_API_KEY"):
            _llm_provider = "toqan"
        elif os.getenv("OPENAI_API_KEY"):
            _llm_provider = "openai"
        else:
            _llm_provider = "openai"  # Default fallback
    LLM_PROVIDER: str = _llm_provider
    
    # Architecture mode
    USE_AGENTIC_ARCHITECTURE: bool = os.getenv("USE_AGENTIC_ARCHITECTURE", "false").lower() == "true"
    
    # OpenAI API configuration
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    
    # Toqan API configuration
    TOQAN_API_KEY: str = os.getenv("TOQAN_API_KEY", "")
    TOQAN_API_BASE_URL: str = os.getenv("TOQAN_API_BASE_URL", "https://api.coco.prod.toqan.ai/api")
    
    # Database configuration
    # Use local PostgreSQL if USE_LOCAL_DB is set to "true", otherwise use Railway
    USE_LOCAL_DB: bool = os.getenv("USE_LOCAL_DB", "false").lower() == "true"
    
    # Local PostgreSQL connection string (default for macOS Homebrew installation)
    # Uses current username since PostgreSQL on macOS typically creates DB with current user
    _default_local_user = os.getenv("USER", os.getenv("USERNAME", "postgres"))
    LOCAL_DATABASE_URL: str = os.getenv(
        "LOCAL_DATABASE_URL",
        f"postgresql://{_default_local_user}@localhost:5432/finhealthmonitor"
    )
    
    # Railway PostgreSQL connection string
    RAILWAY_DATABASE_URL: str = os.getenv(
        "RAILWAY_DATABASE_URL",
        "postgresql://postgres:nIrSLrxNUhzPghZJiuKVwGwcFMxiAzgh@metro.proxy.rlwy.net:10176/railway"
    )
    
    # Legacy DATABASE_URL support (for backward compatibility)
    # If DATABASE_URL is explicitly set, it takes precedence
    _explicit_database_url: Optional[str] = os.getenv("DATABASE_URL")
    
    @property
    def DATABASE_URL(self) -> str:
        """Get the appropriate database URL based on configuration."""
        # If DATABASE_URL is explicitly set, use it (backward compatibility)
        if self._explicit_database_url:
            url = self._explicit_database_url
            # Validate that the URL doesn't contain placeholder values
            if ':port' in url or '/port/' in url or url.endswith(':port'):
                raise ValueError(
                    "DATABASE_URL contains placeholder 'port' instead of actual port number. "
                    "Please set DATABASE_URL with a real port number (e.g., 5432) or unset it "
                    "and use USE_LOCAL_DB=true/false with LOCAL_DATABASE_URL/RAILWAY_DATABASE_URL instead."
                )
            return url
        
        # Otherwise, use local or Railway based on USE_LOCAL_DB flag
        if self.USE_LOCAL_DB:
            url = self.LOCAL_DATABASE_URL
        else:
            url = self.RAILWAY_DATABASE_URL
        
        # Validate that the URL doesn't contain placeholder values
        if ':port' in url or '/port/' in url or url.endswith(':port'):
            raise ValueError(
                f"{'LOCAL_DATABASE_URL' if self.USE_LOCAL_DB else 'RAILWAY_DATABASE_URL'} contains placeholder 'port' instead of actual port number. "
                f"Please set a valid database URL with a real port number (e.g., 5432 for local PostgreSQL)."
            )
        
        return url
    
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

