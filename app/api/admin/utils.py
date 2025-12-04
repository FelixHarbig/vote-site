from fastapi import Request
import os
from ..utils import api_response
from ..anti_abuse import register_failed_ip

async def authorize_admin(token: str, request: Request):
    if token != os.getenv("ADMIN_SECRET"):
        await register_failed_ip(request.client.host)
        return api_response(message="Unauthorized", success=False, status_code=401)
    return True