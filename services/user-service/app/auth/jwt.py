"""JWT token creation and validation."""
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import HTTPException, status

from app.config import config


def create_access_token(
    user_id: str,
    tenant_id: Optional[str] = None,
    email: Optional[str] = None,
    role: Optional[str] = None,
    additional_claims: Optional[Dict[str, Any]] = None
) -> str:
    """
    Create a JWT access token.
    
    Args:
        user_id: User ID (subject)
        tenant_id: Optional tenant ID
        email: Optional user email
        role: Optional user role
        additional_claims: Optional additional claims to include
    
    Returns:
        Encoded JWT token string
    """
    now = datetime.utcnow()
    exp = now + timedelta(hours=config.JWT_EXPIRATION_HOURS)
    
    payload = {
        "sub": user_id,  # Subject (user ID)
        "iat": now,  # Issued at
        "exp": exp,  # Expiration
    }
    
    if tenant_id:
        payload["tenant_id"] = tenant_id
    if email:
        payload["email"] = email
    if role:
        payload["role"] = role
    
    if additional_claims:
        payload.update(additional_claims)
    
    token = jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)
    return token


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
