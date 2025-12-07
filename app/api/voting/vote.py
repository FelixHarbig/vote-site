from ..router import router
from fastapi_cache.decorator import cache
from common.log_handler import log
from fastapi import Request, Body, Response
from ..utils import api_response, get_image_from_cache, set_image_cache
from ..rate_limiter import limiter
import random
import string
import os
from sqlalchemy import select
from database.models import get_session, VoteCodes, Teachers, Votes, Images
from database.utils import fetch_teachers
from typing import Dict, Any
from .tracker import track_metrics, vote_verifications_total, vote_solves_total, vote_submissions_total
from ..anti_abuse import register_failed_ip
from ..schemas import VoteVerifyResponse, TeachersListResponse, VoteSubmissionItem, VoteSubmitResponse


async def verify_challenge(challenge: str, request: Request, awaiting: bool = False) -> bool:
    async with get_session() as session:
        print(challenge)
        key_value = "awaiting" + challenge if awaiting else challenge
        vote = await session.execute(
            select(VoteCodes).where((VoteCodes.continuation_key == key_value) & (VoteCodes.disabled == False) & (VoteCodes.used == False))
        )
        vote = vote.scalars().first()
        if not vote:
            await register_failed_ip(request.client.host)
            log.warning(f"Invalid challenge attempt from {request.client.host}: {challenge}")
            return api_response(message="Invalid challenge.", success=False, status_code=404)
        if awaiting:
            vote.continuation_key = str(challenge)
            await session.commit()
        return True

@router.post("/vote/verify", response_model=VoteVerifyResponse)
@track_metrics(vote_verifications_total, "verify_vote")
@limiter.limit("10/hour" if os.getenv("DEV").upper() != "TRUE" else "20/minute")
async def verify_vote(vote_code: str, request: Request):
    """
    Verify a vote code and receive a challenge token.
    
    This is the first step in the voting process. The student submits their vote code
    and receives a 32-character challenge token if the code is valid.
    
    Args:
        vote_code (str): The unique vote code provided to the student
        request (Request): The HTTP request object (provides client IP for logging)
    
    Returns:
        dict: JSON response with:
            - message: Status message
            - success: Boolean indicating success
            - data: Contains "challenge" token if successful
            - status_code: HTTP status code
    
    Responses:
        200: Vote code verified successfully. Returns challenge token.
        404: Invalid vote code (ID: 1) or code already used (ID: 3)
        400: Vote code already verified (ID: 2)
    
    Rate Limits:
        - Production: 10 attempts per hour
        - Development: 20 attempts per minute
    
    Note:
        Failed attempts register the IP address for anti-abuse tracking.
    """
    log.info(f"Vote verification requested from {request.client.host} for code {vote_code}")

    async with get_session() as session:
        vote = await session.execute(
            select(VoteCodes).where((VoteCodes.code == vote_code) & (VoteCodes.disabled == False))
        )
        vote = vote.scalars().first()
        if not vote:
            await register_failed_ip(request.client.host)
            log.warning(f"Invalid vote code attempt from {request.client.host}: {vote_code}")
            return api_response(message="Invalid vote code. ID: 1", success=False, status_code=404)
        elif vote.used:
            log.info(f"USED vote code attempt from {request.client.host}: {vote_code}")
            return api_response(message="Invalid vote code. ID: 3", success=False, status_code=400)
        elif vote.continuation_key and not vote.continuation_key.startswith("awaiting"):
            await register_failed_ip(request.client.host)
            log.info(f"Vote code already verified from {request.client.host}: {vote_code}")
            return api_response(message="Invalid vote code. ID: 2", success=False, status_code=400)
        challenge = ''.join(random.SystemRandom().choice(string.ascii_letters + string.digits)for _ in range(32))
        vote.continuation_key = "awaiting"+challenge
        await session.commit()
    log.info(f"Vote code verified from {request.client.host}: {vote_code}")
    return api_response(message="Vote code verified.", data={"challenge": challenge})

