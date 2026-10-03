"""must change password: a temporary password is replaced at the first login

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Onboarded and reset accounts get a temporary password that the person must replace
    # before anything else works. Existing accounts keep working as they are.
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("must_change_password", sa.Boolean(), server_default="0", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("must_change_password")
