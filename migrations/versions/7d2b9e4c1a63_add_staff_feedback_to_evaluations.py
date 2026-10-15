"""add staff feedback to evaluations

Revision ID: 7d2b9e4c1a63
Revises: 5c1e2f7a9b40
Create Date: 2026-10-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d2b9e4c1a63'
down_revision: Union[str, Sequence[str], None] = '5c1e2f7a9b40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('evaluation_results', sa.Column('staff_feedback', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('evaluation_results', 'staff_feedback')
