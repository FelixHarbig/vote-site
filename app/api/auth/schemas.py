"""
Pydantic schemas for admin authentication.
"""

from pydantic import BaseModel, Field


class TOTPVerifyRequest(BaseModel):
    """Request body for TOTP verification and authentication."""
    username: str = Field(..., min_length=1, description="Admin username")
    password: str = Field(..., min_length=1, description="Admin password")
    totp_code: str = Field(..., min_length=6, max_length=6, description="6-digit TOTP code from authenticator app")

    class Config:
        json_schema_extra = {
            "example": {
                "username": "admin",
                "password": "SecurePassword123",
                "totp_code": "123456"
            }
        }


class TOTPVerifyResponse(BaseModel):
    """Response from TOTP verification endpoint."""
    success: bool = Field(..., description="Whether authentication was successful")
    message: str = Field(..., description="Status message")
    data: dict = Field(None, description="Token data if successful")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Authentication successful",
                "data": {
                    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
                    "token_type": "bearer",
                    "expires_in": 43200
                }
            }
        }
