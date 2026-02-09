from .router import admin_router as router
from fastapi import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi import Request


@router.get("/metrics") # isn't like super cool but can display some intresting stuff for the current session (doesn't persist trough restart of script)
async def metrics(request: Request):
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
