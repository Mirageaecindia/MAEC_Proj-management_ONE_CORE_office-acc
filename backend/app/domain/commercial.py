"""Money is the BU Head's (decided 2026-10-07).

Contract value, currency, budget burn and costs are sent to the BU Head only. Leads and
engineers plan and track in hours; the server leaves the money out of what it sends
them, so no page can show it by mistake.
"""

from app.core.roles import Role

MONEY_FIELDS = ("contract_value", "contract_currency")


def sees_money(user) -> bool:
    return user.role == Role.BU_HEAD


def without_money(record: dict) -> dict:
    """The record with its money fields emptied (kept as keys, so the response shape stays)."""
    return {**record, **dict.fromkeys(MONEY_FIELDS)}
