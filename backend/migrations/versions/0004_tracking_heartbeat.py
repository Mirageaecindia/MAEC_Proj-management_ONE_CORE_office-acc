"""tracking heartbeat: worked time = logout - login, with a last-seen heartbeat

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-27 22:42:46.448677
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("time_sessions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("version_id", sa.Integer(), nullable=True))
    # An old session was last seen at its logout, or its last sync (updated_at).
    op.execute("UPDATE time_sessions SET last_seen_at = COALESCE(logout_at, updated_at, login_at), version_id = 1")
    with op.batch_alter_table("time_sessions", schema=None) as batch_op:
        batch_op.alter_column("last_seen_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch_op.alter_column("version_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("time_sessions", schema=None) as batch_op:
        batch_op.drop_column("version_id")
        batch_op.drop_column("last_seen_at")
