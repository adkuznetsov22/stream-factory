"""
Simple authentication routes.
Uses a single admin password from environment for simplicity.
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from .settings import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)

# Simple in-memory token store (in production use Redis or DB)
_tokens: dict[str, datetime] = {}

TOKEN_EXPIRY_HOURS = 24


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str
    expires_at: str


def _hash_password(password: str) -> str:
    """Hash password with SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()


def _generate_token() -> str:
    """Generate a secure random token."""
    return secrets.token_urlsafe(32)


def _cleanup_expired_tokens():
    """Remove expired tokens from memory."""
    now = datetime.utcnow()
    expired = [t for t, exp in _tokens.items() if exp < now]
    for t in expired:
        del _tokens[t]


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Login with admin password.
    Returns a bearer token valid for 24 hours.
    """
    settings = get_settings()
    admin_password = getattr(settings, 'admin_password', None)
    
    if not admin_password:
        # If no password configured, allow any login (dev mode)
        pass
    elif _hash_password(request.password) != _hash_password(admin_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password"
        )
    
    _cleanup_expired_tokens()
    
    token = _generate_token()
    expires_at = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS)
    _tokens[token] = expires_at
    
    return LoginResponse(
        token=token,
        expires_at=expires_at.isoformat()
    )


@router.post("/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Invalidate current token."""
    if credentials and credentials.credentials in _tokens:
        del _tokens[credentials.credentials]
    return {"status": "logged out"}


@router.get("/me")
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Check if current token is valid."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = credentials.credentials
    _cleanup_expired_tokens()
    
    if token not in _tokens:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return {
        "authenticated": True,
        "expires_at": _tokens[token].isoformat()
    }


def get_optional_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> bool:
    """Dependency that returns True if authenticated, False otherwise."""
    if not credentials:
        return False
    
    token = credentials.credentials
    _cleanup_expired_tokens()
    
    return token in _tokens


def require_auth(credentials: HTTPAuthorizationCredentials = Depends(security)) -> bool:
    """Dependency that requires authentication."""
    settings = get_settings()
    
    # Skip auth if no admin password configured (dev mode)
    if not getattr(settings, 'admin_password', None):
        return True
    
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = credentials.credentials
    _cleanup_expired_tokens()
    
    if token not in _tokens:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return True
