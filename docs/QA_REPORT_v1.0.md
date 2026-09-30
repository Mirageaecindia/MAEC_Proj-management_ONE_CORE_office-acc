# MAEC ProManage v1.0: test and code-quality report

Date: 2026-09-29. Code reviewed: `main` at commit `438da47`.
Scope: the whole application (backend, frontend, database), reviewed and tested for the v1.0 release.

## 1. Summary

| Area | Result |
|---|---|
| Backend tests | **264 / 264 passed** (32 files), run against a fresh migrated SQLite database with SharePoint disabled |
| Frontend tests | **62 / 62 passed** (11 files, Vitest + Testing Library) |
| Lint | Backend `ruff check` and `ruff format`: clean. Frontend `eslint`: **0 errors, 0 warnings** (16 warnings cleared in this pass) |
| Build | `vite build` succeeds; the WBS Excel template ships in the build |
| Migrations | 8 revisions; a test builds a fresh database from them and checks it matches the models exactly |
| Fixes in this pass | 12 defects found and fixed (§2); none open in the code that was reviewed |

**Release recommendation.** The code is in good shape for a v1.0 pilot with internal users, once the go-live checklist in §6 is done. Update 2026-09-30: H1 (hours over 8 a day) is built, with the visit rule and the unattended flag. H2 (corrections) was dropped by decision: hours stay on the subtask they were logged on, rejected hours can be approved again by a lead of the project within 7 days, and switching subtasks is one step. A manual walk-through of the timesheet flow is still to be done. Two security items (S1 rotate the Azure secret, S2 purge the secret and the HR file from git history) must be done before the repository or the app is exposed beyond the team.

## 2. Defects found and fixed in this pass

| # | Where | Defect | Fix | Test |
|---|---|---|---|---|
| 1 | WBS Structure (frontend) | Subtask hours were capped at 4; the form message said 8 but the check still said 4 | Limit is 1–8 h everywhere (backend rule, form, docs) | `test_wbs_subtask_rules` (14) |
| 2 | Every disabled button | Disabled buttons used the "wait" cursor, so the finished **Approved** state on Resource Booking looked like it was loading | Disabled actions show "not allowed"; a finished state keeps the normal cursor | visual |
| 3 | WBS Structure | Long task names ran over the next column | Fixed column widths; names wrap inside their column | visual |
| 4 | WBS Structure | The whole WBS table (hundreds of rows) was reloaded every 5 seconds per open tab | Refresh on tab focus; every action reloads anyway | – |
| 5 | Backend `wbs-structure` | ~3 queries per node (engineer, parent, level): 1,500 queries for a 500-node project | Two lookups for any number of nodes | `test_query_counts` |
| 6 | Backend bookings, timeline, timeline logs | One or two queries per booking / per task | Batched lookups | `test_query_counts` |
| 7 | Backend booking create/update | Untyped `dict` payload: a non-numeric value gave a 500 | Typed `ResourceBookingIn` / `ResourceBookingUpdate` (422 with the field) | existing suites |
| 8 | Backend WBS CSV upload | A non-numeric parent id, engineer id or hours gave a 500 | Reported with the row number (422) | `test_wbs_outline` |
| 9 | Resource Booking | A booking with no start date passed validation with a misleading message | Both dates required, clear message | – |
| 10 | Engineer dashboard | Polled every 15 s | Once a minute, plus on focus | – |
| 11 | Timeline, Resource Booking, Weekly Logs, dashboards | Loader functions were left out of effect dependencies (stale closures after a role or token change); per-render arrays in memo dependencies | `useCallback` with real dependencies; memoised arrays; clock value instead of a "tick" counter | lint (0 warnings) |
| 12 | WBS upload | The company's breakdown sheet leaves the first two phase blocks unnamed and was refused | Unnamed merged blocks take the phase by position | `test_wbs_outline` |

