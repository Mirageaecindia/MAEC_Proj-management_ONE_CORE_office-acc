"""Migration 0006: former lead accounts become engineers with an employee record (L1 stage 4)."""

from alembic import command
from sqlalchemy import create_engine, inspect, text

from app.core.migrations import _config


def _upgrade(engine, revision):
    with engine.begin() as connection:
        command.upgrade(_config(connection), revision)


def test_lead_accounts_become_engineers_with_an_employee_record(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    _upgrade(engine, "0005")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO employees (id, employee_code, name, role_title) "
                "VALUES (7, 'E0007', 'Priya Nair', 'Mechanical Engineer')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO users (id, username, password_hash, full_name, role, discipline, employee_id, is_active) "
                "VALUES "
                "(1, 'lead.anita', 'x', 'Anita Kumar', 'lead', 'Electrical', NULL, 1), "
                "(2, 'lead.priya', 'x', 'Priya Nair', 'lead', 'Mechanical', 7, 1), "
                "(3, 'buhead', 'x', 'Boss', 'bu_head', NULL, NULL, 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO notifications (recipient_role, recipient_user_id, notification_type, title, is_read) "
                "VALUES ('lead', 1, 't', 't', 0)"
            )
        )

    _upgrade(engine, "head")

    with engine.connect() as connection:
        users = connection.execute(text("SELECT username, role, employee_id FROM users ORDER BY id")).all()
        anita_employee = connection.execute(
            text("SELECT employee_code, name, role_title FROM employees WHERE id = :id"), {"id": users[0][2]}
        ).one()
        roles = connection.execute(text("SELECT DISTINCT recipient_role FROM notifications")).scalars().all()
    assert [(u[0], u[1]) for u in users] == [
        ("lead.anita", "engineer"),
        ("lead.priya", "engineer"),
        ("buhead", "bu_head"),
    ]
    assert users[1][2] == 7  # an existing employee link is kept
    assert users[2][2] is None
    assert tuple(anita_employee) == ("L0001", "Anita Kumar", "Electrical Lead")
    assert roles == ["engineer"]
    assert "discipline" not in {column["name"] for column in inspect(engine).get_columns("users")}
