"""add user ownership to sessions

Revision ID: 8bdf403a9283
Revises: c180b7a60400
Create Date: 2026-10-05 12:05:40.806339

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8bdf403a9283"
down_revision: Union[str, Sequence[str], None] = "c180b7a60400"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add user ownership to simulation sessions."""

    op.add_column(
        "sessions",
        sa.Column(
            "user_id",
            sa.UUID(),
            nullable=True,
        ),
    )

    op.create_index(
        op.f("ix_sessions_user_id"),
        "sessions",
        ["user_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_sessions_user_id_users",
        "sessions",
        "users",
        ["user_id"],
        ["id"],
    )


def downgrade() -> None:
    """Remove user ownership from simulation sessions."""

    op.drop_constraint(
        "fk_sessions_user_id_users",
        "sessions",
        type_="foreignkey",
    )

    op.drop_index(
        op.f("ix_sessions_user_id"),
        table_name="sessions",
    )

    op.drop_column(
        "sessions",
        "user_id",
    )