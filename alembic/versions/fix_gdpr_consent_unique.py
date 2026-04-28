"""fix_gdpr_consent_unique_constraint

Revision ID: fix_gdpr_consent_unique
Revises: add_ip_hash_gdpr
Create Date: 2026-02-13

Fix GDPR consent transfer issue:
- Remove unique constraint that prevents consent transfer
- Allow multiple consent records per user (for audit trail)
- Add index for efficient lookups

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = 'fix_gdpr_consent_unique'
down_revision = '7a8b9c0d1e2f'  # Latest in GDPR branch
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the problematic unique constraint
    op.drop_constraint('uq_gdpr_consent_user_type', table_name='gdpr_consent', type_='unique')
    
    # Add a new index for efficient lookups (non-unique)
    op.create_index('idx_gdpr_consent_user_type_active', 'gdpr_consent', 
                   ['user_id', 'consent_type'], unique=False)
    
    # Note: Multiple consent records per user are now allowed
    # This is better for GDPR audit trail (Art. 30)


def downgrade() -> None:
    # Remove the non-unique index
    op.drop_index('idx_gdpr_consent_user_type_active', table_name='gdpr_consent')
    
    # Restore the unique constraint
    op.create_unique_constraint('uq_gdpr_consent_user_type', 'gdpr_consent', 
                               ['user_id', 'consent_type'])
