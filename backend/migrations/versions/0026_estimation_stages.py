"""estimation stages: the design stage (CD, SD, DD, TD, IFC) of each date column of an estimation

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Empty for the estimations saved so far: no stage chosen yet.
    with op.batch_alter_table("project_estimations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("stages", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("project_estimations", schema=None) as batch_op:
        batch_op.drop_column("stages")
