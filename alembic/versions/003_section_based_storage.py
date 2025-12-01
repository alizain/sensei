"""Section-based storage for tome documents.

Move content from documents to sections table. Documents become containers,
sections hold the actual content with FTS. This solves the PostgreSQL tsvector
size limit issue (~1MB) by chunking content by markdown headings.

Revision ID: 003
Revises: 002
Create Date: 2025-12-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create sections table
    op.create_table(
        "sections",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("document_id", UUID(as_uuid=True), nullable=False),
        sa.Column("parent_section_id", UUID(as_uuid=True), nullable=True),
        sa.Column("heading", sa.String(), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "inserted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_section_id"],
            ["sections.id"],
            ondelete="CASCADE",
        ),
    )

    # Create indexes on sections
    op.create_index("ix_sections_document_id", "sections", ["document_id"])
    op.create_index("ix_sections_parent_section_id", "sections", ["parent_section_id"])

    # Add generated tsvector column for full-text search on sections
    op.execute("""
        ALTER TABLE sections
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
    """)

    # Create GIN index for fast full-text search on sections
    op.execute("""
        CREATE INDEX idx_sections_search_vector
        ON sections USING GIN(search_vector)
    """)

    # Remove content and search_vector from documents table
    # Documents are now containers, sections hold content
    op.execute("DROP INDEX IF EXISTS idx_documents_search_vector")
    op.drop_column("documents", "search_vector")
    op.drop_column("documents", "content")


def downgrade() -> None:
    # Add content column back to documents
    op.add_column(
        "documents",
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
    )
    # Remove the server default after adding the column
    op.alter_column("documents", "content", server_default=None)

    # Add search_vector back to documents
    op.execute("""
        ALTER TABLE documents
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
    """)
    op.execute("""
        CREATE INDEX idx_documents_search_vector
        ON documents USING GIN(search_vector)
    """)

    # Drop sections table
    op.execute("DROP INDEX IF EXISTS idx_sections_search_vector")
    op.drop_index("ix_sections_parent_section_id", table_name="sections")
    op.drop_index("ix_sections_document_id", table_name="sections")
    op.drop_table("sections")
