"""Add full-text search to documents table.

Revision ID: 002
Revises: 001
Create Date: 2025-12-01
"""

from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	# Add generated tsvector column for full-text search
	# GENERATED ALWAYS AS STORED means PostgreSQL auto-updates the vector
	# when content changes - no triggers or application code needed
	op.execute("""
        ALTER TABLE documents
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
    """)

	# Create GIN index for fast full-text search
	op.execute("""
        CREATE INDEX idx_documents_search_vector
        ON documents USING GIN(search_vector)
    """)


def downgrade() -> None:
	op.execute("DROP INDEX IF EXISTS idx_documents_search_vector")
	op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS search_vector")
