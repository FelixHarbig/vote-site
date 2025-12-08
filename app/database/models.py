import sqlalchemy
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv
import os
from common.log_handler import log
from contextlib import asynccontextmanager
load_dotenv()


class VotingEngine(DeclarativeBase): # don't ask me why but apparently this works better
    pass

try:
    databasepath=os.getenv("DATABASE_URL")
    if not databasepath or databasepath.strip() == "" or not databasepath.startswith("postgresql://"):
        raise ValueError("rtfd")
    voting_engine = create_async_engine(f'postgresql+asyncpg{os.getenv("DATABASE_URL")[10:]}', echo=False, pool_size=20, max_overflow=10,pool_recycle=3600, pool_pre_ping=True) # path in general needs to be "normal" and not async, especially for alembic
except Exception as e:
    log.critical(f"Database connection failed: {e}")
    raise e

class Teachers(VotingEngine):
    __tablename__ = 'teachers'
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    name = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    votes = sqlalchemy.orm.relationship("Votes", back_populates="teacher", lazy="selectin")
    images = sqlalchemy.orm.relationship("Images", back_populates="teacher", lazy="selectin")
    gender = sqlalchemy.Column(sqlalchemy.Boolean, nullable=False)
    subjects = sqlalchemy.Column(sqlalchemy.ARRAY(sqlalchemy.String), nullable=False)
    description = sqlalchemy.Column(sqlalchemy.String, nullable=True)
    
    disabled = sqlalchemy.Column(sqlalchemy.Boolean, default=False, nullable=False)
    

"""
When adding new Colums:
    - If Column isn't one that should be voted on, add it to the variable creation of votes_model_fields (in manage_votes.py and vote.py)
    - If Column should be voted on add it to VoteSubmissionItem in schemas.py
you will also need to update the database (read the docs for this)
"""

class Votes(VotingEngine):
    __tablename__ = 'votes'
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    teacher_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey('teachers.id'), nullable=False)
    timestamp = sqlalchemy.Column(sqlalchemy.DateTime, server_default=sqlalchemy.func.now())
    overall = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    understandability = sqlalchemy.Column(sqlalchemy.Integer, nullable=True)
    helpfulness = sqlalchemy.Column(sqlalchemy.Integer, nullable=True)
    fairness = sqlalchemy.Column(sqlalchemy.Integer, nullable=True)
    clarity = sqlalchemy.Column(sqlalchemy.Integer, nullable=True)
    homework_amount = sqlalchemy.Column(sqlalchemy.Integer, nullable=True)
    exam_difficulty = sqlalchemy.Column(sqlalchemy.Integer, nullable=True)
    humor = sqlalchemy.Column(sqlalchemy.Integer, nullable=True)
    character = sqlalchemy.Column(sqlalchemy.Integer, nullable=True)
    style = sqlalchemy.Column(sqlalchemy.Integer, nullable=True)

    ip_address = sqlalchemy.Column(sqlalchemy.String, nullable=True)

    teacher = sqlalchemy.orm.relationship("Teachers", back_populates="votes")

class Images(VotingEngine):
    __tablename__ = 'images'
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    teacher_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey('teachers.id'), nullable=False)
    image = sqlalchemy.Column(sqlalchemy.LargeBinary, nullable=False)

    teacher = sqlalchemy.orm.relationship("Teachers", back_populates="images")
    disabled = sqlalchemy.Column(sqlalchemy.Boolean, default=False, nullable=False)

class VoteCodes(VotingEngine):
    __tablename__ = 'votecodes'
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    code = sqlalchemy.Column(sqlalchemy.String, unique=True, nullable=False)
    used = sqlalchemy.Column(sqlalchemy.Boolean, default=False, nullable=False)
    grade = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    gender = sqlalchemy.Column(sqlalchemy.Boolean, nullable=True)
    continuation_key = sqlalchemy.Column(sqlalchemy.String, nullable=True)

    disabled = sqlalchemy.Column(sqlalchemy.Boolean, default=False, nullable=False)

class Settings(VotingEngine):
    __tablename__ = "settings"
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    name = sqlalchemy.Column(sqlalchemy.String, unique=True, nullable=False)
    enabled = sqlalchemy.Column(sqlalchemy.Boolean, nullable=False)

AsyncSessionLocal = sqlalchemy.ext.asyncio.async_sessionmaker(voting_engine, class_=sqlalchemy.ext.asyncio.AsyncSession, expire_on_commit=False)

@asynccontextmanager
async def get_session():
    async with AsyncSessionLocal() as session:
        yield session

"""
Aquire this session with:
async with get_session() as session:
"""