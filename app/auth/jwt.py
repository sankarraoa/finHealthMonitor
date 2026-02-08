"""JWT token validation utilities for the monolith."""
import jwt
from typing import Optional, Dict, Any
from fastapi import HTTPException, status

from app.config import config


def verify_token(token: str) -> Dict[str, Any]:
    """
    Verify and decode a JWT token.
    
    Args:
        token: JWT token string
    
    Returns:
        Decoded token payload
    
    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        payload = jwt.decode(
            token,
            config.JWT_SECRET,
            algorithms=[config.JWT_ALGORITHM]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )


def get_user_id_from_token(token: str) -> Optional[str]:
    """Extract user ID from token."""
    try:
        payload = verify_token(token)
        return payload.get("sub")
    except HTTPException:
        return None


def get_tenant_id_from_token(token: str) -> Optional[str]:
    """Extract tenant ID from token."""
    try:
        payload = verify_token(token)
        return payload.get("tenant_id")
    except HTTPException:
        return None
