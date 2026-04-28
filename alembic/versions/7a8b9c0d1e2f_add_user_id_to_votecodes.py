"""Add user_id to votecodes for linked voting

Revision ID: 7a8b9c0d1e2f
Revises: add_ip_hash_gdpr
Create Date: 2026-02-13 13:27:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a8b9c0d1e2f'
down_revision: Union[str, None] = 'add_ip_hash_gdpr'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('votecodes', sa.Column('user_id', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_votecodes_user_id'), 'votecodes', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_votecodes_user_id'), table_name='votecodes')
    op.drop_column('votecodes', 'user_id')
