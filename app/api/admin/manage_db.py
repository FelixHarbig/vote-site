from fastapi import Request, Query, Body, HTTPException
from sqlalchemy.inspection import inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select
from database.models import Teachers, Votes, Images, VoteCodes, get_session
from api.router import router
import os
from common.log_handler import log
from ..utils import api_response
from datetime import datetime, date
from ..anti_abuse import register_failed_ip
from .utils import authorize_admin
from ..schemas import AdminResponse




MODEL_MAP = {
    "teachers": Teachers,
    "votes": Votes,
    "images": Images,
    "votecodes": VoteCodes,
}

def serialize_row(row):
    result = {}
    for c in inspect(row).mapper.column_attrs:
        value = getattr(row, c.key)

        # Convert datetime/date to ISO string
        if isinstance(value, (datetime, date)):
            value = value.isoformat()
        # Convert bytes to base64 string
        elif isinstance(value, bytes):
            import base64
            value = base64.b64encode(value).decode('utf-8')
        result[c.key] = value
    return result

def safe_cast(value, to_type):
    # Treat empty string as None
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None
    elif to_type is bool:
        if isinstance(value, bool):
            return value
        elif isinstance(value, str):
            if value.lower() in ("true", "1", "yes", "on"):
                return True
            elif value.lower() in ("false", "0", "no", "off"):
                return False
        return bool(value)
    elif to_type is int:
        return int(value)
    elif to_type is float:
        return float(value)
    elif to_type is datetime:
        return datetime.fromisoformat(value)
    return to_type(value)



@router.get("/admin/db/list_tables", response_model=AdminResponse)
async def list_tables(token: str, request: Request):
    """
    List all available database tables.
    
    Returns the names of all tables that can be queried and edited via the
    database management API. Requires admin authentication.
    
    Args:
        token (str): Admin authentication token
        request (Request): HTTP request object (for client IP logging)
    
    Returns:
        dict: JSON response with:
            - data: List of table names (teachers, votes, images, votecodes)
    
    Responses:
        200: Table list successfully retrieved
        401: Unauthorized or invalid token
    """
    auth = await authorize_admin(token, request)
    if auth is not True:
        return auth
    log.info(f"Listed tables by admin {request.client.host}")
    return api_response(data=list(MODEL_MAP.keys()))


@router.get("/admin/db/fetch", response_model=AdminResponse)
async def fetch_table(
    token: str,
    request: Request,
    table: str = Query(...),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    descending: bool = Query(False)
):
    """
    Fetch rows from a database table with pagination.
    
    Retrieves data from any specified table with support for pagination.
    Datetime/date values are converted to ISO strings, binary data to base64.
    Requires admin authentication.
    
    Args:
        token (str): Admin authentication token
        request (Request): HTTP request object (for client IP logging)
        table (str): Name of the table to query (teachers, votes, images, votecodes)
        limit (int): Maximum rows to return (1-1000, default 100)
        offset (int): Number of rows to skip (default 0)
    
    Returns:
        dict: JSON response with:
            - data: List of serialized row objects
    
    Responses:
        200: Rows successfully retrieved
        400: Invalid table name
        401: Unauthorized or invalid token
    
    Serialization:
        - datetime/date objects converted to ISO format strings
        - binary data (images) converted to base64 strings
        - all types properly type-cast
    """
    auth = await authorize_admin(token, request)
    if auth is not True:
        return auth

    model = MODEL_MAP.get(table)
    if not model:
        return api_response(message="Invalid table", success=False, status_code=400)

    async with get_session() as session:
        stmt = select(model).order_by(model.id if not descending else model.id.desc()).offset(offset).limit(limit)
        rows = (await session.execute(stmt)).scalars().all()

    log.info(f"Fetched {len(rows)} rows from table '{table}' (offset {offset}, limit {limit}) by admin {request.client.host}")

    return api_response(data=[serialize_row(r) for r in rows])


