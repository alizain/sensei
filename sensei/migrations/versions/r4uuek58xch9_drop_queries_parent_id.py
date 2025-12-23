"""drop_queries_parent_id

Revision ID: r4uuek58xch9
Revises: 8dfe094b42a0
Create Date: 2025-12-18

Removes the vestigial parent_id column from queries table.
This column was never populated (always NULL) and is no longer
part of the data model.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "r4uuek58xch9"
down_revision: Union[str, None] = "8dfe094b42a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use raw SQL with IF EXISTS for idempotency
    # (alembic's drop_constraint/drop_column fail if not present)
    op.execute("ALTER TABLE queries DROP CONSTRAINT IF EXISTS queries_parent_id_fkey")
    op.execute("ALTER TABLE queries DROP COLUMN IF EXISTS parent_id")


def downgrade() -> None:
    # Re-add the column and foreign key constraint
    op.add_column(
        "queries",
        sa.Column("parent_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "queries_parent_id_fkey",
        "queries",
        "queries",
        ["parent_id"],
        ["id"],
    )
