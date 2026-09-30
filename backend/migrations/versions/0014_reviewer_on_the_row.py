"""reviewer on the row: the user who last decided a day's hours

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Rejected hours may be approved again within seven days by a lead of the project, but
    # hours the BU Head rejected only by the BU Head: the row remembers who decided it.
    # Rows reviewed before this have no reviewer id and are treated as the BU Head's.
    with op.batch_alter_table("time_log_entries", schema=None) as batch_op:
        batch_op.add_column(sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("time_log_entries", schema=None) as batch_op:
        batch_op.drop_column("reviewed_by_user_id")
