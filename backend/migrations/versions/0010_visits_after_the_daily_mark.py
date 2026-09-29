"""visits after the daily mark: sessions record the last visit and who ended them

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Decided 2026-09-30: hours over 8 a day are banked, and past that mark an engineer who
    # doesn't visit the app for 30 minutes is logged out at their last visit.
    with op.batch_alter_table("time_sessions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("ended_by", sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("time_sessions", schema=None) as batch_op:
        batch_op.drop_column("ended_by")
        batch_op.drop_column("last_active_at")
