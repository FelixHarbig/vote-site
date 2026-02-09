"""
Protected admin router with JWT authentication.
All admin endpoints should use this router instead of the main router.
"""

from fastapi import APIRouter, Depends
from api.auth.jwt_utils import get_current_admin

# Create admin router with JWT dependency applied to all routes
admin_router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(get_current_admin)]
)
