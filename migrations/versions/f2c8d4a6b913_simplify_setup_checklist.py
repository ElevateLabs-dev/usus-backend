"""simplify setup checklist

Revision ID: f2c8d4a6b913
Revises: e6a3c7b1d958
Create Date: 2026-11-23 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2c8d4a6b913'
down_revision: Union[str, Sequence[str], None] = 'e6a3c7b1d958'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('tenants', 'checklist_dismissed_at')
    op.drop_column('tenants', 'launched_at')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('tenants', sa.Column('launched_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('tenants', sa.Column('checklist_dismissed_at', sa.DateTime(timezone=True), nullable=True))
