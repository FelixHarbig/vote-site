from ..router import router
from fastapi import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from .utils import authorize_admin
from fastapi import Request


@router.get("/metrics") # isn't like super cool but can display some intresting stuff for the current session (doesn't persist trough restart of script)
async def metrics(token: str, request: Request):
    auth = await authorize_admin(token, request)
    if auth is not True:
        return auth
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
