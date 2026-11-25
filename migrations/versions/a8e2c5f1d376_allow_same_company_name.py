"""allow same company name

Revision ID: a8e2c5f1d376
Revises: f2c8d4a6b913
Create Date: 2026-11-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a8e2c5f1d376'
down_revision: Union[str, Sequence[str], None] = 'f2c8d4a6b913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('tenants_name_key', 'tenants', type_='unique')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_unique_constraint('tenants_name_key', 'tenants', ['name'])
