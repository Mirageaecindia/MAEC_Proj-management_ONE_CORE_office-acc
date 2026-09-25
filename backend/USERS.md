# MAEC Accounts & Login

MAEC now requires real login. There are three roles:

| Role      | Sees / Can Do                                                            |
|-----------|--------------------------------------------------------------------------|
| `bu_head` | Create Project, Resource Booking, WBS Structure, Timeline & Logs, Executive Dashboard. Creates projects, approves nothing in the timesheet flow (see below). |
| `lead`    | Resource Booking, WBS Structure, Timeline & Logs. Builds WBS, books resources, reviews/approves/rejects engineer timesheets for their assigned tasks. |
| `engineer`| Timeline & Logs (their own timesheets) and Engineer Performance Dashboard. Logs hours against tasks assigned to them. |

Role and identity come only from the logged-in session. There is no role-switcher
and no `?role=` URL override anymore.

## Creating accounts

Users are created manually — none are seeded at startup. From the `backend`
directory, run the CLI:

```
.venv\Scripts\python.exe create_user.py
```

It prompts for username, password, full name, and role. Engineers must be
linked to an existing `employees` row (that is what scopes their WBS tasks,
timesheets, and performance dashboard):

```
.venv\Scripts\python.exe create_user.py --username engineer --role engineer --employee-id 1 --full-name "Arjun Mehta"
```

```
.venv\Scripts\python.exe create_user.py --username lead --role lead --full-name "Anita Kumar" --discipline Electrical
```

Leads **must** have a discipline (`Electrical`, `Mechanical` or `BIM`). It
decides which Create Project dropdown they appear in, so create at least one
lead per discipline. To set the discipline of an existing lead:

```
.venv\Scripts\python.exe create_user.py --username lead --set-discipline Electrical
```

```
.venv\Scripts\python.exe create_user.py --username buhead --role bu_head --full-name "Test BU Head"
```

Notes:
- For `lead`, `full_name` **must** match the lead name used on WBS nodes
  (`assigned_lead`), e.g. "Anita Kumar", because lead scope is resolved by name.
- For `engineer`, `employee-id` must match the `id` in the `employees` table
  (Arjun Mehta = 1, Ravi Kumar = 2).
- Passwords are stored as PBKDF2-HMAC-SHA256 hashes (no plaintext, no external
  dependencies).
- Logging out deletes the session token server-side.

## Deactivating a leaver

Deactivation logs the person out everywhere at once and blocks future logins
(they see the normal "Invalid username or password"). Their data stays. An
inactive lead no longer appears in the Create Project dropdowns.

```
.venv\Scripts\python.exe create_user.py --username eng.arjun --deactivate
.venv\Scripts\python.exe create_user.py --username eng.arjun --activate
```

## Auth flow

- `POST /api/auth/login` → returns `token`, `role`, `full_name`, `engineer_id`.
- Every other endpoint requires `Authorization: Bearer <token>`.
- `GET /api/auth/me` restores the session on page refresh.
- `POST /api/auth/logout` invalidates the token.