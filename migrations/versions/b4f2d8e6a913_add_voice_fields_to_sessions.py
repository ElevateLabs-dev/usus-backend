"""add voice fields to sessions

Revision ID: b4f2d8e6a913
Revises: 9e3a1c5d7b20
Create Date: 2026-10-21 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4f2d8e6a913'
down_revision: Union[str, Sequence[str], None] = '9e3a1c5d7b20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('sessions', sa.Column('voice_assistant_id', sa.String(length=64), nullable=True))
    op.add_column('sessions', sa.Column('voice_call_id', sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sessions', 'voice_call_id')
    op.drop_column('sessions', 'voice_assistant_id')
