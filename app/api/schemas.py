"""
Pydantic schemas for API request/response validation and documentation.
These models provide type hints, validation, and examples for FastAPI's auto-generated docs.
"""

# this was originally ai generated but has been heavily modified

from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict

# inputs

class VoteSubmissionItem(BaseModel):
    """Individual vote submission for a teacher. All fields optional for dynamic handling."""
    overall: int = Field(None, ge=1, le=10, description="Overall rating (1-10)")
    understandability: Optional[int] = Field(None, ge=1, le=10, description="understandability rating (1-10)")
    helpfulness: Optional[int] = Field(None, ge=1, le=10, description="helpfulness rating (1-10)")
    fairness: Optional[int] = Field(None, ge=1, le=10, description="fairness rating (1-10)")
    clarity: Optional[int] = Field(None, ge=1, le=10, description="clarity rating (1-10)")
    homework_amount: Optional[int] = Field(None, ge=1, le=10, description="homework_amount rating (1-10)")
    exam_difficulty: Optional[int] = Field(None, ge=1, le=10, description="exam_difficulty rating (1-10)")
    humor: Optional[int] = Field(None, ge=1, le=10, description="humor rating (1-10)")
    character: Optional[int] = Field(None, ge=1, le=10, description="character rating (1-10)")
    style: Optional[int] = Field(None, ge=1, le=10, description="style rating (1-10)")

    class Config:
        json_schema_extra = {
            "example": {
                "overall": 5,
                "understandability": 6,
                "helpfulness": 7,
                "fairness": 8,
                "clarity": 5,
                "homework_amount": 4,
                "exam_difficulty": 6,
                "humor": 7,
                "character": 8,
                "style": 5
            }
        }

class VoteCodeRequest(BaseModel):
    """Request body for vote verification."""
    vote_code: str = Field(..., min_length=1, description="The unique vote code provided to the student")


# ============================================================================
# VOTING ENDPOINTS SCHEMAS
# ============================================================================

class ChallengeResponse(BaseModel):
    """Challenge token response after successful vote code verification."""
    challenge: str = Field(..., description="32-character challenge token for solving")

    class Config:
        json_schema_extra = {
            "example": {
                "challenge": "example12345value67890challenge1"
            }
        }


class VoteVerifyResponse(BaseModel):
    """Response from vote verification endpoint."""
    success: bool = Field(..., description="Whether verification was successful")
    message: str = Field(..., description="Status message")
    data: Optional[ChallengeResponse] = Field(None, description="Challenge data if successful")


class TeacherInfo(BaseModel):
    """Teacher information returned in voting endpoints."""
    name: str
    gender: Optional[bool] = None
    subjects: List[str]
    description: Optional[str] = None

    class Config:
        json_schema_extra = {
            "1": {
                "name": "John Smith",
                "gender": True,
                "subjects": ["Mathematics", "Physics"],
                "description": "Experienced math teacher"
            }
        }


class TeachersListResponse(BaseModel):
    """Response with mapping of teacher_id -> TeacherInfo."""
    success: bool
    message: Optional[str] = None
    data: Optional[Dict[str, TeacherInfo]] = None
    status_code: Optional[int] = None


class VoteSubmitResponse(BaseModel):
    """Response from vote submission endpoint."""
    success: bool = Field(..., description="Whether submission was successful")
    message: str = Field(..., description="Status message")
    data: None

class VoteAverages(BaseModel):
    """Vote averages for a teacher across all voting criteria."""
    overall: Optional[float] = Field(None, description="Average overall rating (1-10)", ge=1, le=10)
    understandability: Optional[float] = Field(None, description="Average understandability rating (1-10)", ge=1, le=10)
    helpfulness: Optional[float] = Field(None, description="Average helpfulness rating (1-10)", ge=1, le=10)
    fairness: Optional[float] = Field(None, description="Average fairness rating (1-10)", ge=1, le=10)
    clarity: Optional[float] = Field(None, description="Average clarity rating (1-10)", ge=1, le=10)
    homework_amount: Optional[float] = Field(None, description="Average homework_amount rating (1-10)", ge=1, le=10)
    exam_difficulty: Optional[float] = Field(None, description="Average exam_difficulty rating (1-10)", ge=1, le=10)
    humor: Optional[float] = Field(None, description="Average humor rating (1-10)", ge=1, le=10)
    character: Optional[float] = Field(None, description="Average character rating (1-10)", ge=1, le=10)
    style: Optional[float] = Field(None, description="Average style rating (1-10)", ge=1, le=10)

    class Config:
        json_schema_extra = {
            "example": {
                "overall": 7.5,
                "understandability": 8.0,
                "helpfulness": 7.2,
                "fairness": 8.5,
                "clarity": 7.8,
                "homework_amount": 6.5,
                "exam_difficulty": 7.0,
                "humor": 8.2,
                "character": 8.0,
                "style": 7.5
            }
        }


class VotecountResponse(BaseModel):
    """Response containing vote averages for a teacher."""
    success: bool = Field(..., description="Whether operation was successful")
    message: Optional[str] = Field(None, description="Status message")
    data: Optional[VoteAverages] = Field(None, description="Vote averages across all criteria")
    status_code: Optional[int] = Field(None, description="HTTP status code")


# ============================================================================
# ADMIN TEACHER MANAGEMENT SCHEMAS
# ============================================================================

class AdminResponse(BaseModel):
    """Generic admin operation response."""
    success: bool = Field(..., description="Whether operation was successful")
    message: Optional[str] = Field(None, description="Status message")
    data: Optional[Any] = Field(None, description="Additional data if applicable")
