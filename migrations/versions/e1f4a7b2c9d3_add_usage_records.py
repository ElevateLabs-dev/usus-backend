"""add usage records

Revision ID: e1f4a7b2c9d3
Revises: d5e8f2a4b061
Create Date: 2026-11-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1f4a7b2c9d3'
down_revision: Union[str, Sequence[str], None] = 'd5e8f2a4b061'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'usage_records',
        sa.Column('session_id', sa.UUID(), nullable=True),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('purpose', sa.String(length=32), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('seconds', sa.Integer(), nullable=False),
        sa.Column('cost_usd', sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_usage_records_id'), 'usage_records', ['id'], unique=True)
    op.create_index(op.f('ix_usage_records_session_id'), 'usage_records', ['session_id'], unique=False)
    op.create_index(op.f('ix_usage_records_tenant_id'), 'usage_records', ['tenant_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_usage_records_tenant_id'), table_name='usage_records')
    op.drop_index(op.f('ix_usage_records_session_id'), table_name='usage_records')
    op.drop_index(op.f('ix_usage_records_id'), table_name='usage_records')
    op.drop_table('usage_records')
