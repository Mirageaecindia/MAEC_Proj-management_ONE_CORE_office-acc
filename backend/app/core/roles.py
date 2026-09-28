"""Account roles. Values match the strings stored in users.role."""

from enum import StrEnum


class Role(StrEnum):
    """Account roles. Leading a project is not one: see app/services/access.py."""

    BU_HEAD = "bu_head"
    ENGINEER = "engineer"


ALL_ROLES = frozenset(Role)
