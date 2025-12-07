from api.router import router
from .utils import authorize_admin
from ..schemas import AdminResponse
from fastapi import Request, UploadFile
from api.utils import api_response
import csv
import codecs
from database.models import VoteCodes, get_session, Teachers
import random
import string
from common.log_handler import log
from sqlalchemy import select

@router.post("/admin/upload/votecodes", response_model=AdminResponse)
async def upload_votecodes(token: str, request: Request, uploaded_file: UploadFile, enable_code_generation: bool = False):
    """
        Accetped Fields: code | grade (0-12 integer) | gender (true,false) | disabled
    """
    auth = await authorize_admin(token, request)
    if auth is not True:
        return auth
    if not uploaded_file.filename.endswith(".csv"):
        return api_response(message="Invalid file type", success=False, status_code=400)
    csvReader = csv.DictReader(codecs.iterdecode(uploaded_file.file, 'utf-8'))
    required_fields = {'code', 'grade', 'disabled', 'gender'}
    available_fields = set(csvReader.fieldnames or [])
    missing_fields = required_fields - available_fields
    if missing_fields:
        return api_response(message=f"Missing required columns: {', '.join(missing_fields)}", success=False, status_code=400)
    async with get_session() as session:
        for rows in csvReader: 
            if (not rows["code"] and not enable_code_generation) or not rows["grade"]:
                return api_response(message="Invalid File: All fields need to be propagated", success=False, status_code=400)
            if not rows["grade"].isdigit() or not 0 < int(rows["grade"]) <= 12:
                return api_response(message="Grade must be an integer and between 0 to 12")
            else:
                grade = int(rows["grade"])
            if rows["gender"] and rows["gender"].upper() not in ["TRUE","FALSE","0","1"]:
                return api_response(message="Gender must be a bool (1 or 0)", success=False, status_code=400)
            else:
                gender = rows["gender"].upper() in ["TRUE","1"] if rows["gender"] else None
            code = rows["code"]
            if not (enable_code_generation and not rows["code"]) and len(code) < 4:
                return api_response(message="Due to security a code less than 4 characters is extremely insecure", success=False, status_code=400)
            result = await session.execute(
                    select(VoteCodes.id).where(VoteCodes.code == code)
                )
            exists = result.first() is not None or not code
            if exists and not enable_code_generation:
                return api_response(message=f"Code '{code}' you provided is already present. Please only use new codes", success=False, status_code=400)
            if exists:
                for i in range(30) if exists else None: 
                    code = ''.join(random.SystemRandom().choice(string.ascii_letters + string.digits) for _ in range(8))
                    result = await session.execute(
                        select(VoteCodes.id).where(VoteCodes.code == code)
                    )
                    exists = result.first() is not None
                    if not exists:
                        break
                    if i == 29:
                        return api_response(message="Couldn't find a viable code in 30 tries. This is anything but normal.", success=False, status_code=500)
            disabled = rows["disabled"].upper() in ["TRUE","1"] if rows["disabled"] else False
            vote_code = VoteCodes(code=code, gender=gender, grade=grade, disabled=disabled)
            session.add(vote_code)
        try:
            await session.commit()
        except Exception as e:
            await session.rollback()
            log.error("FATAL: Could not commit to database. Error:", e)
            return api_response(message="Failed to commit to database", success=False, status_code=400)
    uploaded_file.file.close()
    log.info(f"Admin {request.client.host} imported votecodes")
    return api_response(message="Successfully uploaded votecodes.")

# for teacher upload: "apples,bananas,pears"
# needed fields: name, gender, subjects, description

@router.post("/admin/upload/teachers")
async def upload_teachers(token: str, request: Request, uploaded_file: UploadFile, allow_empty_subjects: bool = False, ignore_duplicates: bool = False):
    """
    Docstring for upload_teachers
    
    :param token: Admin token
    :type token: str
    :param request: automatic
    :type request: Request
    :param uploaded_file: Upload file, should have: name, gender, subjects (as "maths,comp sci,pe"), disabled
    :type uploaded_file: UploadFile
    :param allow_empty_subjects: False by default
    :type allow_empty_subjects: bool
    :param ignore_duplicates: False by default
    :type ignore_duplicates: bool
    """
    auth = await authorize_admin(token, request)
    if auth is not True:
        return auth
    if not uploaded_file.filename.endswith(".csv"):
        return api_response(message="Invalid file type", success=False, status_code=400)
    csvReader = csv.DictReader(codecs.iterdecode(uploaded_file.file, 'utf-8'))
    required_fields = {'name', 'gender', 'subjects', 'disabled'}
    available_fields = set(csvReader.fieldnames or [])
    missing_fields = required_fields - available_fields
    if missing_fields:
        return api_response(message=f"Missing required columns: {', '.join(missing_fields)}", success=False, status_code=400)
    async with get_session() as session:
        for rows in csvReader:
            if not rows["name"] or not rows["gender"]:
                return api_response(message="Invalid File: All fields need to be propagated", success=False, status_code=400)
            if rows["gender"] and rows["gender"].upper() not in ["TRUE","FALSE","0","1"]:
                return api_response(message="Gender must be a bool (1 or 0)", success=False, status_code=400)
            else:
                gender = rows["gender"].upper() in ["TRUE","1"] if rows["gender"] else None
            if len(rows["name"]) < 4:
                return api_response(message="The name needs to be longer than 4 characters", success=False, status_code=400)
            else:
                name = rows["name"]
            try:
                subjects_str = rows["subjects"].strip('"') if rows["subjects"] else ""
                subjects = [s.strip() for s in subjects_str.split(",") if s.strip()]
                if not subjects and not allow_empty_subjects:
                    return api_response(message="Empty subjects field", success=False, status_code=400)
            except (AttributeError, ValueError) as e:
                return api_response(
                    message=f"Invalid subjects format", uccess=False, status_code=400)
            result = await session.execute(
                    select(Teachers.name).where(Teachers.name == name)
                )
            exists = result.first() is not None
            if exists and not ignore_duplicates:
                return api_response(message=f"Teacher with this name already exists: {name}", success=False, status_code=400)
            disabled = rows["disabled"].upper() in ["TRUE","1"] if rows["disabled"] else False
            teacher = Teachers(name=name, gender=gender, subjects=subjects, disabled=disabled)
            session.add(teacher)
        try:
            await session.commit()
        except Exception as e:
            log.error(f"FATAL: Could not commit to databse: {e}")
            await session.rollback()
            return api_response(message="Could not commit to database", success=False, status_code=500)
    uploaded_file.close()
    log.info(f"Admin {request.client.host} imported teachers")
    return api_response(message="Successfully uploaded teachers!")
            