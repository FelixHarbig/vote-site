"""
GDPR Compliance endpoints for German data protection (DSGVO/BDSG).
Provides GDPR compliance including:
- Consent management with version tracking
- Data export (right to access)
- Data deletion (right to be forgotten)
- Audit logging
- Privacy policy

Note: Data rectification requests should be sent via email to the data controller.
See /api/gdpr/privacy-policy for contact information.

You can easily disable this via settings (database)
This should be seen as a possible example and is in no way legally recommended.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from api.auth.jwt_utils import get_current_admin
from api.supabase_auth import get_authenticated_user, get_optional_user
from supabase_client import get_supabase_admin_client, is_supabase_admin_configured
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import json
import os

from api.utils import api_response, hash_ip
from common.log_handler import log
from api.rate_limiter import limiter
from database.models import get_session, VoteCodes, Votes, Settings, VotingEngine
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
import sqlalchemy


# ============================================================================
# DATABASE MODELS FOR GDPR
# ============================================================================

class GDPRConsentRecord(VotingEngine):
    """Tracks user consent for GDPR compliance."""
    __tablename__ = 'gdpr_consent'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False, index=True)
    session_id = Column(String(255), nullable=True, index=True)
    consent_type = Column(String(100), nullable=False)
    granted = Column(Boolean, nullable=False)
    consent_version = Column(String(20), nullable=False, default="1.0")
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    timestamp = Column(DateTime, server_default=sqlalchemy.func.now(), nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        sqlalchemy.Index('idx_gdpr_consent_user_type', 'user_id', 'consent_type'),
    )


class GDPRAuditLog(VotingEngine):
    """Audit log for GDPR compliance tracking."""
    __tablename__ = 'gdpr_audit_log'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=True, index=True)
    action = Column(String(100), nullable=False)
    resource = Column(String(100), nullable=False)
    details = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    timestamp = Column(DateTime, server_default=sqlalchemy.func.now(), nullable=False)
    
    __table_args__ = (
        sqlalchemy.Index('idx_gdpr_audit_user', 'user_id'),
        sqlalchemy.Index('idx_gdpr_audit_timestamp', 'timestamp'),
    )


# ============================================================================
# CONSTANTS AND ENUMS
# ============================================================================

class ConsentType(str, Enum):
    VOTING = "voting"
    AUTHENTICATION = "authentication"


# Simplified consent types - only what's actually used
CONSENT_TYPES = {
    "voting": {
        "name": "Voting Consent",
        "description": "I consent to the processing of my personal data for voting purposes",
        "required": True,
        "retention": "2 years after last activity",
        "gdpr_legal_basis": "consent",
        "article": "Article 6(1)(a) GDPR"
    },
    "authentication": {
        "name": "Authentication",
        "description": "I consent to the use of my email for authentication purposes",
        "required": True,
        "retention": "Until account deletion",
        "gdpr_legal_basis": "consent",
        "article": "Article 6(1)(a) GDPR"
    }
}


# Cache for gdpr_enabled setting (refreshed periodically)
_gdpr_enabled_cache = {"enabled": True, "last_check": 0}
CACHE_TTL_SECONDS = 30  # How long to cache the setting


async def is_gdpr_enabled() -> bool:
    """
    Check if GDPR mode is enabled in settings.
    Uses a cache to avoid hitting the database on every request.
    """
    import time
    from sqlalchemy import select
    
    current_time = time.time()
    
    # Check if cache is valid
    if current_time - _gdpr_enabled_cache["last_check"] < CACHE_TTL_SECONDS:
        return _gdpr_enabled_cache["enabled"]
    
    # Fetch fresh value from database
    try:
        async with get_session() as session:
            result = await session.execute(
                select(Settings).where(Settings.name == "gdpr_enabled")
            )
            setting = result.scalars().first()
            
            if setting is not None:
                _gdpr_enabled_cache["enabled"] = setting.enabled
            else:
                # Default to True if setting doesn't exist
                _gdpr_enabled_cache["enabled"] = True
            
            _gdpr_enabled_cache["last_check"] = current_time
            log.info(f"GDPR enabled: {_gdpr_enabled_cache['enabled']}")
    except Exception as e:
        log.error(f"Error checking gdpr_enabled setting: {e}")
        # Default to True on error to be safe
        _gdpr_enabled_cache["enabled"] = True
    
    return _gdpr_enabled_cache["enabled"]


# ============================================================================
# HELPER FUNCTIONS (exported for use in voting endpoints)
# ============================================================================

async def check_user_consent(user_id: str, consent_type: str = "voting") -> bool:
    """
    Check if a user has granted the specified consent type.
    
    Args:
        user_id: The Supabase user ID or session ID
        consent_type: The type of consent to check (default: "voting")
    
    Returns:
        True if consent is granted, False otherwise
    """
    try:
        async with get_session() as session:
            from sqlalchemy import select
            
            result = await session.execute(
                select(GDPRConsentRecord.granted).where(
                    GDPRConsentRecord.user_id == user_id,
                    GDPRConsentRecord.consent_type == consent_type,
                    GDPRConsentRecord.revoked_at.is_(None)
                )
            )
            record = result.scalars().first()
            return record if record else False
            
    except Exception as e:
        log.error(f"Error checking user consent: {e}")
        return False


async def log_gdpr_audit(
    user_id: Optional[str],
    action: str,
    resource: str,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
):
    """
    Log a GDPR-related action to the audit trail.
    IP addresses are hashed for privacy compliance.
    
    Args:
        user_id: The user ID (can be None for anonymous actions)
        action: The action performed (e.g., "consent_updated", "vote_submitted")
        resource: The resource affected (e.g., "data_processing", "votes")
        details: Additional details about the action
        ip_address: The IP address of the request (will be hashed)
        user_agent: The user agent string
    """
    # Hash IP for GDPR compliance
    ip_hash = None
    if ip_address:
        import hashlib
        ip_hash = hashlib.sha256(ip_address.encode()).hexdigest()[:16]
    
    try:
        async with get_session() as session:
            audit_log = GDPRAuditLog(
                user_id=user_id,
                action=action,
                resource=resource,
                details=details,
                ip_address=ip_hash,  # Store hashed IP only
                user_agent=user_agent[:500] if user_agent else None  # Truncate user agent
            )
            session.add(audit_log)
            await session.commit()
    except Exception as e:
        log.error(f"Error logging GDPR audit action: {e}")


# ============================================================================
# Pydantic Models
# ============================================================================

class ConsentUpdate(BaseModel):
    consent_type: str
    granted: bool
    session_id: Optional[str] = None
    version: str = "1.0"


class ConsentBulkUpdate(BaseModel):
    consents: Dict[str, bool]
    session_id: Optional[str] = None
    version: str = "1.0"


class ConsentTransferRequest(BaseModel):
    """Request to transfer consent from session to user account."""
    session_id: str
    user_id: str


# ============================================================================
# ROUTER SETUP
# ============================================================================

router = APIRouter(
    prefix="/gdpr",
    tags=["gdpr"],
)


# ============================================================================
# CONSENT TRANSFER (for signup flow)
# ============================================================================

@router.post("/consent/transfer")
@limiter.limit("200/minute")
async def transfer_consent_to_user(
    request: Request,
    transfer: ConsentTransferRequest,
    current_user: Dict[str, Any] = Depends(get_authenticated_user)
):
    """
    Transfer consent from anonymous session to authenticated user account.
    
    This is called when an anonymous user signs up - their consent records
    (associated with session_id) are copied to their user account.
    
    SECURITY: Requires authentication. User can only transfer consent to their own account.
    
    GDPR Art. 7(3): Right to withdraw consent - this transfer preserves
    the user's consent choice while associating it with their account.
    """
    # Check if GDPR is enabled
    if not await is_gdpr_enabled():
        return api_response(
            message="GDPR is not enabled",
            success=False,
            status_code=503
        )
    
    # Require authentication - user must be logged in to transfer consent
    # The user can only transfer consent to their own account
    if current_user.get("user_id") != transfer.user_id:
        return api_response(
            message="User ID mismatch - cannot transfer consent to another account",
            success=False,
            status_code=403
        )
    
    # Validate session_id is provided for anonymous consent transfer
    if not transfer.session_id:
        return api_response(
            message="Session ID is required to transfer consent",
            success=False,
            status_code=400
        )
    
    transferred = []
    already_existed = []
    errors = []
    
    try:
        async with get_session() as session:
            from sqlalchemy import select, update, insert
            from database.models import VoteCodes
            
            # Get all consent records for the session_id
            result = await session.execute(
                select(GDPRConsentRecord).where(
                    GDPRConsentRecord.user_id == transfer.session_id,
                    GDPRConsentRecord.revoked_at.is_(None)
                )
            )
            old_consents = result.scalars().all()
            
            if not old_consents:
                return api_response(
                    message="No consent records found to transfer",
                    data={
                        "transferred": [],
                        "already_existed": [],
                        "session_id": transfer.session_id,
                        "user_id": transfer.user_id
                    }
                )
            
            # Use no_autoflush to prevent premature flush errors
            with session.no_autoflush:
                for old_consent in old_consents:
                    consent_type = old_consent.consent_type
                    
                    # Check if user already has this consent type
                    check_result = await session.execute(
                        select(GDPRConsentRecord.id).where(
                            GDPRConsentRecord.user_id == transfer.user_id,
                            GDPRConsentRecord.consent_type == consent_type,
                            GDPRConsentRecord.revoked_at.is_(None)
                        )
                    )
                    existing = check_result.scalars().first()
                    
                    if existing:
                        already_existed.append({
                            "consent_type": consent_type,
                            "existing_id": existing
                        })
                        # Still mark old consent as revoked
                        await session.execute(
                            update(GDPRConsentRecord).where(
                                GDPRConsentRecord.id == old_consent.id
                            ).values(
                                revoked_at=datetime.utcnow()
                            )
                        )
                        continue
                    
                    # Create new consent record for the user
                    new_consent = GDPRConsentRecord(
                        user_id=transfer.user_id,
                        session_id=transfer.session_id,
                        consent_type=consent_type,
                        granted=old_consent.granted,
                        consent_version=old_consent.consent_version,
                        ip_address=hash_ip(request.client.host),
                        user_agent=request.headers.get("user-agent", "")[:500],
                        timestamp=datetime.utcnow()
                    )
                    try:
                        session.add(new_consent)
                        transferred.append(consent_type)
                    except Exception as insert_error:
                        # Handle unique constraint violation
                        log.warning(f"Consent already exists for user {transfer.user_id}, type {consent_type}")
                        already_existed.append({
                            "consent_type": consent_type,
                            "reason": "already_exists"
                        })
                        # Still mark old consent as revoked
                        await session.execute(
                            update(GDPRConsentRecord).where(
                                GDPRConsentRecord.id == old_consent.id
                            ).values(
                                revoked_at=datetime.utcnow()
                            )
                        )
                        continue
                
                # Mark old session consents as transferred
                for old_consent in old_consents:
                    await session.execute(
                        update(GDPRConsentRecord).where(
                            GDPRConsentRecord.id == old_consent.id
                        ).values(
                            revoked_at=datetime.utcnow()
                        )
                    )
            
            await session.commit()
            
    except Exception as e:
        log.error(f"Error transferring consent: {e}")
        return api_response(
            message="Failed to transfer consent",
            success=False,
            status_code=500,
            data={"error": str(e)}
        )
    
    # Log the transfer in audit trail
    await log_gdpr_audit(
        user_id=transfer.user_id,
        action="consent_transferred",
        resource="gdpr_consent",
        details={
            "session_id": transfer.session_id,
            "transferred_consents": transferred,
            "already_existed": already_existed,
            "errors": errors
        },
        ip_address=request.client.host,
        user_agent=request.headers.get("user-agent", "")[:500]
    )
    
    return api_response(
        message="Consent transferred successfully",
        data={
            "transferred": transferred,
            "already_existed": already_existed,
            "session_id": transfer.session_id,
            "user_id": transfer.user_id
        }
    )



@router.get("/status")
@limiter.limit("200/minute")
async def get_gdpr_status(
    request: Request,
    session_id: Optional[str] = None,
    user: Optional[Dict[str, Any]] = Depends(get_optional_user)
):
    """
    Check if GDPR mode is enabled and whether the user has consented.
    Frontend should show consent dialog when this returns enabled=True and has_consented=False.
    """
    try:
        async with get_session() as session:
            from sqlalchemy import select
            from database.models import Settings
            
            result = await session.execute(
                select(Settings).where(Settings.name == "gdpr_enabled")
            )
            setting = result.scalars().first()
            
            gdpr_enabled = setting.enabled if setting else True  # Default to True
            
            # Check actual user consent status
            has_consented = False
            
            # Determine identifier from token (secure) or session (anonymous)
            identifier = user["user_id"] if user else session_id
            
            if identifier and gdpr_enabled:
                all_consented = True
                for consent_type in CONSENT_TYPES:
                    consent_result = await session.execute(
                        select(GDPRConsentRecord.granted).where(
                            GDPRConsentRecord.user_id == identifier,
                            GDPRConsentRecord.consent_type == consent_type,
                            GDPRConsentRecord.revoked_at.is_(None)
                        )
                    )
                    record = consent_result.scalars().first()
                    if not record:
                        all_consented = False
                        break
                has_consented = all_consented
             
            return api_response(
                message="GDPR status",
                data={
                    "enabled": gdpr_enabled,
                    "consent_required": gdpr_enabled,
                    "has_consented": has_consented
                }
            )
    except Exception as e:
        log.error(f"Error getting GDPR status: {e}")
        return api_response(
            message="Error getting GDPR status",
            success=False,
            status_code=500
        )


# ============================================================================
# CONSENT MANAGEMENT
# ============================================================================

@router.post("/consent")
@limiter.limit("200/minute")
async def update_consent(
    request: Request,
    consent: ConsentUpdate,
    session_id: Optional[str] = None,
    user: Optional[Dict[str, Any]] = Depends(get_optional_user)
):
    """
    Update user consent for data processing.
    GDPR requires explicit consent (Art. 7).
    """
    # Check if GDPR is enabled
    if not await is_gdpr_enabled():
        return api_response(
            message="GDPR is not enabled",
            success=False,
            status_code=503
        )
    
    if consent.consent_type not in CONSENT_TYPES:
        return api_response(
            message=f"Invalid consent type. Valid types: {list(CONSENT_TYPES.keys())}",
            success=False,
            status_code=400
        )
    
    consent_info = CONSENT_TYPES.get(consent.consent_type, {})
    if consent_info.get("required", False) and not consent.granted:
        return api_response(
            message=f"{consent.consent_type} consent cannot be revoked",
            success=False,
            status_code=400
        )
    
    # Prefer session_id from body if available
    effective_session_id = consent.session_id if consent.session_id else session_id
    
    # Determine identifier from token (secure) or session (anonymous)
    identifier = user["user_id"] if user else effective_session_id
    
    if not identifier:
        return api_response(
            message="Session ID or User ID required",
            success=False,
            status_code=403
        )
    
    try:
        async with get_session() as session:
            from sqlalchemy import select, update
            
            result = await session.execute(
                select(GDPRConsentRecord.id).where(
                    GDPRConsentRecord.user_id == identifier,
                    GDPRConsentRecord.consent_type == consent.consent_type,
                    GDPRConsentRecord.revoked_at.is_(None)
                )
            )
            existing = result.scalars().first()
            
            if existing:
                await session.execute(
                    update(GDPRConsentRecord).where(
                        GDPRConsentRecord.id == existing
                    ).values(
                        granted=consent.granted,
                        revoked_at=None if consent.granted else datetime.utcnow()
                    )
                )
            else:
                new_consent = GDPRConsentRecord(
                    user_id=identifier,
                    session_id=session_id,
                    consent_type=consent.consent_type,
                    granted=consent.granted,
                    consent_version=consent.version,
                    ip_address=hash_ip(request.client.host),
                    user_agent=request.headers.get("user-agent", "")[:500]
                )
                session.add(new_consent)
            
            await session.commit()
            
    except Exception as e:
        log.error(f"Error updating consent: {e}")
        return api_response(
            message="Failed to update consent",
            success=False,
            status_code=500
        )
    
    await log_gdpr_audit(
        user_id=identifier,
        action="consent_updated",
        resource=consent.consent_type,
        details={"granted": consent.granted, "version": consent.version},
        ip_address=request.client.host
    )
    
    return api_response(
        message="Consent updated successfully",
        data={
            "consent_type": consent.consent_type,
            "granted": consent.granted,
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@router.post("/consent/bulk")
@limiter.limit("200/minute")
async def update_consents_bulk(
    request: Request,
    bulk: ConsentBulkUpdate,
    session_id: Optional[str] = None,
    user: Optional[Dict[str, Any]] = Depends(get_optional_user)
):
    """
    Update multiple consent settings at once.
    """
    # Check if GDPR is enabled
    if not await is_gdpr_enabled():
        return api_response(
            message="GDPR is not enabled",
            success=False,
            status_code=503
        )
    
    results = {}
    
    # Prefer session_id from body if available
    effective_session_id = bulk.session_id if bulk.session_id else session_id
    
    # Determine identifier
    identifier = user["user_id"] if user else effective_session_id
    
    if not identifier:
        return api_response(
            message="Session ID or User ID required",
            success=False,
            status_code=403
        )
    
    for consent_type, granted in bulk.consents.items():
        if consent_type not in CONSENT_TYPES:
            results[consent_type] = {"success": False, "error": "Invalid consent type"}
            continue
        
        consent_info = CONSENT_TYPES.get(consent_type, {})
        if consent_info.get("required", False) and not granted:
            results[consent_type] = {"success": False, "error": f"{consent_type} consent cannot be revoked"}
            continue
        
        try:
            async with get_session() as session:
                from sqlalchemy import select, update
                
                result = await session.execute(
                    select(GDPRConsentRecord.id).where(
                        GDPRConsentRecord.user_id == identifier,
                        GDPRConsentRecord.consent_type == consent_type,
                        GDPRConsentRecord.revoked_at.is_(None)
                    )
                )
                existing = result.scalars().first()
                
                if existing:
                    await session.execute(
                        update(GDPRConsentRecord).where(
                            GDPRConsentRecord.id == existing
                        ).values(
                            granted=granted,
                            revoked_at=None if granted else datetime.utcnow()
                        )
                    )
                else:
                    new_consent = GDPRConsentRecord(
                        user_id=identifier,
                        session_id=session_id,
                        consent_type=consent_type,
                        granted=granted,
                        consent_version=bulk.version,
                        ip_address=hash_ip(request.client.host),
                        user_agent=request.headers.get("user-agent", "")[:500]
                    )
                    session.add(new_consent)
                
                await session.commit()
                results[consent_type] = {"success": True, "granted": granted}
                
        except Exception as e:
            log.error(f"Error updating consent {consent_type}: {e}")
            results[consent_type] = {"success": False, "error": str(e)}
    
    return api_response(
        message="Consents updated",
        data={
            "results": results,
            "user_id": identifier
        }
    )


@router.get("/consent")
@limiter.limit("60/minute")
async def get_consent_settings(
    request: Request,
    session_id: Optional[str] = None,
    user: Optional[Dict[str, Any]] = Depends(get_optional_user)
):
    """
    Get current consent settings for a user.
    """
    consents = {}
    
    # Determine identifier
    identifier = user["user_id"] if user else session_id
    if not identifier:
        identifier = "anonymous"
    
    try:
        async with get_session() as session:
            from sqlalchemy import select
            
            result = await session.execute(
                select(GDPRConsentRecord).where(
                    GDPRConsentRecord.user_id == identifier,
                    GDPRConsentRecord.revoked_at.is_(None)
                )
            )
            records = result.scalars().all()
            
            for record in records:
                consents[record.consent_type] = {
                    "granted": record.granted,
                    "timestamp": record.timestamp.isoformat(),
                    "version": record.consent_version
                }
                
    except Exception as e:
        log.error(f"Error getting consent: {e}")
    
    return api_response(
        message="Consent settings retrieved",
        data={
            "consents": consents,
            "available_types": CONSENT_TYPES,
            "user_id": identifier
        }
    )


@router.get("/consent/status/{consent_type}")
@limiter.limit("60/minute")
async def check_consent_status(
    request: Request,
    consent_type: str,
    session_id: Optional[str] = None,
    user: Optional[Dict[str, Any]] = Depends(get_optional_user)
):
    """
    Quick check if user has granted specific consent.
    """
    if consent_type not in CONSENT_TYPES:
        return api_response(
            message="Invalid consent type",
            success=False,
            status_code=400
        )
    
    consent_info = CONSENT_TYPES.get(consent_type, {})
    is_required = consent_info.get("required", False)
    
    # Determine identifier
    identifier = user["user_id"] if user else session_id
    if not identifier:
        identifier = "anonymous"
    
    granted = False
    try:
        async with get_session() as session:
            from sqlalchemy import select
            
            result = await session.execute(
                select(GDPRConsentRecord.granted).where(
                    GDPRConsentRecord.user_id == identifier,
                    GDPRConsentRecord.consent_type == consent_type,
                    GDPRConsentRecord.revoked_at.is_(None)
                )
            )
            record = result.scalars().first()
            granted = record if record else False
            
    except Exception as e:
        log.error(f"Error checking consent: {e}")
    
    return api_response(
        message="Consent status",
        data={
            "consent_type": consent_type,
            "granted": granted,
            "required": is_required,
            "explanation": consent_info.get("description", "")
        }
    )


# ============================================================================
# DATA EXPORT (RIGHT TO ACCESS)
# ============================================================================

@router.get("/export")
@limiter.limit("5/minute")
async def export_user_data(
    request: Request,
    user: Dict[str, Any] = Depends(get_authenticated_user)
):
    """
    Export all user data (GDPR Article 15 - Right of Access).
    Authenticated user can only export their own data.
    """
    # Check if GDPR is enabled
    if not await is_gdpr_enabled():
        return api_response(
            message="GDPR is not enabled",
            success=False,
            status_code=503
        )
    
    user_id = user["user_id"]


    export_data = {
        "export_metadata": {
            "export_date": datetime.utcnow().isoformat(),
            "data_controller": await get_data_controller_info(),
            "user_id": user_id,
            "format_version": "1.0"
        },
        "data_categories": {}
    }
    
    try:
        async with get_session() as session:
            from sqlalchemy import select
            
            export_data["data_categories"]["account"] = {
                "user_id": user_id,
                "note": "Account data is managed by Supabase Auth"
            }
            
            result = await session.execute(
                select(VoteCodes).where(VoteCodes.code.like(f"USER_{user_id[:8]}%"))
            )
            votecodes = result.scalars().all()
            export_data["data_categories"]["votecodes"] = [
                {
                    "code": vc.code,
                    "used": vc.used,
                    "grade": vc.grade,
                    "created_at": vc.created_at.isoformat() if vc.created_at else None
                }
                for vc in votecodes
            ]
            
            result = await session.execute(
                select(Votes).where(Votes.user_id == user_id)
            )
            votes = result.scalars().all()
            export_data["data_categories"]["votes"] = [
                {
                    "id": v.id,
                    "teacher_id": v.teacher_id,
                    "overall": v.overall,
                    "timestamp": v.timestamp.isoformat() if v.timestamp else None
                }
                for v in votes
            ]
            
            result = await session.execute(
                select(GDPRConsentRecord).where(GDPRConsentRecord.user_id == user_id)
            )
            consents = result.scalars().all()
            export_data["data_categories"]["consent"] = [
                {
                    "type": c.consent_type,
                    "granted": c.granted,
                    "timestamp": c.timestamp.isoformat(),
                    "version": c.consent_version
                }
                for c in consents
            ]
            
            result = await session.execute(
                select(GDPRAuditLog).where(GDPRAuditLog.user_id == user_id)
            )
            audit_logs = result.scalars().all()
            export_data["data_categories"]["activity_log"] = [
                {
                    "action": log.action,
                    "resource": log.resource,
                    "timestamp": log.timestamp.isoformat()
                }
                for log in audit_logs[-100:]
            ]
            
    except Exception as e:
        log.error(f"Error exporting user data: {e}")
        return api_response(
            message="Failed to export data",
            success=False,
            status_code=500
        )
    
    await log_gdpr_audit(
        user_id=user_id,
        action="data_exported",
        resource="all",
        details={"categories": list(export_data["data_categories"].keys())},
        ip_address=request.client.host
    )
    
    return api_response(
        message="Data export ready",
        data=export_data
    )


# ============================================================================
# DATA DELETION (RIGHT TO BE FORGOTTEN)
# ============================================================================

@router.delete("/delete")
@limiter.limit("5/minute")
async def delete_user_data(
    request: Request,
    user: Dict[str, Any] = Depends(get_authenticated_user)
):
    """
    Delete all user data (GDPR Article 17 - Right to Erasure).
    Authenticated user can only delete their own data.
    """
    # Check if GDPR is enabled
    if not await is_gdpr_enabled():
        return api_response(
            message="GDPR is not enabled",
            success=False,
            status_code=503
        )
    
    user_id = user["user_id"]


    deletion_summary = {
        "user_id": user_id,
        "deleted_at": datetime.utcnow().isoformat(),
        "deletions": {}
    }
    
    try:
        async with get_session() as session:
            from sqlalchemy import delete, update
            
            result = await session.execute(
                delete(VoteCodes).where(VoteCodes.code.like(f"USER_{user_id[:8]}%"))
            )
            deletion_summary["deletions"]["votecodes"] = result.rowcount
            
            await session.execute(
                update(Votes).where(Votes.user_id == user_id).values(
                    user_id=None,
                    ip_hash=None
                )
            )
            deletion_summary["deletions"]["votes_anonymized"] = "votes retained for statistics"
            
            await session.execute(
                update(GDPRConsentRecord).where(
                    GDPRConsentRecord.user_id == user_id
                ).values(
                    revoked_at=datetime.utcnow()
                )
            )
            deletion_summary["deletions"]["consent_revoked"] = True
            
            # Delete Supabase account if configured
            supabase_account_deleted = False
            if is_supabase_admin_configured():
                try:
                    supabase = get_supabase_admin_client()
                    if supabase:
                        # Delete user from Supabase Auth
                        supabase.auth.admin.delete_user(user_id)
                        supabase_account_deleted = True
                        log.info(f"Deleted Supabase account for user {user_id}")
                except Exception as e:
                    log.error(f"Error deleting Supabase account: {e}")
                    # Continue with deletion even if Supabase deletion fails
            deletion_summary["deletions"]["supabase_account_deleted"] = supabase_account_deleted
            
            await session.commit()
            
    except Exception as e:
        log.error(f"Error deleting user data: {e}")
        return api_response(
            message="Failed to delete data",
            success=False,
            status_code=500
        )
    
    await log_gdpr_audit(
        user_id=user_id,
        action="data_deleted",
        resource="all",
        details=deletion_summary,
        ip_address=request.client.host
    )
    
    return api_response(
        message="Your data has been deleted. Your Supabase account has also been removed. Anonymized vote data may be retained for statistics.",
        data=deletion_summary
    )


# ============================================================================
# DATA RECTIFICATION REQUEST (RIGHT TO RECTIFICATION)
# ============================================================================

# Note: Rectification requests should be sent via email to the data controller.
# See privacy policy for contact information.

# Note: Cookie consent banner is not needed for this service.
# No tracking, analytics, or marketing cookies are used.

# ============================================================================
# PRIVACY POLICY
# ============================================================================

@router.get("/privacy-policy")
@limiter.limit("60/minute")
async def get_privacy_policy(request: Request):
    """
    Get the privacy policy document (German DSGVO compliant).
    Designed for single-person non-commercial hosting.
    """
    controller_info = await get_data_controller_info()
    
    policy = {
        "version": "3.1",
        "effective_date": "2026-04-24",
        "last_updated": datetime(2026, 4, 24).isoformat(), # Edit this to the actual date you modify it
        "language": "de",
        "controller": {
            # The following is set from the function above, which is fetched from the .env file
            "name": controller_info.get("name", "VoteStation"),
            "address": controller_info.get("address", "[Ihre Adresse]"),
            "email": controller_info.get("email", "[Ihre E-Mail]") 
        },
        "sections": {
            "1_introduction": {
                "title": "1. Einleitung",
                "content": (
                    "Dieses Voting-System wird als privates, nicht kommerzielles Projekt betrieben. "
                    "Der Schutz Ihrer personenbezogenen Daten ist uns wichtig. "
                    "Die Verarbeitung erfolgt gemäß der Datenschutz-Grundverordnung (DSGVO) "
                    "sowie den geltenden nationalen Datenschutzgesetzen."
                )
            },
            "2_data_controller": {
                "title": "2. Verantwortlicher",
                "content": f"{controller_info.get('name', 'VoteStation')}\n{controller_info.get('address', 'Error while fetching adress')}"
            },
            "3_data_collected": {
                "title": "3. Verarbeitete Daten",
                "content": "Kontoinformationen: E-Mail-Adresse und interne Benutzer-ID von Supabase Auth (Frankfurt, Deutschland)\n"
                          "Vote-Codes: Eindeutige Codes für Abstimmungen\n"
                          "Abstimmungsdaten: Ihre Bewertungen für Lehrkräfte\n"
                          "Technische Daten: Pseudonymisierte IP-Adresse, Browsertyp, Zeitstempel von Anfragen"
            },
            "4_purpose": {
                "title": "4. Zweck der Verarbeitung",
                "content": "Wir verarbeiten Ihre Daten ausschließlich zur Bereitstellung des Voting-Systems und zum Schutz vor Missbrauch. Es erfolgt keine kommerzielle Nutzung."
            },
            "5_legal_basis": {
                "title": "5. Rechtsgrundlage",
                "content": (
                    "Art. 6 Abs. 1 lit. b DSGVO - Vertragserfüllung (Bereitstellung des Dienstes)\n"
                    "Art. 6 Abs. 1 lit. f DSGVO - Berechtigtes Interesse an IT-Sicherheit "
                    "und Missbrauchsvermeidung\n\n"
                    "Das berechtigte Interesse liegt in der Sicherstellung der Integrität "
                    "und Funktionsfähigkeit des Systems."
                )
            },
            "6_retention": {
                "title": "6. Speicherdauer",
                "content": "Account-Daten: Bis zur Kontolöschung (Supabase)\n"
                           "Vote-Codes: 2 Jahre nach Verwendung\n"
                           "Abstimmungsdaten: 1 Jahr (danach anonymisiert)\n"
                           "IP-Hashes: 48 Stunden für Missbrauchsschutz"
            },
            "7_sharing": {
                "title": "7. Datenweitergabe",
                "content": (
                    "Eine Weitergabe personenbezogener Daten an Dritte zu kommerziellen Zwecken erfolgt nicht. "
                    "Zur technischen Bereitstellung des Dienstes setzen wir jedoch Auftragsverarbeiter "
                    "gemäß Art. 28 DSGVO ein."
                )
            },
            "8_third_party": {
                "title": "8. Auftragsverarbeiter (Drittanbieter)", # This is an example
                "content":  "Unesty:\n"
                            "- Rolle: Hosting des VPS (Backend-Server)\n"
                            "- Standort: Deutschland\n"
                            "- Zweck: Serverbetrieb und technische Infrastruktur\n\n"
                            "Supabase Inc.:\n"
                            "- Rolle: Authentifizierung und Datenbank\n"
                            "- Serverstandort: Frankfurt am Main, Deutschland\n\n"
                            "Cloudflare:\n"
                            "- Rolle: DNS Routing\n"
                            "- Sitz: USA\n\n"
                            "Google LLC (nur bei externer Einbindung von Web-Schriften):\n"
                            "- Zweck: Bereitstellung von Web-Schriften\n"
                            "- Sitz: USA\n"
                            "- Hinweis: Dabei kann die IP-Adresse an Google übermittelt werden."
                
            },
            "9_cookies": {
                "title": "9. Cookies",
                "content": "Es werden keine Tracking-, Analytics- oder Marketing-Cookies verwendet. Nur technisch notwendige Cookies für den Betrieb des Voting-Systems."
            },
            "10_your_rights": {
                "title": "10. Ihre Rechte",
                "content": "Auskunft (Art. 15 DSGVO) - Sie haben das Recht, Auskunft über Ihre bei uns gespeicherten personenbezogenen Daten zu erhalten.\n\n"
                           "Berichtigung (Art. 16 DSGVO) - Sie können die Berichtigung unrichtiger Daten verlangen.\n\n"
                           "Löschung (Art. 17 DSGVO) - Sie können die Löschung Ihrer Daten verlangen, sofern keine gesetzlichen Aufbewahrungspflichten bestehen.\n\n"
                           "Einschränkung (Art. 18 DSGVO) - Sie können die Einschränkung der Verarbeitung verlangen.\n\n"
                           "Datenübertragbarkeit (Art. 20 DSGVO) - Sie können Ihre Daten in einem strukturierten, gängigen und maschinenlesbaren Format erhalten.\n\n"
                           "Widerspruch (Art. 21 DSGVO) - Sie können der Verarbeitung Ihrer Daten widersprechen.\n\n"
                           "Beschwerde bei Aufsichtsbehörde (Art. 77 DSGVO) - Sie haben das Recht, Beschwerde bei einer Datenschutzaufsichtsbehörde einzureichen."
            },
            "11_contact": {
                "title": "11. Kontakt",
                "content": "Fragen zum Datenschutz: " + controller_info.get('email', '[Ihre E-Mail]')
            }
        }
    }
    
    return api_response(
        message="Privacy policy retrieved",
        data=policy
    )


@router.get("/data_categories")
@limiter.limit("60/minute")
async def get_data_categories(request: Request):
    """
    Get list of data categories collected by this service.
    """
    categories = []
    
    for cat_id, info in CONSENT_TYPES.items():
        categories.append({
            "id": cat_id,
            "name": info.get("name", cat_id),
            "description": info.get("description", ""),
            "required": info.get("required", False),
            "retention": info.get("retention", "Unlimited"),
            "purpose": info.get("description", ""),
            "legal_basis": info.get("gdpr_legal_basis", "")
        })
    
    return api_response(
        message="Data categories retrieved",
        data={
            "categories": categories,
            "version": "1.0",
            "last_updated": datetime(2026, 2, 17).isoformat(),
        }
    )


# ============================================================================
# DATA PROTECTION OFFICER INFO
# ============================================================================

async def get_data_controller_info() -> Dict[str, Any]:
    """
    Get data controller information
    """
    defaults = {
        "name": os.getenv("CONTROLLER_NAME"),
        "address": os.getenv("CONTROLLER_ADRESS"),
        "email": os.getenv("CONTROLLER_MAIL"),
    }
    
    return defaults


# ============================================================================
# IMPRINT (IMPRESSUM) ENDPOINT
# ============================================================================

@router.get("/imprint")
@limiter.limit("60/minute")
async def get_imprint(request: Request):
    """
    Get the imprint document (German Impressumspflicht compliant).
    Uses the same controller information as the privacy policy.
    """
    controller_info = await get_data_controller_info()
    
    imprint = {
        "version": "1.0",
        "last_updated": datetime(2026, 2, 17).isoformat(),
        "language": "de",
        "controller": {
            "name": controller_info.get("name", ""),
            "address": controller_info.get("address", ""),
            "email": controller_info.get("email", ""),
            "phone": controller_info.get("phone", "")
        },
        "sections": {
            "about": {
                "title": "Über diesen Dienst",
                "content": "Dieses Voting-System wird als privates nicht-kommerzielles Projekt betrieben. Es wird kostenlos für Bildungszwecke zur Verfügung gestellt. Es werden keine kommerziellen Interessen durch diesen Dienst verfolgt. Die Datenverarbeitung erfolgt ausschließlich zum Zweck der Durchführung von Bildungsbewertungen."
            },
            "operator": {
                "title": "Angaben gemäß § 5 TMG",
                "content": "Angaben zum Anbieter dieses Dienstes:\n\nName: " + controller_info.get("name", "") + "\nAdresse: " + controller_info.get("address", "") + "\nE-Mail: " + controller_info.get("email", "") + ("\nTelefon: " + controller_info.get("phone", "") if controller_info.get("phone") else "")
            },
            "liability_content": {
                "title": "Haftung für Inhalte",
                "content": "Als Betreiber dieses Dienstes bin ich für die eigenen Inhalte auf diesen Seiten verantwortlich. Ich bin jedoch nicht verpflichtet, übermittelte oder gespeicherte fremde Informationen zu überwachen oder Umstände zu untersuchen, die auf eine rechtswidrige Tätigkeit hinweisen."
            },
            "liability_links": {
                "title": "Haftung für Links",
                "content": "Dieses Angebot enthält Links zu externen Webseiten Dritter, auf deren Inhalte ich keinen Einfluss habe. Deshalb kann ich für diese fremden Inhalte keine Haftung übernehmen. Für die Inhalte der verlinkten Seiten ist stets der jeweilige Anbieter oder Betreiber der Seiten verantwortlich."
            },
            "copyright": {
                "title": "Urheberrecht",
                "content": "Die Inhalte und Werke auf diesen Seiten unterliegen dem deutschen Urheberrecht. Die Vervielfältigung, Bearbeitung, Verbreitung oder jede Form der Commerzialisierung solcher Inhalte außerhalb der Grenzen des Urheberrechts bedarf der vorherigen schriftlichen Zustimmung des jeweiligen Autors oder Erstellers."
            },
            "data_protection": {
                "title": "Datenschutz",
                "content": "Diese Website wird in Übereinstimmung mit den geltenden Datenschutzvorschriften betrieben. Informationen zur Datenverarbeitung entnehmen Sie bitte unserer Datenschutzerklärung.",
                "link": "/privacy"
            }
        }
    }
    
    return api_response(
        message="Imprint",
        data=imprint
    )


