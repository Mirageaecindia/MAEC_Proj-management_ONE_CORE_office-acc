"""rename the phase ID Coordination to ID - RCP Coordination

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD, NEW = "ID Coordination", "ID - RCP Coordination"


def upgrade() -> None:
    # Data only: the WBS items of the renamed phase take its new name. Nothing else changes.
    op.execute(sa.text("UPDATE wbs_nodes SET phase = :new WHERE phase = :old").bindparams(new=NEW, old=OLD))


def downgrade() -> None:
    op.execute(sa.text("UPDATE wbs_nodes SET phase = :old WHERE phase = :new").bindparams(new=NEW, old=OLD))
