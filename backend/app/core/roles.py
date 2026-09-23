"""Account roles. Values match the strings stored in users.role."""

from enum import StrEnum


class Role(StrEnum):
    BU_HEAD = "bu_head"
    LEAD = "lead"
    ENGINEER = "engineer"


ALL_ROLES = frozenset(Role)
