"""notification link: a page in the app a notification opens

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Optional: existing notifications keep no link.
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.add_column(sa.Column("link", sa.String(length=300), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.drop_column("link")
