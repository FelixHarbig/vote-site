from .router import admin_router as router
from fastapi_cache.decorator import cache
from common.log_handler import log
from fastapi import Request, Body
from database.models import get_session, VoteCodes, Teachers, Votes
import os
import random
import string
from api.utils import api_response
from sqlalchemy import select

from ..schemas import AdminResponse, VoteSubmissionItem

@router.post("/add_votecodes", response_model=AdminResponse)
async def add_votecodes(amount: int, request: Request, grade: int = 0, gender: bool = None, code: str = None):
    """
    Create one or more vote codes.
    
    Generates new vote codes for distribution to students. Can create codes in bulk or
    specify a custom code. All codes are active by default. Requires admin authentication.
    
    Args:
        amount (int): Number of codes to generate (1-1000)

        request (Request): HTTP request object (for client IP logging)
        grade (int, optional): Grade level filter (0-12, default 0). Defaults to 0.
        gender (bool, optional): Gender filter for eligible voters. Defaults to None.
        code (str, optional): Custom code (only when amount=1). Defaults to None.
    
    Returns:
        dict: JSON response with success status and message
    
    Responses:
        200: Vote codes successfully created
        400: Invalid parameters (amount, grade, or custom code with multiple)
        401: Unauthorized or invalid token
    
    Validation:
        - amount: Must be 1-1000
        - grade: Must be 0-12
        - custom code: Only valid when amount=1
    
    Note:
        Generated codes are 8 random alphanumeric characters if not custom specified.
    """

    if amount <= 0 or amount > 1000:
        return api_response(message="Amount must be between 1 and 1000", success=False, status_code=400)
    if grade < 0 or grade > 12:
        return api_response(message="Grade must be between 0 and 12", success=False, status_code=400)
    if code and amount != 1:
        return api_response(message="Code can only be specified when adding a single votecode", success=False, status_code=400)
    async with get_session() as session:
        if code:
            votecode = VoteCodes(code=code, grade=grade, gender=gender)
            session.add(votecode)
        else:
            for _ in range(amount):
                exists = True
                while exists:
                    code = ''.join(random.SystemRandom().choice(string.ascii_letters + string.digits) for _ in range(8))
                    result = await session.execute(
                        select(VoteCodes.id).where(VoteCodes.code == code)
                    )
                    exists = result.first() is not None
                votecode = VoteCodes(code=code, grade=grade, gender=gender)
                session.add(votecode)
        await session.commit()
    log.info(f"Added {amount} votecodes by admin {request.client.host}")
    return api_response(message=f"Successfully added {amount} votecodes.")

@router.post("/disable_votecode", response_model=AdminResponse)
async def disable_votecode(code: str, request: Request, enable: bool = False):
    """
    Disable or re-enable a vote code.
    
    Prevents a specific vote code from being used for voting. Can be reversed by setting
    enable=True. Requires admin authentication.
    
    Args:
        code (str): The vote code to modify        request (Request): HTTP request object (for client IP logging)
        enable (bool, optional): If True, re-enables the code. If False, disables it. Defaults to False.
    
    Returns:
        dict: JSON response with success status and message
    
    Responses:
        200: Vote code status successfully updated
        404: Vote code not found
        401: Unauthorized or invalid token
    
    Note:
        Disabling a code prevents new votes but doesn't affect already-submitted votes.
    """
    async with get_session() as session:
        votecode = await session.execute(
            select(VoteCodes).filter(VoteCodes.code == code))
        votecode = votecode.scalars().first()
        if not votecode:
            return api_response(message="Votecode not found", success=False, status_code=404)
        if enable:
            votecode.disabled = False
            await session.commit()
            return api_response(message=f"Successfully enabled votecode {code}.")
        votecode.disabled = True
        await session.commit()
    log.info(f"Disabled votecode {code} by admin {request.client.host}")
    return api_response(message=f"Successfully disabled votecode {code}.")

