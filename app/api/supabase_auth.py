"""
Supabase Authentication integration for user login and token verification.

You can easily disable this via settings (in database)
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any
from dataclasses import dataclass
import os
from datetime import datetime

from supabase_client import get_supabase_client, get_supabase_admin_client, is_supabase_configured
from api.utils import api_response
from common.log_handler import log
from api.rate_limiter import limiter
from api.anti_abuse import register_failed_ip


# Cache for supabase_auth_enabled setting (refreshed periodically)
_supabase_auth_enabled_cache = {"enabled": True, "last_check": 0}
CACHE_TTL_SECONDS = 30  # How long to cache the setting


async def is_supabase_auth_enabled() -> bool:
    """
    Check if Supabase authentication is enabled in settings.
    Uses a cache to avoid hitting the database on every request.
    """
    import time
    from database.models import get_session, Settings
    from sqlalchemy import select
    
    current_time = time.time()
    
    # Check if cache is valid
    if current_time - _supabase_auth_enabled_cache["last_check"] < CACHE_TTL_SECONDS:
        return _supabase_auth_enabled_cache["enabled"]
    
    # Fetch fresh value from database
    try:
        async with get_session() as session:
            result = await session.execute(
                select(Settings).where(Settings.name == "supabase_auth_enabled")
            )
            setting = result.scalars().first()
            
            if setting is not None:
                _supabase_auth_enabled_cache["enabled"] = setting.enabled
            else:
                # Default to True if setting doesn't exist
                _supabase_auth_enabled_cache["enabled"] = True
            
            _supabase_auth_enabled_cache["last_check"] = current_time
            log.info(f"Supabase auth enabled: {_supabase_auth_enabled_cache['enabled']}")
    except Exception as e:
        log.error(f"Error checking supabase_auth_enabled setting: {e}")
        # Default to True on error to be safe
        _supabase_auth_enabled_cache["enabled"] = True
    
    return _supabase_auth_enabled_cache["enabled"]


security = HTTPBearer(auto_error=False)

async def get_authenticated_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """
    Dependency that verifies the Supabase ID token and returns the user object.
    Raises 401 if invalid.
    """
    token = credentials.credentials
    user_info = await get_current_user_internal(token)
    
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_info


async def get_optional_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Optional[Dict[str, Any]]:
    """
    Dependency that returns user info if valid token provided, else None.
    Raises 401 if token is provided but invalid.
    """
    if not credentials:
        return None
        
    token = credentials.credentials
    user_info = await get_current_user_internal(token)
    
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_info


router = APIRouter(
    prefix="/auth",
    tags=["supabase-auth"],
)


@dataclass
class SupabaseUser:
    """Supabase user data."""
    id: str
    email: Optional[str] = None
    created_at: Optional[str] = None
    user_metadata: Optional[Dict[str, Any]] = None
    app_metadata: Optional[Dict[str, Any]] = None


class UserLoginResponse(BaseModel):
    """Response after successful login."""
    user_id: str
    email: Optional[str]
    access_token: str
    new_user: bool
    votecode: Optional[str] = None
    consent_transferred: bool = False


class UserLoginRequest(BaseModel):
    """Request for Supabase login with optional session_id for consent transfer."""
    id_token: str
    provider: str = "unknown"
    session_id: Optional[str] = None  # For transferring anonymous consent to user account


class UserInfoResponse(BaseModel):
    """User information response."""
    user_id: str
    email: Optional[str]
    provider: Optional[str]
    created_at: Optional[str]


@router.post("/supabase/login")
@limiter.limit("10/minute")
async def supabase_login(request: Request, login_data: UserLoginRequest):
    """
    Verify Supabase ID token and log user in.
    
    The frontend uses Supabase Auth to get an ID token,
    then sends it here for verification.
    
    On success, returns user info and generates a votecode if new user.
    Optionally transfers consent from anonymous session if session_id provided.
    """
    if not is_supabase_configured():
        return api_response(
            message="Supabase authentication not configured",
            success=False,
            status_code=503
        )
    
    # Check if Supabase auth is enabled in settings
    if not await is_supabase_auth_enabled():
        return api_response(
            message="Supabase authentication is currently disabled",
            success=False,
            status_code=503
        )
    
    id_token = login_data.id_token
    provider = login_data.provider
    session_id = login_data.session_id
    
    if not id_token:
        return api_response(
            message="ID token is required",
            success=False,
            status_code=400
        )
    
    try:
        client = get_supabase_admin_client()
        if not client:
            return api_response(
                message="Supabase admin client not available",
                success=False,
                status_code=503
            )
        
        try:
            user_response = client.auth.get_user(id_token)
            
            if user_response is None or hasattr(user_response, 'error') and user_response.error:
                await register_failed_ip(request.client.host)
                log.warning(f"Supabase token verification failed from {request.client.host}")
                return api_response(
                    message="Invalid authentication token",
                    success=False,
                    status_code=401
                )
            
            user = user_response.user
            
            # Check if this is a new user
            user_id = user.id
            email = user.email
            
            log.info(f"User logged in via Supabase: {user_id} ({email})")
            
            # Check if consent needs to be transferred
            consent_transferred = False
            if session_id and not user_id.startswith("anon_"):
                # This is a real user, try to transfer consent
                # The actual transfer will be done by the frontend calling the GDPR endpoint
                consent_transferred = True  # Signal that frontend should transfer consent
            
            return api_response(
                message="Login successful",
                data={
                    "user_id": user_id,
                    "email": email,
                    "provider": provider,
                    "access_token": id_token,
                    "consent_transferred": consent_transferred,
                    "session_id_to_transfer": session_id if session_id else None
                }
            )
            
        except Exception as e:
            log.error(f"Supabase auth error: {e}")
            await register_failed_ip(request.client.host)
            return api_response(
                message="Authentication failed",
                success=False,
                status_code=401
            )
    
    except Exception as e:
        log.error(f"Supabase login error: {e}")
        return api_response(
            message="Authentication error",
            success=False,
            status_code=500
        )


@router.get("/supabase/user")
@limiter.limit("20/minute")
async def get_current_user(request: Request, authorization: str = None):
    """
    Get current authenticated user from Supabase token.
    
    Requires Authorization header with Bearer token.
    """
    if not is_supabase_configured():
        return api_response(
            message="Supabase authentication not configured",
            success=False,
            status_code=503
        )
    
    # Check if Supabase auth is enabled in settings
    if not await is_supabase_auth_enabled():
        return api_response(
            message="Supabase authentication is currently disabled",
            success=False,
            status_code=503
        )
    
    # Get token from header
    if not authorization or not authorization.startswith("Bearer "):
        return api_response(
            message="Authorization header required",
            success=False,
            status_code=401
        )
    
    token = authorization.replace("Bearer ", "")
    
    try:
        client = get_supabase_client()
        if not client:
            return api_response(
                message="Supabase client not available",
                success=False,
                status_code=503
            )
        
        user_response = client.auth.get_user(token)
        
        if user_response is None or (hasattr(user_response, 'error') and user_response.error):
            return api_response(
                message="Invalid or expired token",
                success=False,
                status_code=401
            )
        
        user = user_response.user
        
        return api_response(
            message="User retrieved",
            data={
                "user_id": user.id,
                "email": user.email,
                "provider": user.app_metadata.get("provider", "email"),
                "created_at": str(user.created_at) if user.created_at else None
            }
        )
    
    except Exception as e:
        log.error(f"Get user error: {e}")
        return api_response(
            message="Failed to get user",
            success=False,
            status_code=500
        )


@router.post("/supabase/exchange")
@limiter.limit("10/minute")
async def exchange_supabase_token(request: Request, data: Dict[str, str]):
    """
    Exchange Supabase session for our internal session.
    
    Frontend sends Supabase session token, we verify it and
    return a votecode for voting.
    """
    if not is_supabase_configured():
        return api_response(
            message="Supabase not configured",
            success=False,
            status_code=503
        )
    
    # Check if Supabase auth is enabled in settings
    if not await is_supabase_auth_enabled():
        return api_response(
            message="Supabase authentication is currently disabled",
            success=False,
            status_code=503
        )
    
    supabase_token = data.get("supabase_token")
    
    if not supabase_token:
        return api_response(
            message="Supabase token required",
            success=False,
            status_code=400
        )
    
    # Verify token and get user
    try:
        user_info = await get_current_user_internal(supabase_token)
    except Exception as e:
        log.error(f"Token verification raised exception: {e}")
        return api_response(
            message=f"Token verification failed: {str(e)}",
            success=False,
            status_code=401
        )
    
    if not user_info:
        await register_failed_ip(request.client.host)
        return api_response(
            message="Invalid Supabase token - User info could not be retrieved",
            success=False,
            status_code=401
        )
    
    user_id = user_info["user_id"]
    email = user_info.get("email")
    
    # Get optional session_id for GDPR consent tracking
    session_id = data.get("session_id")
    
    # Check if user already has a votecode
    from database.models import VoteCodes, get_session
    from sqlalchemy import select
    import random
    import string
    
    async with get_session() as session:
        # First try to find by user_id column (more reliable)
        result = await session.execute(
            select(VoteCodes).where(
                VoteCodes.user_id == user_id,
                VoteCodes.disabled == False
            )
        )
        existing_code = result.scalars().first()
        
        if existing_code:
            # Update session_id if provided (for GDPR consent tracking)
            if session_id and not existing_code.session_id:
                existing_code.session_id = session_id
                await session.commit()
            return api_response(
                message="Returning user",
                data={
                    "user_id": user_id,
                    "email": email,
                    "votecode": existing_code.code,
                    "new_user": False
                }
            )
        
        # Generate a NEW 8-character votecode for this user
        exists = True
        while exists:
            votecode = ''.join(random.SystemRandom().choice(string.ascii_letters + string.digits) for _ in range(8))
            
            result = await session.execute(
                select(VoteCodes.id).where(VoteCodes.code == votecode)
            )
            exists = result.first() is not None
    
    new_code = VoteCodes(
        code=votecode,
        grade=0,
        gender=None,
        user_id=user_id,
    )
    session.add(new_code)
    await session.commit()
    
    log.info(f"Generated votecode {votecode} for user {user_id}")
    
    return api_response(
        message="New user - votecode generated",
        data={
            "user_id": user_id,
            "email": email,
            "votecode": votecode,
            "new_user": True
        }
    )


async def get_current_user_internal(token: str) -> Optional[Dict[str, Any]]:
    """Internal helper to get user from Supabase token."""
    try:
        # Use admin client for token verification (has proper credentials)
        client = get_supabase_admin_client()
        if not client:
            log.error("Supabase admin client is None in get_current_user_internal")
            return None
        
        # log.info(f"Verifying token: {token[:10]}...") 
        user_response = client.auth.get_user(token)
        
        if user_response is None:
            log.error("client.auth.get_user returned None")
            return None
            
        if hasattr(user_response, 'error') and user_response.error:
             log.error(f"client.auth.get_user returned error: {user_response.error}")
             return None
        
        user = user_response.user
        if not user:
             log.error("client.auth.get_user returned response but no user object")
             return None

        return {
            "user_id": user.id,
            "email": user.email,
            "provider": user.app_metadata.get("provider", "email"),
            "created_at": str(user.created_at) if user.created_at else None
        }
    except Exception as e:
        log.error(f"Internal get user error: {e}")
        return None


@router.post("/supabase/logout")
@limiter.limit("20/minute")
async def supabase_logout(request: Request, data: Dict[str, str]):
    """
    Logout user from Supabase (revoke token).
    """
    if not is_supabase_configured():
        return api_response(
            message="Supabase not configured",
            success=False,
            status_code=503
        )
    
    # Check if Supabase auth is enabled in settings
    if not await is_supabase_auth_enabled():
        return api_response(
            message="Supabase authentication is currently disabled",
            success=False,
            status_code=503
        )
    
    refresh_token = data.get("refresh_token")
    
    try:
        client = get_supabase_admin_client()
        if client:
            client.auth.sign_out(refresh_token=refresh_token)
    except Exception as e:
        log.warning(f"Supabase logout warning: {e}")
    
    return api_response(message="Logged out successfully")
