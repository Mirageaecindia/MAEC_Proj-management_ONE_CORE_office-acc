"""What the audit log records (decided 2026-10-07).

Every change request a person makes is one entry: who, when, what, on which project.
The catalog below turns each change endpoint into a category and a plain sentence;
`tests/test_audit.py` fails when an endpoint is in neither the catalog nor NOT_AUDITED,
so a new feature can't slip past the log. Reading pages is not logged.
"""

ACCOUNT, PEOPLE, PROJECT, BOOKING, WBS, TIME, HOURS, GOVERNANCE = (
    "account", "people", "project", "booking", "wbs", "time", "hours", "governance",
)  # fmt: skip
CATEGORIES = (ACCOUNT, PEOPLE, PROJECT, BOOKING, WBS, TIME, HOURS, GOVERNANCE)

# Not actions: the browser's minute-by-minute tracking signal, and opening a notification.
NOT_AUDITED = frozenset({
    ("POST", "/api/subtask-tracking/heartbeat"),
    ("POST", "/api/notifications/{notification_id}/read"),
})  # fmt: skip

FAILED_SIGN_IN = "Failed sign-in"

CATALOG: dict[tuple[str, str], tuple[str, str]] = {
    ("POST", "/api/auth/login"): (ACCOUNT, "Signed in"),
    ("POST", "/api/auth/logout"): (ACCOUNT, "Signed out"),
    ("POST", "/api/auth/change-password"): (ACCOUNT, "Changed their password"),
    ("POST", "/api/people/import"): (PEOPLE, "Imported people from a CSV"),
    ("POST", "/api/people/reset-password"): (PEOPLE, "Reset the password of {}"),
    ("PATCH", "/api/people/{user_id}"): (PEOPLE, "Edited {}"),
    ("DELETE", "/api/people/{user_id}"): (PEOPLE, "Deleted the account of {}"),
    ("POST", "/api/people/{user_id}/deactivate"): (PEOPLE, "Deactivated {}"),
    ("POST", "/api/people/{user_id}/reactivate"): (PEOPLE, "Reactivated {}"),
    ("POST", "/api/people/{user_id}/make-bu-head"): (PEOPLE, "Made {} a BU Head"),
    ("POST", "/api/people/{user_id}/remove-bu-head"): (PEOPLE, "Removed the BU Head role from {}"),
    ("POST", "/api/projects"): (PROJECT, "Created a project"),
    ("PUT", "/api/projects/{project_id}"): (PROJECT, "Edited the project"),
    ("DELETE", "/api/projects/{project_id}"): (PROJECT, "Deleted the project"),
    ("POST", "/api/projects/{project_id}/archive"): (PROJECT, "Archived the project"),
    ("POST", "/api/projects/{project_id}/unarchive"): (PROJECT, "Reopened the project"),
    ("POST", "/api/projects/{project_id}/extension-requests"): (GOVERNANCE, "Requested more hours"),
    ("POST", "/api/projects/{project_id}/governance/request-extension"): (GOVERNANCE, "Requested more hours"),
    ("POST", "/api/projects/{project_id}/extension-requests/{request_id}/decision"): (
        GOVERNANCE,
        "Decided an extension request",
    ),
    ("POST", "/api/projects/{project_id}/governance/stop-execution"): (GOVERNANCE, "Stopped execution"),
    ("POST", "/api/projects/{project_id}/governance/resume-execution"): (GOVERNANCE, "Resumed execution"),
    ("POST", "/api/projects/{project_id}/hours/review"): (HOURS, "Reviewed hours"),
    ("POST", "/api/projects/{project_id}/resource-bookings"): (BOOKING, "Booked {}"),
    ("PUT", "/api/projects/{project_id}/resource-bookings/{booking_id}"): (BOOKING, "Edited the booking of {}"),
    ("DELETE", "/api/projects/{project_id}/resource-bookings/{booking_id}"): (BOOKING, "Removed the booking of {}"),
    ("POST", "/api/projects/{project_id}/resource-bookings/submit"): (BOOKING, "Submitted the bookings for approval"),
    ("POST", "/api/projects/{project_id}/resource-bookings/approve"): (BOOKING, "Approved the bookings"),
    ("POST", "/api/projects/{project_id}/resource-bookings/reject"): (BOOKING, "Rejected the bookings"),
    ("PUT", "/api/projects/{project_id}/team-members"): (BOOKING, "Changed their team"),
    ("POST", "/api/projects/{project_id}/wbs-nodes"): (WBS, "Added a WBS item"),
    ("POST", "/api/projects/{project_id}/wbs-nodes/delete"): (WBS, "Deleted WBS items"),
    ("POST", "/api/projects/{project_id}/wbs-upload"): (WBS, "Uploaded a WBS workbook"),
    ("PUT", "/api/wbs-nodes/{node_id}"): (WBS, "Edited {}"),
    ("DELETE", "/api/wbs-nodes/{node_id}"): (WBS, "Deleted {}"),
    ("POST", "/api/wbs-nodes/{node_id}/advance-status"): (WBS, "Changed the status of {}"),
    ("POST", "/api/wbs-nodes/{node_id}/approve"): (WBS, "Approved the task {}"),
    ("POST", "/api/wbs-nodes/{node_id}/comments"): (WBS, "Commented on {}"),
    ("POST", "/api/wbs-nodes/{node_id}/duplicate"): (WBS, "Duplicated {}"),
    ("POST", "/api/wbs-nodes/{node_id}/subtasks"): (WBS, "Added an item under {}"),
    ("POST", "/api/subtask-tracking/start"): (TIME, "Logged in to {}"),
    ("POST", "/api/subtask-tracking/logout"): (TIME, "Logged out of {}"),
    ("POST", "/api/time-log-entries/{entry_id}/approve"): (HOURS, "Approved the hours of {}"),
    ("POST", "/api/time-log-entries/{entry_id}/approve-attended"): (
        HOURS,
        "Approved up to the last visit the hours of {}",
    ),
    ("POST", "/api/time-log-entries/{entry_id}/reapprove"): (HOURS, "Approved again the rejected hours of {}"),
    ("POST", "/api/time-log-entries/{entry_id}/reject"): (HOURS, "Rejected the hours of {}"),
}

# The only request fields an entry may quote, and how. Anything else (passwords above all)
# is never read into the log.
DETAIL_FIELDS: dict[str, str] = {
    "task_name": "“{}”",
    "new_status": "to {}",
    "decision": "{}",
    "action": "{}",
    "requested_hours": "{} h",
    "reason": "reason: {}",
    "comment": "“{}”",
    "comments": "“{}”",
}
DETAIL_LIMIT = 160  # characters of a quoted comment or reason


def detail_from(body: dict) -> str:
    """The quotable parts of a request body, e.g. 'to Done' or 'reason: wrong subtask'."""
    parts = []
    for field, template in DETAIL_FIELDS.items():
        value = body.get(field)
        if value in (None, ""):
            continue
        text = str(value).strip()
        if len(text) > DETAIL_LIMIT:
            text = text[: DETAIL_LIMIT - 1] + "…"
        parts.append(template.format(text))
    return ", ".join(parts)


GONE = "an item since deleted"


def sentence(label: str, target: str | None, detail: str) -> str:
    """'Changed the status of 1.2 Risers (to Done)'. `{}` in the label is the item's name."""
    text = label.format(target or GONE) if "{}" in label else label
    return f"{text} ({detail})" if detail else text
