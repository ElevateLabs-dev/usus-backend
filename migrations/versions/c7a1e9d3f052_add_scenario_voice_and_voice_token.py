"""add scenario voice and session voice token

Revision ID: c7a1e9d3f052
Revises: b4f2d8e6a913
Create Date: 2026-11-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7a1e9d3f052'
down_revision: Union[str, Sequence[str], None] = 'b4f2d8e6a913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('scenarios', sa.Column('voice_id', sa.String(length=40), nullable=True))
    op.add_column('sessions', sa.Column('voice_token', sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sessions', 'voice_token')
    op.drop_column('scenarios', 'voice_id')
