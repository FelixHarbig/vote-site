# from api.voting import
from api.router import router
from fastapi import APIRouter, Depends
from fastapi_cache.decorator import cache
from common.log_handler import log

# Import voting modules
from api.voting import vote

# Import authentication router
from api.auth.router import router as auth_router

# Include authentication router (no auth required for login endpoint)
router.include_router(auth_router)

# Import admin modules (they register routes on admin_router)
from api.admin import manage_teachers, manage_votes, manage_db, manage_images, metrics, manage_imports, manage_exports

# Import and include the protected admin router
from api.admin.router import admin_router
router.include_router(admin_router)

@router.get("/")
@cache(expire=3600)
async def index():
    return {"message": "Why are you here?"}
