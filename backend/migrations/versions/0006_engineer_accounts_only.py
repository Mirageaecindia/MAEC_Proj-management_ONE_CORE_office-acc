"""engineer accounts only: lead accounts become engineers with an employee record

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Leading a project is now a role on the project (decided 2026-09-28). Every
    # former lead account becomes an engineer account; one without an employee
    # record gets one, so the BU Head can still pick them as a lead.
    connection = op.get_bind()
    leads = connection.execute(
        sa.text("SELECT id, username, full_name, discipline FROM users WHERE role = 'lead' AND employee_id IS NULL")
    ).all()
    for user_id, username, full_name, discipline in leads:
        title = f"{discipline} Lead" if discipline else "Lead"
        connection.execute(
            sa.text(
                "INSERT INTO employees (employee_code, name, role_title, discipline) "
                "VALUES (:code, :name, :title, :discipline)"
            ),
            {"code": f"L{user_id:04d}", "name": full_name or username, "title": title, "discipline": title},
        )
        employee_id = connection.execute(
            sa.text("SELECT id FROM employees WHERE employee_code = :code"), {"code": f"L{user_id:04d}"}
        ).scalar_one()
        connection.execute(
            sa.text("UPDATE users SET employee_id = :employee_id WHERE id = :id"),
            {"employee_id": employee_id, "id": user_id},
        )
    connection.execute(sa.text("UPDATE users SET role = 'engineer' WHERE role = 'lead'"))
    connection.execute(sa.text("UPDATE notifications SET recipient_role = 'engineer' WHERE recipient_role = 'lead'"))

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("discipline")


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("discipline", sa.VARCHAR(length=100), nullable=True))
