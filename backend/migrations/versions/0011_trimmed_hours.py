"""trimmed hours: what "approve up to the last visit" left out of a day

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A reviewer may approve a day only up to the engineer's last visit; the rest stays on
    # the row as trimmed hours (and in the audit log), so nothing logged is lost.
    with op.batch_alter_table("time_log_entries", schema=None) as batch_op:
        batch_op.add_column(sa.Column("trimmed_hours", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("time_log_entries", schema=None) as batch_op:
        batch_op.drop_column("trimmed_hours")
