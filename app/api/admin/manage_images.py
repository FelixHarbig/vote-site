from api.router import router
from fastapi_cache.decorator import cache
from common.log_handler import log
from fastapi import Request, Body
from database.models import get_session, Teachers, Images
import os
from api.utils import api_response
from sqlalchemy import select
import base64
from ..rate_limiter import limiter
from .utils import authorize_admin
from ..schemas import AdminResponse



@router.post("/admin/add_image", response_model=AdminResponse)
async def add_image(
    token: str,
    request: Request,
    teacher_id: int = Body(...),
    image_binary: str = Body(...),
):
    """
    Add a profile image for a teacher.
    
    Uploads a base64-encoded image and associates it with a teacher.
    Requires admin authentication.
    
    Args:
        token (str): Admin authentication token
        request (Request): HTTP request object (for client IP logging)
        teacher_id (int): ID of the teacher
        image_binary (str): Base64-encoded image data
    
    Returns:
        dict: JSON response with success status and message
    
    Responses:
        200: Image successfully added
        400: Invalid base64 encoding
        401: Unauthorized or invalid token
    
    Note:
        Image must be base64-encoded for transmission.
        Stored as binary data in the database.
    """
    auth = await authorize_admin(token, request)
    if auth is not True:
        return auth
    try:
        image_bytes = base64.b64decode(image_binary, validate=True)
    except Exception:
        return api_response(message="Invalid image encoding", success=False, status_code=400)
    PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
    if not image_bytes.startswith(PNG_MAGIC):
        return api_response("Only PNG images are allowed", success=False, status_code=400)

    async with get_session() as session:
        image = Images(teacher_id=teacher_id, image=image_bytes)
        session.add(image)
        await session.commit()
    log.info(f"Added image for teacher {teacher_id} by admin {request.client.host}")
    return api_response(message="Successfully added image.")

@router.get("/admin/get_images", response_model=AdminResponse)
@limiter.limit("20/minute")
@cache(expire=60)
async def get_images(teacher_id: int, token: str, request: Request):
    """
    Get all profile images for a teacher.
    
    Retrieves all images associated with a specific teacher. Images are returned
    as base64-encoded strings. Results are cached for 60 seconds.
    Requires admin authentication.
    
    Args:
        teacher_id (int): ID of the teacher
        token (str): Admin authentication token
        request (Request): HTTP request object (for client IP logging)
    
    Returns:
        dict: JSON response with:
            - data: List of image objects containing id, teacher_id, and base64-encoded image
    
    Responses:
        200: Images successfully retrieved
        401: Unauthorized or invalid token
    
    Rate Limits:
        - 20 requests per minute
    
    Caching:
        - Results cached for 60 seconds
    """
    auth = await authorize_admin(token, request)
    if auth is not True:
        return auth
    async with get_session() as session:
        result = await session.execute(
            select(Images).where(Images.teacher_id == teacher_id)
        )
        images = result.scalars().all()
        images_data = []
        for img in images:
            images_data.append({
                "id": img.id,
                "teacher_id": img.teacher_id,
                "image": base64.b64encode(img.image).decode("utf-8"), # this is important
            })
    log.info(f"Retrieved {len(images_data)} images for teacher {teacher_id} by admin {request.client.host}")
    return api_response(data=images_data)

@router.post("/admin/delete_image", response_model=AdminResponse)
async def delete_image(image_id: int, token: str, request: Request):
    """
    Delete a specific teacher profile image.
    
    Removes an image record from the database. Requires admin authentication.
    
    Args:
        image_id (int): ID of the image to delete
        token (str): Admin authentication token
        request (Request): HTTP request object (for client IP logging)
    
    Returns:
        dict: JSON response with success status and message
    
    Responses:
        200: Image successfully deleted
        404: Image not found
        401: Unauthorized or invalid token
    """
    auth = await authorize_admin(token, request)
    if auth is not True:
        return auth
    async with get_session() as session:
        result = await session.execute(
            select(Images).where(Images.id == image_id)
        )
        image = result.scalars().first()
        if not image:
            return api_response(message="Image not found", success=False, status_code=404)
        await session.delete(image)
        await session.commit()
    log.info(f"Deleted image {image_id} by admin {request.client.host}")
    return api_response(message="Successfully deleted image.")