Earlier in the same release cycle (28 Sep) the review also removed a per-render loop in Task Details tests, fixed the stale "leads a project" flag after a lead assignment, and made the Timeline test independent of the real date.

## 3. Backend

### 3.1 Structure
- FastAPI + SQLAlchemy 2 + Pydantic 2 + Alembic. Two halves: `backend/app/` (auth, BU Head, tracking, hours review: 25 endpoints in routers → services → repositories) and `backend/main.py` (the Lead/Engineer endpoints: 30 endpoints, 2,312 lines, importing the shared helpers from `app/`). `tests/test_route_ownership.py` guards that nothing in `app/` is re-added to `main.py`.
- Services raise domain errors (`app/core/errors.py`), mapped to 400/401/403/404/409/429/502 by one handler. Timestamps are UTC.
- Sessions: bearer tokens in `login_sessions`, 12 h TTL, 5 failed logins lock a username for 15 min.

### 3.2 Business rules verified by tests
- **Roles:** BU Head or engineer accounts; lead is a role on a project (`project_role`). A person can lead one project and work on another with one login; every lead action requires the lead role on that project.
- **Leads:** chosen per project with a period and %, stored as approved `role="lead"` bookings; capacity = the busiest day across all active projects ≤ 100% (`peak_allocation`); a lead can't be booked as an engineer on their project; one person per slot.
- **Hours:** only Login/Logout on subtasks; Logout − Login, paused by a 5-minute heartbeat silence, resumed on the same subtask, 8 h/day cap; one row per subtask, engineer and day; approved per finished day by the task's lead, else the BU Head (leads' own hours, tasks without an active lead); transitions pending → approved/rejected, approved → rejected with a reason (audited), rejected → approved only within 7 days by a lead of the project or the BU Head, with a reason (audited); a reviewed day never changes.
- **Governance:** usage = approved hours; alert at the threshold, automatic lock at 100% of target + approved extensions; a manual stop is never lifted automatically; nobody approves hours while locked; an approved extension that leaves usage at or above 100% keeps the lock.
- **Projects:** unique code; edit audited field by field; replacing a lead moves their WBS nodes; archive = read-only for everyone (flush-time guard), hidden from leads and engineers, ended tracking sessions banked; delete only without history.
- **Access:** engineers see a project only after the BU Head approves their booking; leads see their projects; archived projects are hidden.

### 3.3 Algorithms reviewed
| Algorithm | Where | Complexity / notes |
|---|---|---|
| Capacity: busiest day of overlapping bookings | `app/domain/allocation.py` `peak_allocation` | Sweep line over start/end events, O(n log n); undated side = open-ended; tested with the backlog's counter-example |
| Planned hours of a booking | `planned_hours` | Weekdays × 8 × %, O(days) |
| Who reviews whose hours | `app/services/hours_review.py` `HoursReview` | Two queries per project, then O(1) per row |
| Tracking: heartbeat grace, resume, daily cap, two-tab race | `app/services/tracking.py` | Optimistic locking (`version_id`) so a resume is banked once |
| Governance level, monthly normal/exceeded split | `app/domain/governance.py` | Pure functions, O(months) |
| Planned hours spread over months | `app/domain/calendar.py` | Even per calendar month (N10 asks for working-day weighting: open) |
| WBS outline parsing (bold = task) | `app/services/wbs_outline.py` | Reads `xl/styles.xml` once; O(rows) |
| Approved hours for usage | `WorkRepository.approved_hours` | One SQL `SUM` |

### 3.4 Edge cases covered by tests
Login of an inactive account; five failed logins; expired session; a session from another tab; heartbeat after the laptop was off; Logout after a gap; two tabs resuming at once; the daily cap; Login on a locked project, on someone else's subtask, on a main task; a day that isn't over; hours on a task with no lead or whose lead's period ended; the lead of a task who did part of it; bookings in different months vs overlapping; moving a booking's dates; the same person in two lead slots; a lead already booked as an engineer; an unknown phase, a subtask before any task, a bad number in the upload; re-uploading the same workbook; archiving with an open session and a pending extension; deleting a project with history; migrations from a database with old lead accounts and with old week decisions.

