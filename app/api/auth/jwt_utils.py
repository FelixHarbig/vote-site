"""
JWT token utilities for admin authentication.
Handles token creation, validation, and FastAPI dependency injection.
"""

import os
from datetime import datetime, timedelta
from typing import Optional
import jwt
from fastapi import Depends, HTTPException, Header
from common.log_handler import log


# JWT configuration from environment variables
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_HOURS = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_HOURS", "12"))


def create_access_token(username: str, expires_delta: Optional[timedelta] = None) -> tuple[str, int]:
    """
    Create a JWT access token for an admin user.
    
    Args:
        username: Admin username to encode in token
        expires_delta: Optional custom expiration time, defaults to configured hours
        
    Returns:
        Tuple of (token_string, expires_in_seconds)
    """
    if expires_delta is None:
        expires_delta = timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    
    expire = datetime.utcnow() + expires_delta
    expires_in_seconds = int(expires_delta.total_seconds())
    
    to_encode = {
        "sub": username,
        "exp": expire,
        "iat": datetime.utcnow()
    }
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    log.info(f"Created JWT token for admin '{username}', expires in {ACCESS_TOKEN_EXPIRE_HOURS} hours")
    
    return encoded_jwt, expires_in_seconds


def verify_access_token(token: str) -> str:
    """
    Verify and decode a JWT access token.
    
    Args:
        token: JWT token string
        
    Returns:
        Username from token if valid
        
    Raises:
        HTTPException: If token is invalid, expired, or malformed
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token: no username")
        
        return username
    
    except jwt.ExpiredSignatureError:
        log.warning("JWT token validation failed: token expired")
        raise HTTPException(status_code=401, detail="Token has expired")
    
    except jwt.InvalidTokenError as e:
        log.warning(f"JWT token validation failed: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_admin(authorization: Optional[str] = Header(None)) -> str:
    """
    FastAPI dependency to validate JWT token and extract admin username.
    
    This should be used as a dependency in protected admin routes.
    Expects Authorization header in format: "Bearer <token>"
    
    Args:
        authorization: Authorization header from request
        
    Returns:
        Admin username if token is valid
        
    Raises:
        HTTPException: If authorization header is missing or token is invalid
    """
    if authorization is None:
        log.warning("Admin route access attempt without Authorization header")
        raise HTTPException(
            status_code=401,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Extract token from "Bearer <token>" format
    parts = authorization.split()
    
    if len(parts) != 2 or parts[0].lower() != "bearer":
        log.warning(f"Admin route access attempt with malformed Authorization header")
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header format. Expected: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    token = parts[1]
    username = verify_access_token(token)
    
    return username