@router.post("/vote/solve", response_model=TeachersListResponse)
@track_metrics(vote_solves_total, "solve_vote")
@limiter.limit("5/hour" if os.getenv("DEV").upper() != "TRUE" else "20/minute")
async def solve_vote(vote_code: str, challenge: str, request: Request):
    """
    Solve the challenge and unlock teacher list retrieval.
    
    This is the second step in the voting process. The student submits both the vote code
    and the challenge token received from /vote/verify. On success, they receive the list
    of available teachers to vote on.
    
    Args:
        vote_code (str): The original vote code
        challenge (str): The challenge token from /vote/verify response
        request (Request): The HTTP request object (provides client IP for logging)
    
    Returns:
        dict: JSON response with:
            - message: Status message
            - success: Boolean indicating success
            - data: List of teacher objects if successful
            - status_code: HTTP status code
    
    Responses:
        200: Challenge solved successfully. Returns available teachers list.
        404: Invalid vote code or challenge
        400: Invalid challenge provided
    
    Rate Limits:
        - Production: 5 attempts per hour
        - Development: 20 attempts per minute
    
    Note:
        The challenge-response mechanism prevents unauthorized voting.
    """
    log.info(f"Vote solving requested from {request.client.host} for code {vote_code}")
    
    valid = await verify_challenge(challenge=challenge, request=request, awaiting=True)
    if valid is not True:
        return valid
    teachers = await fetch_teachers()
    log.info(f"Vote challenge successfully solved from {request.client.host} for code {vote_code}")
    return api_response(message="Vote successfully solved.", data=teachers)


@router.get("/vote/get_teachers", response_model=TeachersListResponse)
@limiter.limit("5/minute" if os.getenv("DEV").upper() != "TRUE" else "20/minute")
@cache(expire=600) # change this to whatever you want, 1 = 1 second
async def get_teachers(request: Request, challenge: str):
    """
    Retrieve the list of available teachers.
    
    This endpoint provides the teacher list for voting. It's a cached endpoint used
    either after /vote/solve or when the cache expires and needs refreshing.
    
    Args:
        request (Request): The HTTP request object (provides client IP for logging)
        challenge (str): The valid challenge token from /vote/solve
    
    Returns:
        dict: JSON response with:
            - message: Status message
            - success: Boolean indicating success
            - data: List of teacher objects with their details
            - status_code: HTTP status code
    
    Responses:
        200: Teachers successfully retrieved
        404: Invalid or expired challenge
    
    Rate Limits:
        - Production: 5 requests per minute
        - Development: 20 requests per minute
    
    Caching:
        - Results are cached for 600 seconds (10 minutes)
        - Cache key includes the endpoint, reducing database load
    
    Note:
        Challenge must be a valid challenge from /vote/solve.
    """
    log.info(f"Teachers request from {request.client.host} with challenge {challenge}")
    valid = await verify_challenge(challenge=challenge, request=request)
    if valid is not True:
        return valid
    teachers = await fetch_teachers()
    log.info(f"Teachers successfully requested from {request.client.host}")
    return api_response(message="Teachers successfully retrieved.", data=teachers)

@router.get("/vote/options")
async def get_vote_options(request: Request, challenge: str):
    valid = await verify_challenge(challenge=challenge, request=request)
    if valid is not True:
        return valid
    options = []
    for field_name, _ in VoteSubmissionItem.model_fields.items():
        options.append(field_name)
    return api_response(message="Vote options retrieved.", data=options)

@router.get("/vote/image", response_class=Response)
@limiter.limit("10/minute" if os.getenv("DEV").upper() != "TRUE" else "60/minute")
async def get_image(teacher_id: int, request: Request, challenge: str, number: int = 1):
    if not (challenge == os.getenv("ADMIN_SECRET") and os.getenv("DEV").upper() == "TRUE"):
        valid = await verify_challenge(challenge=challenge, request=request)
        if valid is not True:
            return valid
    cached = await get_image_from_cache(teacher_id, number)
    if cached:
        log.info(f"Serving cached image for teacher {teacher_id}")
        return Response(content=cached, media_type="image/png")

    async with get_session() as session:
        image_result = await session.execute(
            select(Images).where(Images.teacher_id == teacher_id)
        )
        images = image_result.scalars().all()
        if not images:
            return api_response(message="Image not found.", success=False, status_code=404)

    img_bytes = images[number-1].image
    await set_image_cache(teacher_id, number, img_bytes, expire=600)
    return Response(content=img_bytes, media_type="image/png")


