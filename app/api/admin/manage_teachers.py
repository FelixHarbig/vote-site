from api.router import router
from fastapi_cache.decorator import cache
from common.log_handler import log
from fastapi import Request
from database.models import get_session, Teachers
import os
from api.utils import api_response
from sqlalchemy import select
import base64
from typing import List
from .utils import authorize_admin
from ..schemas import AdminResponse
from database.utils import fetch_teachers

@router.post("/admin/add_teacher", response_model=AdminResponse)
async def add_teacher(name: str, gender: bool, subjects: List[str], token: str, request: Request):
    """
    Add a new teacher to the system.
    
    Creates a new teacher record in the database. Requires admin authentication.
    
    Args:
        name (str): Full name of the teacher
        gender (bool): Gender identifier (True/False)
        subjects (List[str]): List of subjects taught by the teacher
        token (str): Admin authentication token
        request (Request): HTTP request object (for client IP logging)
    
    Returns:
        dict: JSON response with success status and message
    
    Responses:
        200: Teacher successfully added
        401: Unauthorized or invalid token
        403: Forbidden - insufficient permissions
    
    Note:
        Requires valid admin token. Teacher will be enabled by default.
    """
    auth = await authorize_admin(token, request)
    if auth is not True:
        return auth
    async with get_session() as session:
        teacher = Teachers(name=name, gender=gender, subjects=subjects)
        session.add(teacher)
        await session.commit()
    log.info(f"Added teacher {name} by admin {request.client.host}")
    return api_response(message="Successfully added teacher.")

@router.post("/admin/delete_teacher", response_model=AdminResponse)
async def delete_teacher(teacher_id: int, token: str, request: Request):
    """
    Permanently delete a teacher from the system.
    
    Removes a teacher record completely from the database. Requires admin authentication.
    
    Args:
        teacher_id (int): ID of the teacher to delete
        token (str): Admin authentication token
        request (Request): HTTP request object (for client IP logging)
    
    Returns:
        dict: JSON response with success status and message
    
    Responses:
        200: Teacher successfully deleted
        404: Teacher not found
        401: Unauthorized or invalid token
    
    Warning:
        This action is permanent and cannot be undone. Associated votes may be affected.
    """
    auth = await authorize_admin(token, request)
    if auth is not True:
        return auth
    async with get_session() as session:
        result = await session.execute(
            select(Teachers).where(Teachers.id == teacher_id)
        )
        teacher = result.scalars().first()
        if not teacher:
            return api_response(message="Teacher not found", success=False, status_code=404)
        await session.delete(teacher)
        await session.commit()
    log.info(f"Deleted teacher {teacher_id} by admin {request.client.host}")
    return api_response(message="Successfully deleted teacher.")

@router.get("/admin/list_teachers", response_model=AdminResponse)
@cache(expire=60)
async def list_teachers(token: str, request: Request):
    """
    List all teachers in the system.
    
    Retrieves a list of all teacher records. Results are cached for 60 seconds.
    Requires admin authentication.
    
    Args:
        token (str): Admin authentication token
        request (Request): HTTP request object (for client IP logging)
    
    Returns:
        dict: JSON response with:
            - data: List of teacher objects containing id, name, gender, subjects
            - status_code: HTTP status code
    
    Responses:
        200: List of teachers successfully retrieved
        401: Unauthorized or invalid token
    
    Caching:
        - Results cached for 60 seconds
        - Reduces database load for frequent admin checks
    """
    auth = await authorize_admin(token, request)
    if auth is not True:
        return auth
    teachers_list = await fetch_teachers()
    # async with get_session() as session:
    #     result = await session.execute(select(Teachers))
    #     teachers = result.scalars().all()
    #     teachers_data = []
    #     for t in teachers:
    #         teachers_data.append({
    #             "id": t.id,
    #             "name": t.name,
    #             "gender": t.gender,
    #             "subjects": t.subjects,
    #         }) # could be useful if you add admin stuff to teachers later. should make a new option in fetch_teachers tho
    log.info(f"Listed {len(teachers_list)} teachers by admin {request.client.host}")
    return api_response(data=teachers_list)

@router.post("/admin/disable_teacher", response_model=AdminResponse)
async def disable_teacher(teacher_id: int, disable: bool, token: str, request: Request):
    """
    Enable or disable a teacher.
    
    Toggles the disabled status of a teacher without deleting their record.
    Disabled teachers will not appear in voting lists. Requires admin authentication.
    
    Args:
        teacher_id (int): ID of the teacher to modify
        disable (bool): True to disable, False to enable
        token (str): Admin authentication token
        request (Request): HTTP request object (for client IP logging)
    
    Returns:
        dict: JSON response with success status and message
    
    Responses:
        200: Teacher status successfully updated
        404: Teacher not found
        401: Unauthorized or invalid token
    
    Note:
        Disabling a teacher does not delete their record or associated votes.
    """
    auth = await authorize_admin(token, request)
    if auth is not True:
        return auth
    async with get_session() as session:
        result = await session.execute(
            select(Teachers).where(Teachers.id == teacher_id)
        )
        teacher = result.scalars().first()
        if not teacher:
            return api_response(message="Teacher not found", success=False, status_code=404)
        teacher.disabled = disable
        await session.commit()
    log.info(f"{'Disabled' if disable else 'Enabled'} teacher {teacher_id} by admin {request.client.host}")
    return api_response(message=f"Successfully {'disabled' if disable else 'enabled'} teacher.")

@router.get("/admin/get_teacher", response_model=AdminResponse)
async def get_teacher(teacher_id: int, token: str, request: Request):
    """
    Get details of a specific teacher.
    
    Retrieves all information about a single teacher by ID.
    Requires admin authentication.
    
    Args:
        teacher_id (int): ID of the teacher to retrieve
        token (str): Admin authentication token
        request (Request): HTTP request object (for client IP logging)
    
    Returns:
        dict: JSON response with:
            - data: Teacher object containing id, name, gender, subjects, disabled status
            - status_code: HTTP status code
    
    Responses:
        200: Teacher details successfully retrieved
        404: Teacher not found
        401: Unauthorized or invalid token
    """
    auth = await authorize_admin(token, request)
    if auth is not True:
        return auth
    async with get_session() as session:
        result = await session.execute(
            select(Teachers).where(Teachers.id == teacher_id)
        )
        teacher = result.scalars().first()
        if not teacher:
            return api_response(message="Teacher not found", success=False, status_code=404)
        teacher_data = {
            "id": teacher.id,
            "name": teacher.name,
            "gender": teacher.gender,
            "subjects": teacher.subjects,
            "disabled": teacher.disabled,
        }
    log.info(f"Retrieved teacher {teacher_id} by admin {request.client.host}")
    return api_response(data=teacher_data)
