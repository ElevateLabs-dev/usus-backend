"""add setup checklist

Revision ID: e6a3c7b1d958
Revises: d1b5f9c3e742
Create Date: 2026-11-23 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6a3c7b1d958'
down_revision: Union[str, Sequence[str], None] = 'd1b5f9c3e742'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('tenants', sa.Column('logo_key', sa.String(length=255), nullable=True))
    op.add_column('tenants', sa.Column('launched_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('tenants', sa.Column('checklist_dismissed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('walkthrough_done_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'walkthrough_done_at')
    op.drop_column('tenants', 'checklist_dismissed_at')
    op.drop_column('tenants', 'launched_at')
    op.drop_column('tenants', 'logo_key')
