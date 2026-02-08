"""Client for calling User Service microservice."""
import httpx
import os
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)

# Get user service URL from environment
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://localhost:8001")


class UserServiceClient:
    """Client for interacting with the User Service microservice."""
    
    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize the client.
        
        Args:
            base_url: Optional base URL for the user service. Defaults to USER_SERVICE_URL env var.
        """
        self.base_url = base_url or USER_SERVICE_URL
        self.timeout = 30.0
    
    async def login(self, email: str, password: str) -> Dict[str, Any]:
        """
        Login user and get JWT token.
        
        Args:
            email: User email
            password: User password
        
        Returns:
            Dict with access_token, user, tenants, default_tenant
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/api/auth/login",
                    json={"email": email, "password": password}
                )
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"User service login error: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"User service connection error: {e}")
                raise
    
    async def register(self, user_data: Dict[str, Any], tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Register a new user.
        
        Args:
            user_data: User data dict with email, first_name, last_name, password, etc.
            tenant_id: Optional tenant ID to add user to
        
        Returns:
            User response dict
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                params = {}
                if tenant_id:
                    params["tenant_id"] = tenant_id
                
                resp = await client.post(
                    f"{self.base_url}/api/auth/register",
                    json=user_data,
                    params=params
                )
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"User service register error: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"User service connection error: {e}")
                raise
    
    async def get_user(self, user_id: str, token: str) -> Dict[str, Any]:
        """
        Get user by ID.
        
        Args:
            user_id: User ID
            token: JWT token
        
        Returns:
            User response dict
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.get(
                    f"{self.base_url}/api/users/{user_id}",
                    headers={"Authorization": f"Bearer {token}"}
                )
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"User service get_user error: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"User service connection error: {e}")
                raise
    
    async def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify JWT token by calling user service (or decode locally if shared secret).
        
        For now, we'll decode locally using the shared JWT_SECRET.
        In production, you might want to call a /api/auth/verify endpoint.
        
        Args:
            token: JWT token
        
        Returns:
            Decoded token payload
        """
        # For now, decode locally - both services share JWT_SECRET
        # In the future, you could call an endpoint: f"{self.base_url}/api/auth/verify"
        try:
            import jwt
            from app.config import config
            
            payload = jwt.decode(
                token,
                config.JWT_SECRET if hasattr(config, 'JWT_SECRET') else os.getenv("JWT_SECRET", ""),
                algorithms=["HS256"]
            )
            return payload
        except jwt.InvalidTokenError as e:
            logger.error(f"Token verification error: {e}")
            raise ValueError(f"Invalid token: {e}")
    
    async def get_user_tenants(self, user_id: str, token: str) -> List[Dict[str, Any]]:
        """
        Get all tenants for a user.
        
        Args:
            user_id: User ID
            token: JWT token
        
        Returns:
            List of tenant dicts
        """
        # This would require a new endpoint in user-service
        # For now, we can get it from the login response or create the endpoint
        # For simplicity, we'll return empty list and let the caller handle it
        return []