@router.post("/vote/submit", response_model=VoteSubmitResponse)
@track_metrics(vote_submissions_total, "submit_vote")
@limiter.limit("5/hour" if os.getenv("DEV").upper() != "TRUE" else "20/minute")
async def submit_vote(request: Request, challenge: str, vote_data: Dict[str, VoteSubmissionItem] = Body(...)):
    """
    Submit votes for one or more teachers.
    
    This is the final step in the voting process. The student submits their votes for
    multiple teachers at once. All votes must be included in a single request. After
    successful submission, both the challenge and vote code are invalidated.
    
    Args:
        request (Request): The HTTP request object (provides client IP for logging)
        challenge (str): The valid challenge token from /vote/solve
        vote_data (VoteBatch): Dictionary mapping teacher_id to VoteSubmission objects
            Example: {"1": {"overall": 5}, "2": {"overall": 4}}
    
    Returns:
        dict: JSON response with:
            - message: Status message
            - success: Boolean indicating success
            - status_code: HTTP status code
    
    Responses:
        200: Votes successfully submitted
        404: Invalid challenge or teacher not found
        400: Invalid data format or teacher disabled
    
    Rate Limits:
        - Production: 5 submissions per hour
        - Development: 20 submissions per minute
    
    Important Notes:
        - ALL votes must be submitted in a single request
        - After submission, the challenge and vote code are invalidated
        - Cannot submit partial votes and return later to add more
        - All referenced teachers must exist and be enabled
    
    Example Request Body:
        {
            "1": {"overall": 5},
            "2": {"overall": 4},
            "3": {"overall": 3}
        }
    """
    log.info(f"Vote submission requested from {request.client.host} for challenge {challenge}")
    try:
        async with get_session() as session:
            vote = await session.execute(
                select(VoteCodes).where((VoteCodes.continuation_key == challenge) & (VoteCodes.disabled == False))
            )
            vote = vote.scalars().first()
            if not vote or vote.used:
                log.warning(f"Invalid challenge attempt from {request.client.host}: {challenge}")
                return api_response(message="Invalid challenge.", success=False, status_code=404)
            
            teacher_ids = [int(tid) for tid in vote_data.keys() if tid.isdigit()]
            teachers_query = await session.execute(
                select(Teachers).where(Teachers.id.in_(teacher_ids), Teachers.disabled == False)
            )
            valid_teachers = {t.id for t in teachers_query.scalars().all()}
            log.debug(f"Valid teachers found: {valid_teachers} | Expected: {teacher_ids}")
            if len(valid_teachers) != len(teacher_ids):
                invalid = set(teacher_ids) - valid_teachers
                return api_response(message=f"Invalid teachers: {invalid}", success=False, status_code=404)
            
            # Get all valid vote field names from Votes model
            votes_model_fields = {col.name for col in Votes.__table__.columns 
                                  if col.name not in ('id', 'teacher_id', 'timestamp', 'ip_address')}
            
            for teacher_id, submission in vote_data.items():
                if not teacher_id.isdigit():
                    await session.rollback()
                    log.info(f"Invalid teacher ID format: {teacher_id} from {request.client.host}")
                    return api_response(message=f"Invalid teacher ID: {teacher_id}", success=False, status_code=400)

                vote_kwargs = {
                    'teacher_id': int(teacher_id),
                }
                
                # Add all submitted vote fields that are valid in the model
                for field_name, field_value in submission.model_dump(exclude_none=True).items():
                    if field_name in votes_model_fields and field_value is not None:
                        vote_kwargs[field_name] = field_value
                
                new_vote = Votes(**vote_kwargs)
                session.add(new_vote)
            
            vote.used = True
            try:
                await session.commit()
            except Exception as e:
                await session.rollback()
                log.error(f"Error committing votes from {request.client.host}: {e}")
                return api_response(message="Error submitting votes.", success=False, status_code=500)
        log.info(f"Vote successfully submitted from {request.client.host} for challenge {challenge}")
        return api_response(message="Vote successfully submitted.")
    except Exception as e:
        log.error(f"Unexpected error during vote submission from {request.client.host}: {e}")
        return api_response(message="Unexpected error during vote submission.", success=False, status_code=500)