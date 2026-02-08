"""Configuration management for the user service."""
import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Application configuration loaded from environment variables."""
    
    # Service configuration
    SERVICE_NAME: str = "user-service"
    PORT: int = int(os.getenv("PORT", 8001))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    
    # JWT configuration
    JWT_SECRET: str = os.getenv("JWT_SECRET", os.getenv("SECRET_KEY", os.urandom(32).hex()))
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))
    
    # Database configuration
    # Railway sets DATABASE_URL automatically when Postgres is linked
    # For local dev, use LOCAL_DATABASE_URL or fallback to default
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
        # If DATABASE_URL is explicitly set, use it (Railway or explicit override)
        if self._explicit_database_url:
            url = self._explicit_database_url
            if ':port' in url or '/port/' in url or url.endswith(':port'):
                raise ValueError(
                    "DATABASE_URL contains placeholder 'port' instead of actual port number. "
                    "Please set DATABASE_URL with a real port number."
                )
            return url
        
        # Otherwise, use local or Railway based on USE_LOCAL_DB flag
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
    
    # Application settings
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"


# Create a global config instance
config = Config()
