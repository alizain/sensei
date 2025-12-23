"""query_messages_to_jsonb

Revision ID: 8dfe094b42a0
Revises: 98d24c27bbe3
Create Date: 2025-12-06 12:36:42.722577
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8dfe094b42a0"
down_revision: Union[str, None] = "98d24c27bbe3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Convert existing Text JSON to JSONB with explicit casting
    op.execute("""
        ALTER TABLE queries
        ALTER COLUMN messages TYPE JSONB
        USING messages::jsonb
    """)


def downgrade() -> None:
    # Convert JSONB back to Text
    op.execute("""
        ALTER TABLE queries
        ALTER COLUMN messages TYPE TEXT
        USING messages::text
    """)
