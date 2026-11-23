"""add knowledge base

Revision ID: d1b5f9c3e742
Revises: c4e8a2d6f190
Create Date: 2026-11-23 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = 'd1b5f9c3e742'
down_revision: Union[str, Sequence[str], None] = 'c4e8a2d6f190'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.add_column('tenants', sa.Column('use_kb_for_evaluation', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.create_table(
        'documents',
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('file_type', sa.String(length=10), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('char_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('chunk_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('uploaded_by', sa.UUID(), nullable=True),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_documents_id'), 'documents', ['id'], unique=True)
    op.create_index(op.f('ix_documents_tenant_id'), 'documents', ['tenant_id'], unique=False)
    op.create_table(
        'document_chunks',
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(1536), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_document_chunks_id'), 'document_chunks', ['id'], unique=True)
    op.create_index(op.f('ix_document_chunks_document_id'), 'document_chunks', ['document_id'], unique=False)
    op.create_index(op.f('ix_document_chunks_tenant_id'), 'document_chunks', ['tenant_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('document_chunks')
    op.drop_table('documents')
    op.drop_column('tenants', 'use_kb_for_evaluation')