@router.post("/admin/db/edit", response_model=AdminResponse)
async def edit_table(
    token: str,
    request: Request,
    table: str = Query(...),
    pk: str = Query(...),
    field: str = Query(...),
    value: str = Query(...)
):
    """
    Edit a single field in a database row.
    
    Modifies one field of a single row identified by primary key.
    Supports type casting for booleans, integers, floats, and strings.
    Requires admin authentication.
    
    Args:
        token (str): Admin authentication token
        request (Request): HTTP request object (for client IP logging)
        table (str): Name of the table to edit
        pk (str): Primary key value of the row to edit
        field (str): Field/column name to modify
        value (str): New value (will be type-cast based on column type)
    
    Returns:
        dict: JSON response with:
            - data: Updated row object
            - success: Boolean indicating success
    
    Responses:
        200: Field successfully updated
        400: Invalid table, field, or value type
        404: Row not found
        401: Unauthorized or invalid token
        500: Database error
    
    Type Casting:
        - Boolean: Accepts true/false/yes/no/1/0/on/off (case-insensitive)
        - Integer: Parsed as int
        - Float: Parsed as float
        - String: Used as-is, empty string becomes NULL
    """
    auth = await authorize_admin(token, request)
    if auth is not True:
        return auth

    model = MODEL_MAP.get(table)
    if not model:
        return api_response(success=False, message="Invalid table", status_code=400)

    if not hasattr(model, field):
        return api_response(success=False, message="Invalid field", status_code=400)

    pk_name = inspect(model).primary_key[0].name
    pk_column = getattr(model, pk_name)
    pk_value = safe_cast(pk, pk_column.type.python_type)

    async with get_session() as session:
        row_stmt = select(model).where(pk_column == pk_value)
        row = (await session.execute(row_stmt)).scalar_one_or_none()

        if not row:
            return api_response(success=False, message="Row not found", status_code=404)

        col = getattr(model, field)
        try:
            cast_value = safe_cast(value, col.type.python_type)
        except Exception as e:
            return api_response(success=False, message=f"Invalid value: {e}", status_code=400)

        setattr(row, field, cast_value)

        try:
            await session.commit()
        except SQLAlchemyError as e:
            await session.rollback()
            log.error(f"DB error on editing row {pk} in table '{table}': {e}")
            return api_response(success=False, message=f"DB error: {e}", status_code=500)
    
    log.info(f"Edited row {pk} in table '{table}' by admin {request.client.host}")
    return api_response(success=True, data=serialize_row(row), message="Row updated")


@router.post("/admin/db/edit_row", response_model=AdminResponse)
async def edit_row(
    token: str,
    request: Request,
    table: str = Query(...),
    pk: str = Query(...),
    body: dict = Body(...)
):
    """
    Edit multiple fields in a database row at once.
    
    Modifies multiple fields of a single row in one request. More efficient than
    calling /admin/db/edit multiple times. Requires admin authentication.
    
    Args:
        token (str): Admin authentication token
        request (Request): HTTP request object (for client IP logging)
        table (str): Name of the table to edit
        pk (str): Primary key value of the row to edit
        body (dict): Dictionary of field names to new values
    
    Returns:
        dict: JSON response with:
            - data: Updated row object
            - success: Boolean indicating success
    
    Responses:
        200: Row successfully updated
        400: Invalid table, field, or value type
        404: Row not found
        401: Unauthorized or invalid token
        500: Database error
    
    Example Request Body:
        {
            "name": "New Name",
            "disabled": true,
            "overall": 5
        }
    """
    auth = await authorize_admin(token, request)
    if auth is not True:
        return auth

    model = MODEL_MAP.get(table)
    if not model:
        return api_response(success=False, message="Invalid table")

    pk_name = inspect(model).primary_key[0].name
    pk_column = getattr(model, pk_name)
    pk_value = safe_cast(pk, pk_column.type.python_type)

    async with get_session() as session:
        stmt = select(model).where(pk_column == pk_value)
        row = (await session.execute(stmt)).scalar_one_or_none()

        if not row:
            return api_response(success=False, message="Row not found")

        model_columns = {c.name: c for c in inspect(model).columns}

        try:
            for field, value in body.items():
                if field not in model_columns:
                    return api_response(success=False, message=f"Invalid field: {field}")

                col = model_columns[field]
                cast_value = safe_cast(value, col.type.python_type)

                setattr(row, field, cast_value)

            await session.commit()
            log.info(f"Edited row {pk} in table '{table}' by admin {request.client.host}")
            return api_response(success=True, data=serialize_row(row))

        except SQLAlchemyError as e:
            await session.rollback()
            log.error(f"DB error on editing row {pk} in table '{table}': {e}")
            return api_response(success=False, message=f"DB error: {e}")
        except Exception as e:
            log.error(f"Unexpected error on editing row {pk} in table '{table}': {e}")
            return api_response(success=False, message=f"Unexpected error: {e}")