@router.get("/list_votecode_amount", response_model=AdminResponse)
@cache(expire=60)
async def list_votecode_amount(request: Request):
    """
    Get statistics about vote code usage.
    
    Returns counts of total, used, and unused vote codes.
    Results are cached for 60 seconds. Requires admin authentication.
    
    Args:        request (Request): HTTP request object (for client IP logging)
    
    Returns:
        dict: JSON response with:
            - data: Object containing:
                - total_votecodes: Number of active vote codes
                - used_votecodes: Number of already-used codes
                - unused_votecodes: Number of available codes
    
    Responses:
        200: Statistics successfully retrieved
        401: Unauthorized or invalid token
    
    Caching:
        - Results cached for 60 seconds
    """
    async with get_session() as session:
        total_votecodes = await session.execute(
            select(VoteCodes).where(VoteCodes.disabled == False)
        )
        total_votecodes = total_votecodes.scalars().all()
        used_votecodes = [vc for vc in total_votecodes if vc.used]
        unused_votecodes = [vc for vc in total_votecodes if not vc.used]
    log.debug(f"Listed votecode amounts by admin {request.client.host}")
    return api_response(data={
        "total_votecodes": len(total_votecodes),
        "used_votecodes": len(used_votecodes),
        "unused_votecodes": len(unused_votecodes),
    })

@router.get("/get_votecode", response_model=AdminResponse)
async def validate_votecode(code: str, request: Request):
    """
    Get details about a specific vote code.
    
    Retrieves information about a single vote code including its status and usage.
    Requires admin authentication.
    
    Args:
        code (str): The vote code to look up        request (Request): HTTP request object (for client IP logging)
    
    Returns:
        dict: JSON response with:
            - data: Vote code object containing:
                - code: The vote code string
                - used: Whether the code has been used
                - grade: Associated grade level
                - gender: Associated gender filter
                - disabled: Whether the code is disabled
                - continuation_key: Challenge token if in progress
    
    Responses:
        200: Vote code details successfully retrieved
        404: Vote code not found
        401: Unauthorized or invalid token
    """
    async with get_session() as session:
        votecode = await session.execute(
            select(VoteCodes).filter(VoteCodes.code == code))
        votecode = votecode.scalars().first()
        if not votecode:
            return api_response(message="Votecode not found", success=False, status_code=404)
    log.debug(f"Validated votecode {code} by admin {request.client.host}")
    return api_response(data={
        "code": votecode.code,
        "used": votecode.used,
        "grade": votecode.grade,
        "gender": votecode.gender,
        "disabled": votecode.disabled,
        "continuation_key": votecode.continuation_key,
    })

@router.post("/disable_all_votescodes", response_model=AdminResponse)
async def disable_votes_for_teacher(really_sure: bool, request: Request):
    """
    Disable all active vote codes at once.
    
    Mass-disables all currently active vote codes. This is a dangerous operation
    that requires explicit confirmation. Requires admin authentication.
    
    Args:        really_sure (bool): Must be True to confirm this destructive action
        request (Request): HTTP request object (for client IP logging)
    
    Returns:
        dict: JSON response with success status and message
    
    Responses:
        200: All vote codes successfully disabled
        400: Confirmation not provided (really_sure != True)
        401: Unauthorized or invalid token
    
    Warning:
        This action disables ALL active vote codes. Use with caution!
        Already-used codes are not affected as they're already inactive.
    """
    if not really_sure:
        return api_response(message="You must confirm this action by setting really_sure to True", success=False, status_code=400)
    async with get_session() as session:
        result = await session.execute(
            select(VoteCodes).where(VoteCodes.disabled == False)
        )
        votecodes = result.scalars().all()
        for vc in votecodes:
            vc.disabled = True
        await session.commit()
    log.info(f"Disabled all votescodes by admin {request.client.host}")
    log.warning(f"All votescodes have been disabled by admin {request.client.host}")
    return api_response(message=f"Successfully disabled all votescodes.")


"""
    API endpoints for managing Votes themselves, not the VoteCodes
"""

