"""add platform settings

Revision ID: 5c1e2f7a9b40
Revises: d03a76b369fb
Create Date: 2026-10-14 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5c1e2f7a9b40'
down_revision: Union[str, Sequence[str], None] = 'd03a76b369fb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'platform_settings',
        sa.Column('maintenance_mode', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_platform_settings_id'), 'platform_settings', ['id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_platform_settings_id'), table_name='platform_settings')
    op.drop_table('platform_settings')
