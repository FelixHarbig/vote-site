import sys, os
sys.path.append(os.path.dirname(__file__)) # this is somehow required by docker or else it just won't work
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from dotenv import load_dotenv
from contextlib import asynccontextmanager
import redis.asyncio as redis
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from common.log_handler import log
from database.models import VotingEngine, voting_engine
import asyncio
from api.rate_limiter import limiter


load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    redis_client = redis.from_url(
        redis_url,
        encoding="utf-8",
        decode_responses=False
    )
    FastAPICache.init(RedisBackend(redis_client), prefix="fastapi-cache")
    log.info("FastAPI Cache initialized with Redis backend")
    
    async with voting_engine.begin() as conn:
        log.info("Creating database tables if they do not exist")
        await conn.run_sync(VotingEngine.metadata.create_all)

    try:
        yield
    finally:
        await redis_client.close()
        log.info("Redis connection closed")

if os.getenv("DEV", "FALSE").upper() == "TRUE":
    app = FastAPI(debug=True, title="Voting backend DEVELOPMENT",lifespan=lifespan)
    log.warning("Starting **development** server")
else:
    app = FastAPI(title="Voting backend",lifespan=lifespan, openapi_url=None, docs_url=None, redoc_url=None)
app.state.limiter = limiter
from api import router as api_router
app.include_router(api_router)

from api.anti_abuse import setup_ban_middleware
setup_ban_middleware(app)

ALLOWED_ORIGINS = os.getenv("FRONTEND_URL", "").split(",")
if os.getenv("DEV", "FALSE").upper() == "TRUE":
    ALLOWED_ORIGINS.append("http://localhost:3000")
    ALLOWED_ORIGINS.append("http://localhost:5000")
    ALLOWED_ORIGINS.append("http://localhost:8000")
    ALLOWED_ORIGINS.append("http://localhost:8001")
    allowed_origins = ALLOWED_ORIGINS
    log.warning("CORS allowed origins set for development")
else:
    if not ALLOWED_ORIGINS or ALLOWED_ORIGINS.strip() == "":
        raise ValueError("FRONTEND_URL is not set")
    allowed_origins = ALLOWED_ORIGINS


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET","POST","DELETE"],
    
    allow_headers=["*"],
)




if __name__ == "__main__":
    import uvicorn

    log.warning("Starting development server")
    from api.anti_abuse import reset_ip_ban
    asyncio.run(reset_ip_ban("127.0.0.1"))
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)


