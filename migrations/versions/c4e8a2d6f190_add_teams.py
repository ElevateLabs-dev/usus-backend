"""add teams

Revision ID: c4e8a2d6f190
Revises: b7d2f4a8c613
Create Date: 2026-11-23 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e8a2d6f190'
down_revision: Union[str, Sequence[str], None] = 'b7d2f4a8c613'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _base_columns() -> list:
    return [
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    ]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'teams',
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        *_base_columns(),
        sa.UniqueConstraint('tenant_id', 'name'),
    )
    op.create_table(
        'team_members',
        sa.Column('team_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        *_base_columns(),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('team_id', 'user_id'),
    )
    op.create_table(
        'team_scenarios',
        sa.Column('team_id', sa.UUID(), nullable=False),
        sa.Column('scenario_id', sa.UUID(), nullable=False),
        *_base_columns(),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['scenario_id'], ['scenarios.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('team_id', 'scenario_id'),
    )
    for table, columns in (
        ('teams', ['tenant_id']),
        ('team_members', ['tenant_id', 'team_id', 'user_id']),
        ('team_scenarios', ['tenant_id', 'team_id', 'scenario_id']),
    ):
        op.create_index(op.f(f'ix_{table}_id'), table, ['id'], unique=True)
        for column in columns:
            op.create_index(op.f(f'ix_{table}_{column}'), table, [column], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('team_scenarios')
    op.drop_table('team_members')
    op.drop_table('teams')
