import os
from datetime import datetime, timedelta
import redis.asyncio as aioredis
from fastapi.responses import JSONResponse
from fastapi import Request
from typing import Callable, Awaitable
from common.log_handler import log
from .utils import api_response

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
r = aioredis.from_url(redis_url, decode_responses=True)

MAX_FAILED_ATTEMPTS = int(os.getenv("MAX_FAILED_ATTEMPTS", 10))
BAN_DURATION = timedelta(hours=48)

async def is_ip_banned(ip: str):
    ban = await r.get(f"banned_ip:{ip}")
    if ban:
        ban_dt = datetime.fromisoformat(ban)
        if datetime.utcnow() < ban_dt:
            return True, (ban_dt - datetime.utcnow())
        else:
            await r.delete(f"banned_ip:{ip}")
    return False, None

async def register_failed_ip(ip: str):
    key = f"failed_ip:{ip}"
    now_iso = datetime.utcnow().isoformat()
    await r.rpush(key, now_iso)
    await r.expire(key, int(BAN_DURATION.total_seconds()))
    attempts = await r.lrange(key, 0, -1)
    log.debug(f"{ip} failed attempts: {len(attempts)}")
    if len(attempts) >= MAX_FAILED_ATTEMPTS:
        log.info(f"Banned IP address: {ip}")
        ban_until = datetime.utcnow() + BAN_DURATION
        await r.set(f"banned_ip:{ip}", ban_until.isoformat(),
                    ex=int(BAN_DURATION.total_seconds()))
        await r.delete(key)
        return True
    return False

def setup_ban_middleware(app):
    @app.middleware("http")
    async def ban_middleware(request: Request, call_next: Callable[[Request], Awaitable]):
        ip = request.headers.get("X-Forwarded-For") or request.client.host
        banned, retry = await is_ip_banned(ip)
        if banned:
            retry_seconds = int(retry.total_seconds())
            return api_response(message="Your IP is banned", data=f"retry_after_seconds: {retry_seconds}", success=False, status_code=403, headers={"Retry-After": str(retry_seconds)})
        return await call_next(request)
    
async def reset_ip_ban(ip: str):
    await r.delete(f"banned_ip:{ip}")
    await r.delete(f"failed_ip:{ip}")
