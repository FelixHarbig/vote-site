"""add_gdpr_tables

Revision ID: a1b2c3d4e5f6
Revises: (latest revision)
Create Date: 2024-01-01 00:00:00.000000

GDPR compliance tables:
- gdpr_consent: Track user consent records
- gdpr_requests: Track GDPR data requests
- gdpr_audit_log: Audit trail
- data_protection_info: Data controller info
- user_id column in votes table
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'a1b2c3d4e5f6'
down_revision = 'd87843916e25'  # Update this to latest revision
branch_labels = None
depends_on = None


def upgrade():
    # Add user_id column to votes table
    op.add_column('votes', sa.Column('user_id', sa.String(255), nullable=True))
    op.create_index('idx_votes_user_id', 'votes', ['user_id'])
    
    # Create gdpr_consent table
    op.create_table(
        'gdpr_consent',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('session_id', sa.String(255), nullable=True),
        sa.Column('consent_type', sa.String(100), nullable=False),
        sa.Column('granted', sa.Boolean(), nullable=False),
        sa.Column('consent_version', sa.String(20), nullable=False, server_default='1.0'),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('timestamp', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'consent_type', name='uq_gdpr_consent_user_type')
    )
    op.create_index('idx_gdpr_consent_user_type', 'gdpr_consent', ['user_id', 'consent_type'])
    
    # Create gdpr_requests table
    op.create_table(
        'gdpr_requests',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('request_id', sa.String(100), nullable=False),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('request_type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('priority', sa.String(20), nullable=False, server_default='normal'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('deadline_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('verification_code', sa.String(100), nullable=True),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('processed_by', sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('request_id')
    )
    op.create_index('idx_gdpr_requests_status', 'gdpr_requests', ['status'])
    op.create_index('idx_gdpr_requests_deadline', 'gdpr_requests', ['deadline_at'])
    
    # Create gdpr_audit_log table
    op.create_table(
        'gdpr_audit_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.String(255), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('resource', sa.String(100), nullable=False),
        sa.Column('details', postgresql.JSONB(), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('timestamp', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_gdpr_audit_user', 'gdpr_audit_log', ['user_id'])
    op.create_index('idx_gdpr_audit_timestamp', 'gdpr_audit_log', ['timestamp'])
    
    # Create data_protection_info table
    op.create_table(
        'data_protection_info',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('key', sa.String(100), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key')
    )


def downgrade():
    # Drop tables in reverse order
    op.drop_table('data_protection_info')
    op.drop_table('gdpr_audit_log')
    op.drop_table('gdpr_requests')
    op.drop_table('gdpr_consent')
    
    # Drop index and column from votes
    op.drop_index('idx_votes_user_id', table_name='votes')
    op.drop_column('votes', 'user_id')
