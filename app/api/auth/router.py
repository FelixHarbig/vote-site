"""
Authentication router for admin login with TOTP verification.
"""

from fastapi import APIRouter, Request
from database.models import get_session, Admins
from sqlalchemy import select
from api.utils import api_response
from .schemas import TOTPVerifyRequest, TOTPVerifyResponse
from .password_utils import verify_password
from .totp_utils import verify_totp
from .jwt_utils import create_access_token
from common.log_handler import log
from api.anti_abuse import register_failed_ip
from datetime import datetime

router = APIRouter(
    prefix="/auth",
    tags=["authentication"],
)


@router.post("/verify_totp", response_model=TOTPVerifyResponse)
async def verify_totp_endpoint(request: Request, credentials: TOTPVerifyRequest):
    """
    Verify admin credentials and TOTP code, return JWT access token.
    
    This endpoint authenticates an admin user by verifying:
    1. Username exists in database
    2. Password matches the stored hash
    3. TOTP code is valid for the admin's secret
    
    On success, returns a JWT bearer token that must be included in the
    Authorization header for subsequent admin API requests.
    
    Args:
        request: FastAPI request object (for IP logging)
        credentials: Login credentials containing username, password, and TOTP code
        
    Returns:
        JSON response with JWT token if successful, or error message if failed
        
    Responses:
        200: Authentication successful, returns access token
        401: Authentication failed (invalid username, password, or TOTP code)
    """
    async with get_session() as session:
        result = await session.execute(
            select(Admins).where(Admins.username == credentials.username)
        )
        admin = result.scalars().first()
        
        if not admin:
            log.warning(f"Admin login attempt with invalid username '{credentials.username}' from {request.client.host}")
            await register_failed_ip(request.client.host)
            return api_response(
                message="Invalid username, password, or TOTP code",
                success=False,
                status_code=401
            )
        
        if not verify_password(credentials.password, admin.password_hash):
            log.warning(f"Admin login attempt with invalid password for '{credentials.username}' from {request.client.host}")
            await register_failed_ip(request.client.host)
            return api_response(
                message="Invalid username, password, or TOTP code",
                success=False,
                status_code=401
            )
        
        if not verify_totp(admin.totp_secret, credentials.totp_code):
            log.warning(f"Admin login attempt with invalid TOTP code for '{credentials.username}' from {request.client.host}")
            await register_failed_ip(request.client.host)
            return api_response(
                message="Invalid username, password, or TOTP code",
                success=False,
                status_code=401
            )

        admin.last_login = datetime.utcnow()
        await session.commit()
        
        access_token, expires_in = create_access_token(username=admin.username)
        
        log.info(f"Admin '{credentials.username}' successfully authenticated from {request.client.host}")
        
        return api_response(
            message="Authentication successful",
            data={
                "access_token": access_token,
                "token_type": "bearer",
                "expires_in": expires_in
            }
        )
