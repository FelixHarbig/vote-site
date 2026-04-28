"""add_ip_hash_gdpr

Revision ID: add_ip_hash_gdpr
Revises: 4ade333fd6c3
Create Date: 2025-02-12

GDPR compliance changes:
- Replace ip_address with ip_hash in votes table (privacy protection)
- GDPR mode enabled by default

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_ip_hash_gdpr'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add ip_hash column to votes table (replaces raw ip_address for GDPR compliance)
    op.add_column('votes', sa.Column('ip_hash', sa.String(64), nullable=True))

    # Create index on ip_hash for abuse detection queries
    op.create_index('idx_votes_ip_hash', 'votes', ['ip_hash'])

    # Note: The old ip_address column is kept for rollback compatibility
    # It can be safely dropped after verifying all new votes use ip_hash
    # op.drop_column('votes', 'ip_address')  # Optional: uncomment after migration verified


def downgrade() -> None:
    # Drop the index first
    op.drop_index('idx_votes_ip_hash', table_name='votes')
    
    # Drop the ip_hash column
    op.drop_column('votes', 'ip_hash')
