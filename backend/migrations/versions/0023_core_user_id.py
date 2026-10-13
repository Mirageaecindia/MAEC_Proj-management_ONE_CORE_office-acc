"""core user id: each account's id in MAEC One Core, which signs everyone in

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Empty for every existing account: each is linked by email at the person's first visit
    # through the gate (app/services/identity.py). Unique: one Core person, one account.
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("core_user_id", sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f("ix_users_core_user_id"), ["core_user_id"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_core_user_id"))
        batch_op.drop_column("core_user_id")
