from .router import admin_router as router
from ..schemas import AdminResponse
from fastapi import Request, Response
from api.utils import api_response
import csv
import codecs
from database.models import VoteCodes, get_session, Teachers, Votes
import io
from common.log_handler import log
from sqlalchemy import select
import csv

async def export_model(model_class, filename: str, request: Request):
    """Generic CSV export for any SQLAlchemy model"""
    async with get_session() as session:
        result = await session.execute(
            select(model_class).order_by(model_class.id)
        )
        instances = result.scalars().all()
        # Dynamic columns excluding relationships
        fieldnames = [col.name for col in model_class.__table__.columns 
                     if col.name != model_class.__mapper__.relationships]
        
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for instance in instances:
            row = {col.name: getattr(instance, col.name) 
                   for col in model_class.__table__.columns 
                   if col.name != model_class.__mapper__.relationships}
            if "continuation_key" in row:
                key = row.pop("continuation_key")
                row["continuation_key"] = "awaiting" if key and key.startswith("awaiting") else "active" if key else "unregistered"
            writer.writerow(row)
        csv_content = output.getvalue()
        output.close()
        return Response( content=csv_content, media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Cache-Control": "no-cache" })
    

@router.get("/export/votecodes")
async def export_teachers(request: Request):
    return await export_model(VoteCodes, "votecodes.csv", request)

@router.get("/export/teachers")
async def export_teachers(request: Request):
    return await export_model(Teachers, "teachers.csv", request)

@router.get("/export/votes")
async def export_votes(request: Request):
    return await export_model(Votes, "votes.csv", request)

