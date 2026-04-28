"""Add session_id to votecodes table for GDPR consent tracking

Revision ID: add_session_id_votecodes
Revises: fix_gdpr_consent_unique
Create Date: 2026-02-13

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_session_id_votecodes'
down_revision = 'fix_gdpr_consent_unique'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'votecodes',
        sa.Column('session_id', sa.String(255), nullable=True, index=True)
    )


def downgrade() -> None:
    op.drop_column('votecodes', 'session_id')
