# MAEC Accounts & Login

MAEC requires real login. There are two kinds of account, and one role on a project:

| Account   | Sees / Can Do                                                            |
|-----------|--------------------------------------------------------------------------|
| `bu_head` | Projects, Create Project, Resource Booking, WBS Structure, Timeline & Logs, Executive Dashboard, Work Summary. Creates projects and chooses their leads, approves bookings and extension requests, approves the project leads' own hours. |
| `engineer`| WBS Structure, Timeline & Logs, Performance Dashboard. Works on assigned subtasks (Login/Logout records the hours) and submits their week. |
| **lead of a project** | Not an account: the BU Head picks any engineer as a project's Electrical, Mechanical or BIM lead, with a period and a utilization %. On that project they book engineers, build the WBS, approve tasks and engineers' hours, and request extra hours. An engineer who leads any project also gets the Resource Booking and Executive Dashboard tabs. |

Role and identity come only from the logged-in session and the project's data.
There is no role-switcher and no `?role=` URL override.

## Creating accounts

**In the app (normal way, no server access):** the BU Head imports engineers from the HR export on
Projects → People. Each gets an engineer account named by their work email, linked to an employee record
(employee code = HR employee id), with a random temporary password that must be changed at the first login.
The BU Head resets forgotten passwords on the same card, and sees everyone with an account there:
corrects an engineer's name, work email or job role, deactivates or reactivates a leaver, and deletes only an
account with no work on record. A BU Head can make an engineer who is on no live project a BU Head, and
take the role back from a promoted BU Head, confirmed with their own password. See `app/services/provisioning.py`; this moves to
the company's global admin application when it exists.

Users are never seeded at startup. From the `backend` directory, the CLI also creates them:

```
.venv\Scripts\python.exe create_user.py
```

It prompts for username, password, full name and role. Engineers must be
linked to an existing `employees` row (that is what scopes their bookings,
subtasks, hours and performance dashboard, and what lets the BU Head pick them
as a project lead):

```
.venv\Scripts\python.exe create_user.py --username eng.arjun --role engineer --employee-id 1 --full-name "Arjun Mehta"
.venv\Scripts\python.exe create_user.py --username buhead --role bu_head --full-name "Test BU Head"
```

Notes:
- `employee-id` must match the `id` in the `employees` table.
- Passwords are stored as PBKDF2-HMAC-SHA256 hashes (no plaintext, no external
  dependencies).
- Logging out deletes the session token server-side.
- Accounts created as `lead` before September 2026 were converted to engineer
  accounts by migration 0006, each with an employee record (code `L<user id>`).

## Deactivating a leaver

Deactivation logs the person out everywhere at once and blocks future logins
(they see the normal "Invalid username or password"). Their data stays. An
inactive account no longer appears in the Create Project lead dropdowns.

```
.venv\Scripts\python.exe create_user.py --username eng.arjun --deactivate
.venv\Scripts\python.exe create_user.py --username eng.arjun --activate
```

## Auth flow

- `POST /api/auth/login` → returns `token`, `role`, `full_name`, `engineer_id`, `leads_projects` (whether the person leads at least one project) and `must_change_password`. Usernames are matched without regard to case.
- While `must_change_password` is set (a temporary password from onboarding or a reset), every endpoint except `GET /api/auth/me`, `POST /api/auth/change-password` and logout answers 403 with `X-Error-Code: PASSWORD_CHANGE_REQUIRED`.
- `POST /api/auth/change-password` `{current_password, new_password}` (at least 8 characters, different from the current one) sets the person's own password; their other sessions end.
- Every other endpoint requires `Authorization: Bearer <token>`.
- `GET /api/auth/me` restores the session on page refresh.
- `POST /api/auth/logout` invalidates the token.
- Every project returned by the API carries `my_role`: the caller's role on it (`bu_head`, `lead` or `engineer`).
