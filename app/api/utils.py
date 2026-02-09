from fastapi.responses import JSONResponse
from typing import Any, Optional
import os
import redis.asyncio as aioredis
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

def api_response(
    data: Any = None,
    message: Optional[str] = None,
    success: bool = True,
    status_code: int = 200,
    headers: dict = None,
):
    payload = {
        "success": success,
        "message": message,
        "data": data
    }

    return JSONResponse(
        content=payload,
        status_code=status_code,
        headers=headers
    )

security = HTTPBearer()

from fastapi import Security, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Create security scheme instance
security = HTTPBearer(auto_error=False)

async def extract_challenge_from_header(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    challenge: Optional[str] = Query(None)
) -> str:
    """
    Extract challenge token from Authorization header (Bearer) OR Query param.
    Priority: Header > Query
    """
    if credentials and credentials.credentials:
        return credentials.credentials
    
    if challenge:
        return challenge
        
    raise HTTPException(status_code=401, detail="Missing authorization (Header or Query)")



redis = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

async def get_image_from_cache(teacher_id: int, number: int = 1):
    key = f"teacher_image:{teacher_id}:{number}"
    cached = await redis.get(key)
    if cached:
        return cached
    return None

async def set_image_cache(teacher_id: int, number: int, data: bytes, expire=600):
    key = f"teacher_image:{teacher_id}:{number}"
    await redis.set(key, data, ex=expire)