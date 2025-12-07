# from api.voting import
from api.router import router
from fastapi_cache.decorator import cache
from common.log_handler import log
from api.admin import manage_teachers, manage_votes, manage_db, manage_images, metrics, manage_imports, manage_exports
from api.voting import vote

@router.get("/")
@cache(expire=3600)
async def index():
    return {"message": "Why are you here?"}