### 3.5 Code quality
- Layering is respected in `app/` (thin routers, services with rules, repositories with SQL, domain modules with pure functions). Each rule lives in one place: totals in `total_hours`, capacity in `peak_allocation`, reviewer in `HoursReview`, access in `project_role`.
- Over-engineering avoided: no ORM relationships or generic base classes were added; batching is done with plain dictionary lookups; the outline parser uses the standard library instead of a new dependency.
- **Debt, tracked in `docs/TODO.md`:** `main.py` is still a 2,312-line module with 30 endpoints (E1: move feature by feature when touched); dead tables `gantt_tasks` and `project_leads` (E7); no database foreign keys (E5); the header-based CSV import keeps a second parser alongside the outline import.

## 4. Frontend

### 4.1 Structure
- React 19 + Vite. `features/` (BU Head pages, SharePoint) and `components/`, `hooks/`, `api/` use one API client, TanStack Query and shared hooks; the Lead/Engineer pages under `pages/` are older and still call `fetch` directly (E2). Role-based routing and tabs come from `utils/access.js`; each page reads its role on the selected project from `project.my_role`.
- Tracking heartbeat runs app-wide once a minute per tab (by design: it is what pauses time when the laptop is off).

### 4.2 Pages reviewed
Login, Created Projects, Create/Edit Project, Executive Dashboard (BU Head and lead views), Work Summary, Resource Booking, WBS Structure, Task Details, Timeline & Logs, Engineer Weekly Logs, Engineer Performance Dashboard, SharePoint Mirror, header and notification bell. Every page's loaders, handlers and role gates were read; the defects found are in §2.

### 4.3 Test coverage
Form validation and payload mapping (Create/Edit Project), BU Head page smoke tests (projects, edit, dashboard, stop/resume, archive, work summary), Resource Booking reject with reason and the one-line table format, Task Details Login/Logout including the in-flight heartbeat race, Timeline per-day approval and bulk approval, Weekly Logs per-day review with a reason, the daily-hours helpers, the access rule, the API client and formatters.

### 4.4 Known limitations (open backlog)
W1 the BU Head's Timeline view is thin; W3 the Resource Booking page keeps its own 5-second notification poll; legacy pages use `window.confirm` for deletes; E2 legacy pages fetch directly instead of through hooks; E8 tokens are kept in `localStorage`.

## 5. Database

### 5.1 Connectivity
- One SQLAlchemy engine from `DATABASE_URL` (`app/core/config.py`); a session per request (`get_db`), always closed. Development: SQLite in WAL mode with `synchronous=NORMAL`. Deployment (`docker-compose.yml`): **Postgres 18** with `psycopg`, the API waits on the database health check, and migrations run at API start (`migrate(engine)`), which is safe with the single API process; with several processes, run `alembic upgrade head` as a deploy step.
- A database created before Alembic is refused with a clear message. The only databases that may be started are a fresh one or the laptop's migrated dev database.
- Not yet done: the full test suite has not been run against Postgres (go-live item E5). The SQL used is dialect-neutral (no SQLite-only functions), and migration 0007 uses portable correlated updates.

