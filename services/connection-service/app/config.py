"""Configuration management for the connection service."""
import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Application configuration loaded from environment variables."""
    
    # Service configuration
    SERVICE_NAME: str = "connection-service"
    PORT: int = int(os.getenv("PORT", 8002))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    
    # Database configuration
    USE_LOCAL_DB: bool = os.getenv("USE_LOCAL_DB", "false").lower() == "true"
    
    _default_local_user = os.getenv("USER", os.getenv("USERNAME", "postgres"))
    LOCAL_DATABASE_URL: str = os.getenv(
        "LOCAL_DATABASE_URL",
        f"postgresql://{_default_local_user}@localhost:5432/finhealthmonitor"
    )
    
    RAILWAY_DATABASE_URL: str = os.getenv(
        "RAILWAY_DATABASE_URL",
        os.getenv("DATABASE_URL", "")  # Railway injects this
    )
    
    _explicit_database_url: Optional[str] = os.getenv("DATABASE_URL")
    
    @property
    def DATABASE_URL(self) -> str:
        """Get the appropriate database URL based on configuration."""
        if self._explicit_database_url:
            url = self._explicit_database_url
            if ':port' in url or '/port/' in url or url.endswith(':port'):
                raise ValueError(
                    "DATABASE_URL contains placeholder 'port' instead of actual port number. "
                    "Please set DATABASE_URL with a real port number."
                )
            return url
        
        if self.USE_LOCAL_DB:
            url = self.LOCAL_DATABASE_URL
        else:
            url = self.RAILWAY_DATABASE_URL
        
        if not url:
            raise ValueError(
                "DATABASE_URL not set. Please set DATABASE_URL environment variable "
                "or configure USE_LOCAL_DB and LOCAL_DATABASE_URL/RAILWAY_DATABASE_URL."
            )
        
        if ':port' in url or '/port/' in url or url.endswith(':port'):
            raise ValueError(
                f"{'LOCAL_DATABASE_URL' if self.USE_LOCAL_DB else 'RAILWAY_DATABASE_URL'} contains placeholder 'port' instead of actual port number. "
                f"Please set a valid database URL with a real port number (e.g., 5432 for local PostgreSQL)."
            )
        
        return url
    
    # Xero OAuth configuration
    XERO_CLIENT_ID: str = os.getenv("XERO_CLIENT_ID", "")
    XERO_CLIENT_SECRET: str = os.getenv("XERO_CLIENT_SECRET", "")
    XERO_REDIRECT_URI: str = os.getenv("XERO_REDIRECT_URI", "http://localhost:8000/callback")
    XERO_AUTH_URL: str = os.getenv("XERO_AUTH_URL", "https://login.xero.com/identity/connect/authorize")
    XERO_TOKEN_URL: str = os.getenv("XERO_TOKEN_URL", "https://identity.xero.com/connect/token")
    XERO_API_BASE_URL: str = os.getenv("XERO_API_BASE_URL", "https://api.xero.com")
    
    # QuickBooks OAuth configuration
    QUICKBOOKS_CLIENT_ID: str = os.getenv("QUICKBOOKS_CLIENT_ID", "")
    QUICKBOOKS_CLIENT_SECRET: str = os.getenv("QUICKBOOKS_CLIENT_SECRET", "")
    QUICKBOOKS_REDIRECT_URI: str = os.getenv("QUICKBOOKS_REDIRECT_URI", "http://localhost:8000/quickbooks/callback")
    QUICKBOOKS_ENVIRONMENT: str = os.getenv("QUICKBOOKS_ENVIRONMENT", "sandbox").lower()
    
    # Application settings
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    SECRET_KEY: str = os.getenv("SECRET_KEY", os.urandom(32).hex())
    
    def get_xero_scopes(self) -> str:
        """Get Xero OAuth scopes."""
        return " ".join([
            "accounting.transactions",
            "accounting.contacts",
            "accounting.settings",
            "accounting.reports.read",
            "accounting.journals.read",
            "accounting.attachments",
            "payroll.employees",
            "payroll.payruns",
            "payroll.payslip",
            "payroll.timesheets",
            "offline_access"
        ])


# Create a global config instance
config = Config()
