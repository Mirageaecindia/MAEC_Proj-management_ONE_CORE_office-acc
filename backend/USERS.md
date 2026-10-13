# MAEC people: signing in, roles and profiles

Nobody signs in to Project Management itself. **MAEC One Core** (`auth.mirageaec.com`) does,
for every MAEC One app: it holds the accounts, passwords and seats. On every request this
app's backend asks Core who the browser is (`app/api/gate.py`), and maps the answer to the
person's profile here (`app/core/identity.py`).

There are two kinds of profile here, and one role on a project:

| Profile   | Sees / Can Do                                                            |
|-----------|--------------------------------------------------------------------------|
| `bu_head` | Projects, Create Project, Resource Booking, WBS Structure, Timeline & Logs, Executive Dashboard, Work Summary. Creates projects and chooses their leads, approves bookings and extension requests, approves the project leads' own hours. |
| `engineer`| WBS Structure, Timeline & Logs, Performance Dashboard. Works on assigned subtasks (Login/Logout records the hours) and submits their week. |
| **lead of a project** | Not a profile: the BU Head picks any engineer as a project's Electrical, Mechanical or BIM lead, with a period and a utilization %. On that project they book engineers, build the WBS, approve tasks and engineers' hours, and request extra hours. An engineer who leads any project also gets the Resource Booking and Executive Dashboard tabs. |

Core decides **who gets in** (a seat on Project Management). This app decides **what they
are here**: `bu_head` or `engineer` (`users.role`) and which projects they lead. Role and
identity never come from a URL, a client header or the browser's storage.

## Who is who

- The first time someone visits, their MAEC One account is linked to the profile whose
  username is their email (letter case and surrounding spaces ignored), by storing Core's id
  in `users.core_user_id`. After that the link alone is used: an email change in Core keeps it.
- Core never changes `users.id`, `employees.id`, `full_name` or `role` here.
- Someone with a seat but no profile is answered 403 `PROFILE_NOT_SET_UP` and told to ask a
  Business Head. They are not created automatically: an employee record needs the HR
  employee code and the job role, which Core doesn't know.
- A profile deactivated here (before the move to MAEC One) is refused, whatever Core says.

## Profiles (BU Head, in the app)

On Projects → People the BU Head:
- imports engineers from the HR export, or adds one person (employee code, name, work email,
  job role). Each gets an engineer profile named by their work email, linked to an employee
  record; no password. Each still needs a seat in MAEC One;
- corrects an engineer's name or job role (not the email: that is who they are in MAEC One);
- makes an engineer who is on no live project a BU Head, or takes the role back from a
  promoted BU Head, confirmed in a dialog.

Resetting passwords, deactivating and deleting are done in MAEC One. See
`app/services/provisioning.py`.

## API

- `GET /api/auth/me` → the profile: `id`, `username`, `full_name`, `role`, `employee_id`,
  `leads_projects` (whether the person leads at least one project) and `core_url` (MAEC One as
  a browser reaches it: Sign out and Change password link there).
- Every request carries MAEC One's cookie (`maec_one_session`, set for the parent domain); the
  browser sends it by itself. No token is kept in the browser.
- Not signed in at MAEC One: 401 `{reason, login_url}`; the frontend sends the window to
  `login_url` once. No seat: 403 `{reason: "no_access", login_url}`. MAEC One unreachable: 503.
- Every project returned by the API carries `my_role`: the caller's role on it (`bu_head`, `lead` or `engineer`).

## Kept in the database for now

`users.password_hash`, `users.must_change_password` and the `login_sessions` table are no
longer read or written. They stay until a separate migration after go-live removes them.
Profiles created since the move carry no password (`password_hash` is `!`).
