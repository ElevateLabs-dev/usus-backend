"""add metrics

Revision ID: b7d2f4a8c613
Revises: a3c9e1f7b254
Create Date: 2026-11-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d2f4a8c613'
down_revision: Union[str, Sequence[str], None] = 'a3c9e1f7b254'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'metrics',
        sa.Column('key', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'key'),
    )
    op.create_index(op.f('ix_metrics_id'), 'metrics', ['id'], unique=True)
    op.create_index(op.f('ix_metrics_tenant_id'), 'metrics', ['tenant_id'], unique=False)
    op.add_column('scenarios', sa.Column('metrics', sa.JSON(), server_default=sa.text("'[]'"), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('scenarios', 'metrics')
    op.drop_index(op.f('ix_metrics_tenant_id'), table_name='metrics')
    op.drop_index(op.f('ix_metrics_id'), table_name='metrics')
    op.drop_table('metrics')
