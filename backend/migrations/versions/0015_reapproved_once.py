"""reapproved once: a row approved again from the rejected list is the BU Head's from then on

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Stops two leads rejecting and re-approving the same hours in turn: after one
    # re-approval only the BU Head takes the hours back or approves them again.
    with op.batch_alter_table("time_log_entries", schema=None) as batch_op:
        batch_op.add_column(sa.Column("reapproved_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("time_log_entries", schema=None) as batch_op:
        batch_op.drop_column("reapproved_at")
