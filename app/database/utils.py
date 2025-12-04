from sqlalchemy import select
from database.models import get_session, Teachers, VoteCodes

async def fetch_teachers():
    async with get_session() as session:
        result = await session.execute(
            select(Teachers).where(Teachers.disabled == False)
        )
        teachers = result.scalars().all()

    return {
        str(t.id): {                # keys as strings to match json_schema_extra style
            "name": t.name,
            "gender": t.gender,
            "subjects": t.subjects,
            "description": t.description,
        }
        for t in teachers
    }