@router.post("/admin/disable_image", response_model=AdminResponse)
async def disable_image(image_id: int, disable: bool, token: str, request: Request):
    """
    Enable or disable a teacher profile image.
    
    Toggles the disabled status of an image. Disabled images may not be displayed
    to students during voting. Requires admin authentication.
    
    Args:
        image_id (int): ID of the image to modify
        disable (bool): True to disable, False to enable
        token (str): Admin authentication token
        request (Request): HTTP request object (for client IP logging)
    
    Returns:
        dict: JSON response with success status and message
    
    Responses:
        200: Image status successfully updated
        404: Image not found
        401: Unauthorized or invalid token
    
    Note:
        Disabling an image does not delete it, just prevents display.
    """
    auth = await authorize_admin(token, request)
    if auth is not True:
        return auth
    async with get_session() as session:
        result = await session.execute(
            select(Images).where(Images.id == image_id)
        )
        image = result.scalars().first()
        if not image:
            return api_response(message="Image not found", success=False, status_code=404)
        image.disabled = disable
        await session.commit()
        log.info(f"Disabled/enabled image {image_id} by admin {request.client.host}")
    return api_response(message=f"Successfully {'disabled' if disable else 'enabled'} image.")

@router.get("/admin/list_images", response_model=AdminResponse)
@cache(expire=60)
async def list_images(token: str, request: Request):
    """
    List all teacher profile images in the system.
    
    Retrieves metadata about all images (not the images themselves).
    Results are cached for 60 seconds. Requires admin authentication.
    
    Args:
        token (str): Admin authentication token
        request (Request): HTTP request object (for client IP logging)
    
    Returns:
        dict: JSON response with:
            - data: List of image metadata objects containing id, teacher_id, disabled status, timestamp
    
    Responses:
        200: Image list successfully retrieved
        401: Unauthorized or invalid token
    
    Caching:
        - Results cached for 60 seconds
    
    Note:
        This endpoint returns metadata only, not the actual image data.
        Use /admin/get_images to retrieve actual image content.
    """
    auth = await authorize_admin(token, request)
    if auth is not True:
        return auth
    async with get_session() as session:
        result = await session.execute(
            select(Images)
        )
        images = result.scalars().all()
        images_data = []
        for img in images:
            images_data.append({
                "id": img.id,
                "teacher_id": img.teacher_id,
                "disabled": img.disabled,
                "timestamp": img.timestamp,
            })
    log.info(f"Listed {len(images_data)} images by admin {request.client.host}")
    return api_response(data=images_data)

@router.post("/admin/disable_all_images", response_model=AdminResponse)
async def disable_all_images(token: str, request: Request):
    """
    Disable all active teacher profile images at once.
    
    Mass-disables all currently active images. Disabled images will not be
    displayed to students during voting. Requires admin authentication.
    
    Args:
        token (str): Admin authentication token
        request (Request): HTTP request object (for client IP logging)
    
    Returns:
        dict: JSON response with success status and message
    
    Responses:
        200: All images successfully disabled
        401: Unauthorized or invalid token
    
    Warning:
        This disables ALL active images. Images are not deleted, just hidden.
    """
    auth = await authorize_admin(token, request)
    if auth is not True:
        return auth
    async with get_session() as session:
        result = await session.execute(
            select(Images).where(Images.disabled == False)
        )
        votecodes = result.scalars().all()
        for vc in votecodes:
            vc.disabled = True
        await session.commit()
    log.info(f"Disabled all images by admin {request.client.host}")
    log.warning(f"All images have been disabled by admin {request.client.host}")
    return api_response(message=f"Successfully disabled all images.")