@router.post("/add_vote", response_model=AdminResponse)
async def add_vote(teacher_id: int, request: Request, vote_data: VoteSubmissionItem = Body(...), ip_address: str = None):
    """
    Manually add a vote for a teacher.
    
    Creates a vote record directly without requiring a vote code. Useful for manual
    vote entry by administrators. Uses the same schema as regular vote submissions.
    Requires admin authentication.
    
    Args:
        teacher_id (int): ID of the teacher receiving the vote (query parameter)        request (Request): HTTP request object (for client IP logging)
        vote_data (VoteSubmissionItem): Vote data in request body
            - Any combination of vote fields can be provided (all optional)
            - All numeric vote fields must be between 1-10
        ip_address (str, optional): IP address to associate with the vote (query parameter)
    
    Returns:
        dict: JSON response with success status and message
    
    Responses:
        200: Vote successfully created
        400: No vote fields provided
        401: Unauthorized or invalid token
        404: Teacher not found or is disabled
    
    Note:
        This bypasses the normal vote code challenge flow and is for admin use only.
        Automatically supports all vote types - no schema updates needed when adding new fields!
    """
    
    # Get all valid vote field names from Votes model
    votes_model_fields = {col.name for col in Votes.__table__.columns 
                          if col.name not in ('id', 'teacher_id', 'timestamp', 'ip_address')}
    
    # Extract vote fields from request body (exclude None values)
    vote_fields = {}
    for field_name, field_value in vote_data.model_dump(exclude_none=True).items():
        if field_name in votes_model_fields and field_value is not None:
            vote_fields[field_name] = field_value
    
    # Ensure at least one vote field was provided
    if not vote_fields:
        return api_response(
            message="At least one vote field must be provided (e.g., overall, clarity, helpfulness)",
            success=False,
            status_code=400
        )
    
    async with get_session() as session:
        # Verify teacher exists and is enabled
        teacher = await session.execute(
            select(Teachers).where((Teachers.id == teacher_id) & (Teachers.disabled == False))
        )
        if not teacher.scalars().first():
            return api_response(
                message="Teacher not found or is disabled",
                success=False,
                status_code=404
            )
        
        # Build vote kwargs with provided fields and ip_address
        vote_kwargs = {
            'teacher_id': teacher_id,
            **vote_fields
        }
        if ip_address:
            vote_kwargs['ip_address'] = ip_address
        
        vote = Votes(**vote_kwargs)
        session.add(vote)
        await session.commit()
    
    log.info(f"Added vote for teacher {teacher_id} with fields {list(vote_fields.keys())} by admin {request.client.host}")
    return api_response(message=f"Successfully added vote with {len(vote_fields)} field(s).")

@router.get("/get_votes", response_model=AdminResponse)
async def get_votes(teacher_id: int, request: Request, limit: int = 100, offset: int = 0):
    """
    Get votes for a specific teacher with pagination.
    
    Retrieves all votes received by a teacher with all available vote fields dynamically.
    Results support pagination. Requires admin authentication.
    
    Args:
        teacher_id (int): ID of the teacher        request (Request): HTTP request object (for client IP logging)
        limit (int, optional): Maximum number of votes to return (default 100). Defaults to 100.
        offset (int, optional): Number of votes to skip for pagination (default 0). Defaults to 0.
    
    Returns:
        dict: JSON response with:
            - data: List of vote objects containing all available vote fields
    
    Responses:
        200: Votes successfully retrieved
        401: Unauthorized or invalid token
    
    Pagination:
        - limit and offset control which votes are returned
        - Use offset=100, limit=100 to get votes 101-200, etc.
    """
    async with get_session() as session:
        result = await session.execute(
            select(Votes).where(Votes.teacher_id == teacher_id).offset(offset).limit(limit)
        )
        votes = result.scalars().all()
        votes_data = []
        
        # Get all column names from Votes model
        votes_model_fields = {col.name for col in Votes.__table__.columns 
                          if col.name not in ('id', 'teacher_id', 'timestamp', 'ip_address')}
        
        for v in votes:
            vote_dict = {}
            # Dynamically build response with all available fields
            for col_name in votes_model_fields:
                value = getattr(v, col_name, None)
                # Convert timestamp to ISO format if present
                if col_name == 'timestamp' and value is not None:
                    vote_dict[col_name] = value.isoformat()
                else:
                    vote_dict[col_name] = value
            votes_data.append(vote_dict)
    
    log.debug(f"Retrieved {len(votes_data)} votes for teacher {teacher_id} by admin {request.client.host}")
    return api_response(data=votes_data)

