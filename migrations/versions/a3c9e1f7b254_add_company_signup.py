"""add company signup

Revision ID: a3c9e1f7b254
Revises: e1f4a7b2c9d3
Create Date: 2026-11-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3c9e1f7b254'
down_revision: Union[str, Sequence[str], None] = 'e1f4a7b2c9d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('tenants', sa.Column('company_type', sa.String(length=100), nullable=True))
    op.add_column('tenants', sa.Column('referral_source', sa.String(length=100), nullable=True))
    op.create_table(
        'pending_signups',
        sa.Column('email', sa.String(length=254), nullable=False),
        sa.Column('company_name', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(), nullable=False),
        sa.Column('company_type', sa.String(length=100), nullable=True),
        sa.Column('referral_source', sa.String(length=100), nullable=True),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('last_sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sends', sa.Integer(), server_default=sa.text('1'), nullable=False),
        sa.Column('window_started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_pending_signups_id'), 'pending_signups', ['id'], unique=True)
    op.create_index(op.f('ix_pending_signups_email'), 'pending_signups', ['email'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_pending_signups_email'), table_name='pending_signups')
    op.drop_index(op.f('ix_pending_signups_id'), table_name='pending_signups')
    op.drop_table('pending_signups')
    op.drop_column('tenants', 'referral_source')
    op.drop_column('tenants', 'company_type')