### 5.2 Tables (13 in use, 2 legacy)
| Table | Purpose | Key columns / constraints |
|---|---|---|
| `users` | Login accounts (`bu_head` / `engineer`) | unique-indexed `username`, `employee_id` → employees, `is_active` |
| `login_sessions` | Bearer tokens | indexed `token`, `user_id` |
| `employees` | HR roster (seeded from CSV; placeholders `L<id>` for converted lead accounts) | unique `employee_code` |
| `projects` | Project and commercial baseline | unique-indexed `project_code`; three lead slots (name + user id); governance fields; `archived_at` |
| `resource_bookings` | Engineer bookings and lead assignments | `role` (`engineer` / `lead`), `utilization_rate`, dates, `approval_status`; indexed by project, employee, role, status |
| `wbs_nodes` | Tasks and subtasks (2 levels) | `parent_id`, `phase`, assigned lead (user id) and engineer (employee id), dates, status |
| `wbs_node_history` | Status changes and comments | by node and project |
| `time_sessions` | Login/Logout sessions | `login_at`, `last_seen_at`, `last_active_at` (last visit), `logout_at`, `active_seconds`, `ended_by`, `version_id` (optimistic lock) |
| `time_log_entries` | One day's hours per subtask and engineer; outlives the subtask | **unique** (project, task, employee, work_date); `approval_status`, `reviewed_by/at`, `review_reason`; `task_name` kept when the subtask is deleted; `trimmed_hours` left out by "approve up to last visit"; `reviewed_by_user_id`, `reapproved_at` |
| `governance_actions` | Audit log (stop, resume, lock, extension decisions, edits, archive, hours taken back) | by project |
| `extension_requests` | Extra-hours requests and decisions | by project, requester, status |
| `notifications` | Per-role or per-user notifications | by recipient role / user / project |
| `alembic_version` | Migration head | – |
| `gantt_tasks`, `project_leads` | **Legacy, unused** (E7) | – |

### 5.3 Integrity notes
- Referential integrity is enforced in code (project delete removes children explicitly; the archive guard refuses writes at flush time). There are **no database foreign keys** yet (E5); adding them before Postgres goes live is recommended.
- Unique constraints cover the identities that matter (username, employee code, project code, one hours row per day).
- Migration chain 0001 → 0017 is verified by `tests/test_migrations.py` (fresh build equals the models) and by data migration tests for 0006 (lead accounts → engineers) and 0007 (week decisions → rows). 0008 drops the old weekly rows by design (test data only).

## 6. Go-live checklist (status)
- [ ] **S1** rotate the Azure client secret (needs Azure credentials).
- [ ] **S2** purge the HR CSV and the old secret from git history; both remotes (`origin`, `company`) must be force-pushed once; ask the one other clone owner to delete her clone.
- [x] **H1** hours over 8 a day are kept (flagged). **H2** corrections: dropped by decision 2026-09-30 (second look at rejected hours and one-step switching instead).
- [ ] **E5** run the full suite and `alembic upgrade head` against Postgres; add foreign keys.
- [ ] Map or delete the `L*` placeholder employees before the real HR roster is loaded.
- [ ] Give every existing project's leads a period and % (projects created before 28 Sep).
- [ ] Engineers keep MAEC open in a tab; exclude the site from Edge sleeping tabs / Chrome Memory Saver.
- [ ] Server `.env`, nightly `pg_dump` off the server, restore drill, SharePoint end-to-end test against the real tenant.
- [x] Test suites, lint and build green on the release commit (`438da47`).

## Appendix: test inventory
Backend (264 tests): projects (21), governance workflow (17), governance (15), resource approval (13), WBS subtask rules (11), project archive (11), engineer performance (11), auth (11), project edit (10), WBS outline upload (9), hours review (8), tracking (7), sessions (7), lead assignments (7), SharePoint mirror (6), oversight views (6), timezone (5), project roles (5), lead WBS access (5), work summary (4), WBS statuses (4), create_user (4), allocation (4), weekend hours (3), user deactivation (3), route ownership (3), resource gantt (3), migrations (3), backup (3), query counts (2), uploads (1), migration 0006 (1), plus 14 parametrised cases.

Frontend (62 tests): BU Head page smoke tests (14), Create Project form (11), Timeline & Logs (7), formatters (6), API client (5), daily-hours helpers (4), Task Details (4), Engineer Weekly Logs (4), folder tree (3), Resource Booking (3), access rule (1).