@router.post("/admin/db/add", response_model=AdminResponse)
async def add_table_row(
    token: str,
    request: Request,
    table: str = Query(...)
):
    """
    Add a new row to a database table.
    
    Creates a new record in the specified table with provided field values.
    Validates all required fields are present and types are correct.
    Requires admin authentication.
    
    Args:
        token (str): Admin authentication token
        request (Request): HTTP request object (for client IP logging)
        table (str): Name of the table to insert into
        body (dict): Request JSON body with field values
    
    Returns:
        dict: JSON response with:
            - data: Created row object with all fields
            - success: Boolean indicating success
    
    Responses:
        200: Row successfully created
        400: Invalid table, missing required field, or type mismatch
        401: Unauthorized or invalid token
        500: Database error
    
    Validation:
        - All non-nullable, non-default, non-primary-key fields required
        - Type casting applied to match column types
        - Primary key auto-generated if applicable
    
    Example Request Body:
        {
            "name": "John Smith",
            "gender": true,
            "subjects": ["Math", "Science"]
        }
    """
    auth = await authorize_admin(token, request)
    if auth is not True:
        return auth

    body = await request.json()

    model = MODEL_MAP.get(table)
    if not model:
        return api_response(success=False, message="Invalid table")

    model_columns = {c.name: c for c in inspect(model).columns}
    new_data = {}

    # Validate + cast
    for field, col in model_columns.items():
        if field in body:
            try:
                new_data[field] = safe_cast(body[field], col.type.python_type)
            except Exception as e:
                return api_response(success=False, message=f"Invalid type for '{field}': {e}")
        else:
            # Required field test
            if not col.nullable and col.default is None and not col.primary_key:
                return api_response(success=False, message=f"Missing required field '{field}'")

    row = model(**new_data)

    async with get_session() as session:
        try:
            session.add(row)
            await session.commit()
            log.info(f"Added new row to table '{table}' by admin {request.client.host}")
            return api_response(success=True, data=serialize_row(row))

        except SQLAlchemyError as e:
            await session.rollback()
            log.error(f"DB error on adding row to '{table}': {e}")
            return api_response(success=False, message=f"DB error: {e}")


@router.delete("/admin/db/remove", response_model=AdminResponse)
async def remove_row(
    token: str,
    request: Request,
    table: str = Query(...),
    pk: str = Query(...)
):
    """
    Delete a row from a database table.
    
    Permanently removes a single row identified by primary key.
    This is a destructive operation. Requires admin authentication.
    
    Args:
        token (str): Admin authentication token
        request (Request): HTTP request object (for client IP logging)
        table (str): Name of the table to delete from
        pk (str): Primary key value of the row to delete
    
    Returns:
        dict: JSON response with:
            - success: Boolean indicating success
            - message: Status message
    
    Responses:
        200: Row successfully deleted
        400: Invalid table
        404: Row not found
        401: Unauthorized or invalid token
        500: Database error
    
    Warning:
        This action permanently deletes the row and cannot be easily undone.
        Ensure you have appropriate backups before using this endpoint.
    """
    auth = await authorize_admin(token, request)
    if auth is not True:
        return auth

    model = MODEL_MAP.get(table)
    if not model:
        return api_response(success=False, message="Invalid table")

    pk_name = inspect(model).primary_key[0].name
    pk_column = getattr(model, pk_name)
    pk_value = safe_cast(pk, pk_column.type.python_type)

    async with get_session() as session:
        stmt = select(model).where(pk_column == pk_value)
        row = (await session.execute(stmt)).scalar_one_or_none()

        if not row:
            return api_response(success=False, message="Row not found")

        try:
            await session.delete(row)
            await session.commit()
            log.info(f"Deleted row {pk} from table '{table}' by admin {request.client.host}")
            return api_response(success=True, message="Row deleted")
        except SQLAlchemyError as e:
            await session.rollback()
            log.error(f"DB error on deleting row {pk} from table '{table}': {e}")
            return api_response(success=False, message=f"DB error: {e}")