@router.get("/get_vote_count", response_model=AdminResponse)
async def get_vote_count(teacher_id: int, request: Request):
    """
    Get vote statistics for a teacher.
    
    Returns the total vote count and average ratings for all vote types for a specific teacher.
    Requires admin authentication.
    
    Args:
        teacher_id (int): ID of the teacher        request (Request): HTTP request object (for client IP logging)
    
    Returns:
        dict: JSON response with:
            - data: Object containing:
                - vote_count: Total number of votes received
                - averages: Dictionary with average for each vote type (or null if no votes)
    
    Responses:
        200: Vote statistics successfully retrieved
        404: Teacher not found
        401: Unauthorized or invalid token
    """
    async with get_session() as session:
        teacher_result = await session.execute(
            select(Teachers).where(Teachers.id == teacher_id)
        )
        teacher = teacher_result.scalars().first()
        if not teacher:
            return api_response(message="Teacher not found", success=False, status_code=404)

        result = await session.execute(
            select(Votes).where(Votes.teacher_id == teacher_id)
        )
        votes = result.scalars().all()
        vote_count = len(votes)
        
        # Dynamically calculate averages for all numeric vote fields
        averages = {}
        votes_model_fields = {col.name for col in Votes.__table__.columns 
                               if col.name not in ('id', 'teacher_id', 'timestamp', 'ip_address')}
        
        if votes:
            for field_name in votes_model_fields:
                values = [getattr(v, field_name) for v in votes if getattr(v, field_name) is not None]
                if values:
                    averages[field_name] = sum(values) / len(values)
                else:
                    averages[field_name] = None
        else:
            # If no votes, set all averages to None
            for field_name in votes_model_fields:
                averages[field_name] = None

    log.debug(f"Retrieved vote count for teacher {teacher_id} by admin {request.client.host}")
    return api_response(data={
        "vote_count": vote_count,
        "averages": averages,
    })


@router.delete("/delete_votes", response_model=AdminResponse)
async def delete_votes(teacher_id: int, sure: bool, request: Request):
    """
    Delete all votes for a specific teacher.
    
    Removes all vote records for a given teacher. This is a destructive action
    that requires explicit confirmation. Requires admin authentication.
    
    Args:
        teacher_id (int): ID of the teacher whose votes to delete
        sure (bool): Must be True to confirm this destructive action        request (Request): HTTP request object (for client IP logging)
    
    Returns:
        dict: JSON response with success status and message
    
    Responses:
        200: All votes successfully deleted
        400: Confirmation not provided (sure != True)
        401: Unauthorized or invalid token
    
    Warning:
        This action permanently deletes all votes for the teacher.
        This cannot be easily undone without database backups.
    """
    if not sure:
        return api_response(message="You must confirm this action by setting sure to True", success=False, status_code=400)
    async with get_session() as session:
        result = await session.execute(
            select(Votes).where(Votes.teacher_id == teacher_id)
        )
        votes = result.scalars().all()
        for v in votes:
            await session.delete(v)
        await session.commit()
    log.info(f"Deleted all votes for teacher {teacher_id} by admin {request.client.host}")
    return api_response(message="Successfully deleted votes.")


@router.delete("/nuke_ip", response_model=AdminResponse)
async def nuke_ip(ip_address: str, request: Request, all_votes: bool = False):
    """
    Remove all votes associated with a specific IP address.
    
    Deletes all vote records that were submitted from the given IP address.
    Requires admin authentication.
    
    Args:
        ip_address (str): The IP address to delete        request (Request): HTTP request object (for client IP logging)
        all_votes (bool, optional): If True, deletes the votes entirely.
    
    Returns:
        dict: JSON response with success status and message
    
    Responses:
        200: Votes successfully deleted
        401: Unauthorized or invalid token
    
    Note:
        This action removes votes based on IP address and may affect multiple teachers.
    """
    async with get_session() as session:
        result = await session.execute(
            select(Votes).where(Votes.ip_address == ip_address)
        )
        votes = result.scalars().all()
        for v in votes:
            if all_votes:
                await session.delete(v)
            else:
                v.ip_address = None
                session.add(v)
        await session.commit()
    log.info(f"Nuked votes from IP {ip_address} by admin {request.client.host}")
    return api_response(message=f"Successfully deleted {"votes" if all_votes else "ip adress instances in database"} from IP.")