# MAEC ProManage: prioritised to-do list

Last updated: 2026-09-28 (Docker deployment setup, E9). Sajjad is the only person pushing to `main`. **The app is not deployed yet.** The target is a netcup VPS in Vienna running Docker Compose ([DEPLOYMENT.md](DEPLOYMENT.md)); see the go-live checklist. All databases today hold test data. Owner:
Sajjad, who now owns all three roles (BU Head, Lead, Engineer) plus the
SharePoint integration.

This list combines three sources:
- the open roadmap items;
- two rounds of external code review (September 2026);
- known issues in the Lead and Engineer code.

Background for every item is in [PROJECT_GUIDE.md](PROJECT_GUIDE.md).

**How to read it**
- Priority groups:
  - **P0** is security and data, fixed now.
  - **P1** makes the numbers correct and closes gaps in control.
  - **P2** completes the workflows.
  - **P3** is architecture and technical debt.
  - **P4** is SharePoint, which comes last by decision.
- Size: **S** is under half a day, **M** is 1–3 days, **L** is a week or more.
- ⚖️ means a product decision is still open. These are in the "Open decisions" section.
- Items with IDs from the old list keep those IDs in brackets, e.g. (P1 #7).

---

## Working rules

1. **Every schema change is an Alembic revision:** change `models.py`, run `alembic revision --autogenerate -m "..."` in `backend/`, review the generated file, commit both. `tests/test_migrations.py` fails if models and migrations disagree.
2. **Lead and Engineer code is moved into `app/` when it is first touched,** but only for changes of size **M or larger**. Before changing it:
   - write characterization tests for the endpoint's current behaviour;
   - move it into `app/` (routers → services → repositories);
   - then make the change.
3. **P0 fixes and S-sized fixes are patched in place** in `main.py` with a test (e.g. S3, S4, S5). They must not turn into refactors.
4. The guard test `test_route_ownership.py` stays: code that lives in `app/` is never re-added to `main.py`.
5. New business rules come with tests. Run the full check set before every push (see CLAUDE.md).

---

## Decided (do not reopen without a reason)

| Topic | Decision | Recorded in |
|---|---|---|
| Governance baseline | BU Head target effort hours + approved extension hours | guide §7.7 |
| Lock scope | **Whole project.** The per-discipline breakdown is informational only and never triggers anything | guide §7.7 |
| Threshold behaviour | Alert at the threshold; automatic lock at 100% of the baseline; an approved extension or a Resume unlocks | guide §7.7 |
| Usage | **Approved hours only**: a row the Lead approved, or a row in a week the Lead approved. Pending hours don't count; rejected hours never count | guide §7.7 |
| D1: how hours are recorded | **Subtask Login/Logout only; no manual timesheet** (manager, 2026-09-27). Engineers create a subtask each day (estimate up to 4 h, work may run over) and log in and out on it. Worked time = Logout − Login, idle included; nothing logs out automatically; time with the laptop off is not counted and the session resumes by itself. Logout banks into the weekly row; the Lead approves as before | guide §7.4 |
| D2: calendar and time zone | Per **person**, through their office: working-week pattern + time zone. The project calendar only matters for planned hours | this file |
| C7: task assignment | Leads may assign WBS tasks after booking; the engineer sees them once the booking is approved. Safeguards in C7 | this file |
| D8: while locked | **Logging is allowed** (flagged as over-baseline); **approval is blocked**; Leads may still **reject**. Rules in N14 | this file |
| Warning on approved + pending | When approved + pending hours reach the alert threshold: a **warning only**, never a lock | this file (N13) |
| Leads per project | **Everyone is an engineer; the BU Head picks any engineer as a project's Electrical, Mechanical or BIM lead**, with start date, end date and utilization % that count toward the same 100% cap as bookings. A lead can do subtasks (Login/Logout) but **can't book themselves** on a project they lead. **The BU Head approves a lead's own hours.** An engineer who leads any project also sees the Resource Booking page | L1 |

---

## P0: Security and data (do now, in this order)

| ID | Task | Why | Where | Size |
|---|---|---|---|---|
| S1 | **Rotate the Azure client secret.** Update `.env` on every machine. Check whether the GitHub repo is private, **and whether it was ever public** | The secret leaked in git history (commit `1b40874`) | Azure portal, `.env`, GitHub settings | S |
| S2 | **Purge the HR CSV and the old secret from git history** with `git filter-repo`, **right after S1**. Force-push once (the only planned exception to "never force-push main"), then everyone re-clones. If the repo was ever public, assume both were copied and **inform whoever handles HR / data protection**: the CSV is employee personal data and India's DPDP Act applies | Every week it waits, the data sits in more clones | whole repo | M |
| S3 | ✅ **Done.** Project-access checks added to Lead WBS node create, **update** and delete. The unused legacy `gantt_tasks` endpoints (`GET /api/projects/{id}/wbs-tasks`, `PUT /api/wbs-tasks/{id}`), which had no access check, were removed. Advance-status was already limited to nodes in the Lead's scope | A Lead could change WBS data on projects they weren't allocated to | `main.py`, `tests/test_lead_wbs_access.py` | S |
| S4 | ✅ **Done, then superseded (D1).** The server now computes worked time from its own clock (Logout − Login), so the browser reports no seconds at all | Anyone calling the API could claim 8 h a minute after starting | `app/services/tracking.py`, `tests/test_tracking.py` | S |
| S5 | ✅ **Done.** The public `/uploads` mount was removed: nothing was ever stored there. The authenticated, project-checked download endpoint is built with the first real files (C3, SOW upload). A test fails if any public mount comes back | Anyone with a file URL could have downloaded it | `main.py`, `tests/test_uploads.py`, `CLAUDE.md` | S |
| S6 | ✅ **Done.** `users.is_active` (the last change via `schema_upgrades.py`). Login and existing sessions refuse inactive users (generic error); inactive leads are hidden from the Create Project dropdowns and can't be assigned; `create_user.py --deactivate / --activate` (deactivating ends their sessions at once) | A leaver could only be removed by editing the database | `models.py`, `app/core/security.py`, `app/services/auth.py`, `app/repositories/users.py`, `create_user.py`, `tests/test_user_deactivation.py` | S |
| S7 | ✅ **Script done and restore-tested.** `backup_db.py` takes a consistent snapshot via the SQLite backup API (safe while running) and keeps the newest 14. Drill run on 2026-09-26: back up the live DB, restore it to a copy, start the real server on it, log in, load projects and a dashboard: passed. **Still to do by hand:** (1) choose an **off-machine** target (another drive or a restricted OneDrive folder; the backups contain personal data, so only you should have access) and pass it with `--dir`; (2) create the nightly scheduled task on the machine that holds the real database | Backups on the same disk die with it (disk failure, ransomware) | `backend/backup_db.py`, `tests/test_backup_db.py` | S |
| S8 | ✅ **Done.** CLAUDE.md, CONTRIBUTING.md, USERS.md and the guide describe the single owner, the working rules and the new commands | Rules must match reality | docs | S |

---

## P1: Correct numbers and gaps in control

### P1a: Numbers the BU Head can trust

| ID | Task | Why | Where | Size |
|---|---|---|---|---|
| N1 | ✅ **Done 2026-09-28 (D1 changed).** No timesheet screen: hours come from subtask Login/Logout. The idle and hidden-tab pause was removed; worked time = Logout − Login, paused while the laptop is off (heartbeat), resumed by itself; the manual `POST /timesheet-entries` endpoint was removed. Tracking moved to `app/` | The browser tracker recorded about zero while engineers worked in Revit/AutoCAD | `app/services/tracking.py`, `app/api/routers/engineer/tracking.py`, `hooks/useTracking.js`, `TaskDetailsPage.jsx`, migration `0004` | M |
| N2 | ✅ **Done.** Hours on all seven days are accepted and counted: row totals, approved usage (SQL), monthly buckets, "has tracked hours" filters, the Timeline & Logs weekly total, and tracking no longer discards weekend sessions. Planned-hours maths stays Mon–Fri until N3 | KSA works Sun–Thu, Indian offices often Saturday; those hours were silently dropped | `app/domain/timesheets.py`, `app/repositories/work.py`, `main.py`, `TimelineLogsPage.jsx`, `tests/test_weekend_hours.py` | S |
| N3 | **Office field (prerequisite for D2):** an `offices` table (week pattern, time zone) and `employees.office_id`. **Default everyone to one office now** so nothing breaks. Then use it for the daily cap and day boundaries, and later for planned-hours maths | The 8 h cap and "today" use the server date; IST and GST days split differently | new table + Alembic, `main.py` tracking, `app/domain/calendar.py` | M |
| N4 | **Real earned value:** EV = estimated hours of **finished** WBS tasks; PV = planned-to-date from the WBS dates. Show SPI = EV / PV and CPI = EV / approved hours. Replaces the current "SPI" (approved ÷ WBS hours), which isn't SPI | The only honest progress figure. Needs N8 first | `app/services/metrics.py`, `GovernanceSummaryCards.jsx` | M |
| N5 | ✅ **Done.** Past the contract value, budget burn reports `over_budget` (the overrun) and `remaining` never goes negative; the dashboard card turns red with "Over budget by … (N% of contract)". The bar was already capped at 100% | Misleading figure | `app/services/metrics.py`, `GovernanceSummaryCards.jsx` | S |
| N6 | ⚖️ **Rate card:** cost = hours × the rate of whoever logged them. It needs **rate history** (`effective_from`, so changing a rate doesn't rewrite past burn) and **currency conversion** (contracts are in AED/SAR/INR/USD; rates are probably INR). Also fill the resource summary's hard-coded zeros (roadmap 7.4) | Budget burn and resourcing are hours ratios, not cost | new `rates` / `fx_rates` tables, `metrics.py`, `booking_approval.py` | M |
| N7 | **Map "discipline" to Electrical / Mechanical / BIM** instead of the job title (P1 #13). Remove the "exceptions / exceeded" wording from the per-discipline view | It groups by designation, and "exceeded" suggests it triggers something (it doesn't, see Decided) | `metrics.py`, mapping table | S–M |
| N8 | ✅ **Done.** One status vocabulary (`app/domain/wbs.py`): tasks To Do → In-Progress → Submitted for Approval → Approved, subtasks To Do → In-Progress → Done. A guard on `WbsNode.deliverable_status` normalizes legacy names on every write (form, edit, Excel upload, API); migration `0002` converted existing rows; one `is_finished` rule for Work Summary, Timeline and both Engineer dashboards; the Lead's WBS form no longer sends "Not Started". Work Summary completion and engineer progress now show real values | Completion showed 0% | `app/domain/wbs.py`, `models.py`, `migrations/versions/0002_*`, `app/services/work_summary.py`, `main.py`, `WbsStructurePage.jsx`, `tests/test_wbs_statuses.py` | S |
| N9 | **One timesheet approval route:** weekly, at main-task level (fits D1). Per-row reject stays for corrections. Migrate the data. The Engineer dashboard reuses `effective_status` instead of its own copy, and so must `project_timeline_logs` (Lead/Engineer Timeline & Logs) and the older `engineer_performance` endpoint, which today count by row status only, so week-approved hours still show as pending there. **Allowed review transitions** (today the per-row review ignores the old status, so a Lead can approve hours and later un-approve them to hold usage under the threshold or 100%, delaying the alert and the lock, and flip rejected → approved with no trace): pending → approved or rejected (normal); approved → rejected only with a **reason and an audit entry**, shown on the BU Head's dashboard; rejected → approved **not allowed** (the engineer re-submits) | Two routes double the rules and the bugs | `main.py` weekly-hours + time-log review, Engineer dashboard | M |
| N10 | **Monthly chart: spread planned hours by working days**, not evenly per calendar month | A task running 28 Sep to 31 Oct puts half its hours in September | `app/domain/calendar.py` | S |
| N11 | **Booking planned hours respect the booking %** (20% means 1.6 h a day, not 8) | Resourcing figures are overstated | `main.py` `estimated_hours_from_dates` / booking create and edit | S |
| N12 | ✅ **Done 2026-09-28.** The allocation cap is checked per day: the busiest day in the new booking's dates, across all active projects, stays at or below 100% (a missing date is open-ended). Used by Lead bookings and, next, lead assignments | Today it adds up every booking regardless of dates | `app/domain/allocation.py`, `app/services/allocation.py`, `tests/test_allocation.py` | S |
| N13 | **Governance visibility:** (1) pending hours as their own prominent figure; (2) **approval lag**, the age of the oldest pending entry; (3) a **warning-only** alert when approved + pending reach the threshold; (4) an "over-baseline, awaiting extension" figure (N14) | Without these the BU Head can't tell "under budget" from "the Lead hasn't approved anything" | `metrics.py`, `governance_monitor.py`, dashboard cards | M |
| N14 | **Lock behaviour (D8).** Rules: (a) while locked, engineers can log and track; those hours are flagged **over-baseline** and shown in the N13(4) figure; (b) approval (row and week) is blocked while locked; **reject stays allowed** (was C9), and a rejection never reopens the project (already enforced: an automatic lock reopens only when the BU Head raises the baseline); (c) after Resume or an extension, approving backlogged hours re-runs the lock check, e.g. a 10 h extension followed by 60 h of backlog approvals must lock again; (d) ✅ **done 2026-09-26:** an approved extension that leaves usage at or above 100% keeps the lock, and the Lead is told why. (e) **Resuming at or above 100%** is today an open-ended bypass (the project never re-locks): require a **reason** (audited), show a lasting "running over baseline, unlocked" state on the dashboard (and on W4), and decide whether to re-arm the lock at a new ceiling (usage at resume + X%). (f) **Update the Stop confirmation text** (C8) when this ships: it says engineers can't log or track hours, which stops being true once logging is allowed while locked. Tests for every rule | Blocking logging hides work instead of stopping it; rules (c) and (d) stop the lock being bypassed | `main.py` logging and review endpoints (move per rule 2), `app/services/governance.py` `decide_extension`, `governance_monitor.py` | M |

### P1b: BU Head control and project lifecycle

| ID | Task | Why | Where | Size |
|---|---|---|---|---|
| C1 | ✅ **Done.** `projects.archived_at` (migration `0003`); `POST /projects/{id}/archive` and `/unarchive` (BU Head, audited, Leads notified). Archived = **read-only for everyone** (a flush-level guard refuses any write of its data, whatever the endpoint), hidden from Leads and Engineers (all their lists, dashboards, Gantt and endpoints), out of the allocation cap and governance alerts. Archiving ends active tracking (time banked) and cancels a pending extension request; unarchive restores the lock as it was. The BU Head sees archived projects behind a filter and can open their dashboard (read-only). Hard delete only for a project with no history; otherwise archive | Delete wiped the governance audit log | `app/services/archive_guard.py`, `app/services/projects.py`, `app/services/access.py`, `main.py` allocation cap, `CreatedProjectsPage.jsx`, `useProjectSelection.js`, `tests/test_project_archive.py` | M |
| C2 | ✅ **Done.** `PUT /api/projects/{id}` (BU Head) and an Edit page (the Create form, filled in; no SharePoint section). Every changed field is audited before → after; project code stays unique; a currency change needs an explicit confirmation (dialog) because amounts are relabelled, not converted; replacing a lead moves their WBS nodes to the new lead (old lead loses access, both are notified); archived projects can't be edited. **Lock re-check both ways:** lowering the target past 100% locks; raising it reopens an **automatic** lock (the monitor now does this for any drop back under 100%); a manual stop stays | A typo in the contract value could only be fixed by deleting the project | `app/services/projects.py`, `app/services/governance_monitor.py`, `CreateProjectPage.jsx`, `tests/test_project_edit.py` | M |
| C3 | **Create Project: add end date, scope, project type and SOW upload** (P1 #9); the SOW goes through the authenticated file endpoint (S5). Show the SharePoint failure message, which is lost on redirect today | Missing baseline data; contracts must not be public | `createProjectForm.js`, `services/projects.py` | M |
| C4 | ✅ **Done.** Reject button next to Approve on the Resource Booking page (BU Head, only while a submission is pending), with a required reason in a confirmation dialog; the reason goes into the Leads' notification. A persistent booking audit trail is C12 | The BU Head could approve but not send back | `app/services/booking_approval.py`, `resourcing.py`, `ResourceBookingPage.jsx`, `hooks/useResourceBookings.js`, tests | S |
| C5 | **Approve or reject bookings per engineer**, not all-or-nothing | You can't approve three engineers and reject one | `booking_approval.py`, `main.py` submit, UI | M |
| C6 | **Editing an approved booking creates a pending change; the last approved version stays active** (dates, %, access) until the BU Head approves the change | Otherwise the engineer loses project access mid-project, and today edits bypass approval entirely | `models.py` (pending-change fields), `main.py` booking update, `booking_approval.py` | M |
| C7 | **Assignment vs access (decided):** Leads assign after booking; the engineer sees tasks once the booking is approved. Safeguards: (a) a **badge on WBS tasks** saying "assigned engineer not approved"; (b) when the BU Head rejects or reduces a booking, the Lead is told **which tasks are affected**; (c) removing a booking can't leave tasks assigned silently | Today tasks can end up with someone who will never see them | `main.py` WBS + booking delete, `booking_approval.py` notification, `WbsStructurePage.jsx` | S–M |
| C8 | ✅ **Done.** Stop and Resume each open a confirmation dialog that says what happens (Stop locks logging, tracking and approvals and notifies the Leads; Resume reopens them). Resume warns when usage is at or above 100% that the project won't lock again automatically | Prevents clicking by accident | `GovernanceControls.jsx`, `pages.smoke.test.jsx` | S |
| C9 | *(merged into N14 rule b)* | | | |
| C10 | ✅ **Done** (with S3). Deleting a WBS node also deletes its `time_sessions` | Left orphan rows | `main.py` WBS delete | S |
| C11 | ✅ **Obsolete (D1).** There is no manual entry; Logout creates the week's row when needed | – | – | – |
| C13 | **WBS edit dialog must respect the status flow.** Today a Lead can set any status directly (Approved, Done), skipping the engineer's steps and the dedicated approve action. Limit the edit dialog to non-status fields, or to transitions the flow allows | Workflow bypass | `WbsStructurePage.jsx`, `main.py` `update_wbs_node` | S |
| C12 | **Audit log for booking approvals, rejections and edits** (who, when, before/after) | The governance log doesn't cover resourcing decisions | `booking_approval.py`, `main.py` booking edit, new audit table or `governance_actions` | S–M |

---

## P2: Workflows and visibility

| ID | Task | Why | Where | Size |
|---|---|---|---|---|
| L1 | **Leads are chosen per project from all engineers** (decided 2026-09-28, see *Decided*). Stages: (1) ✅ N12 date-aware capacity; (2) ✅ **done 2026-09-28:** lead/engineer are roles on a project (`project_role`); an engineer set as a project lead has lead powers there only, a lead booked elsewhere works there as an engineer, leads do subtasks with Login/Logout; (3) ✅ **done 2026-09-28:** each lead slot has start/end/% and becomes an approved `role="lead"` booking (capacity, timeline, WBS assignee list); dropdowns list everyone with an employee record; a lead can't be booked as an engineer on their project; the BU Head approves leads' hours (`require_hours_reviewer`); (4) frontend: menus and pages follow the role on the selected project (Resource Booking for any engineer who leads a project), lead accounts converted to engineer accounts, BU Head approval UI for leads' hours, `Role.LEAD` removed | One person leads one project and works on another | `app/services/access.py`, `main.py`, `app/services/projects.py`, `CreateProjectPage.jsx`, `App.jsx` | L |
| W1 | **BU Head Timeline view** (P1 #15): Timeline & Logs is empty for the BU Head, the Gantt is hard-coded to Sep–Dec 2026, and the Submission phase is missing | The BU Head has no schedule view | `TimelineLogsPage.jsx`, timeline endpoints | M |
| W2 | **BU Head Weekly Logs view** (P1 #16), read-only across all projects. **Also decide:** archiving hides a project from its Engineers, including their own past timesheets and hours. If hours ever feed appraisals, Engineers need read-only access to their own history in archived projects | The BU Head can't see timesheets | new page + endpoint | M |
| W3 | **One notification system:** move the Resource Booking page's own 5 s-polling banner to the header bell | Duplicate code and polling load | `ResourceBookingPage.jsx`, `NotificationBell.jsx` | S |
| W4 | **Portfolio dashboard:** all projects with level, burn, locks and approval lag | The BU Head's home screen | new page + aggregate endpoint | L |
| W5 | **Exports** (CSV/PDF) of the dashboard, Work Summary and timesheets | Reporting upward | export endpoints | M |
| W6 | **User management page:** create users, set discipline and office, reset password, deactivate (the CLI covers deactivation until then via S6). **Deactivating must list the person's bookings and WBS assignments for reassignment**, so a leaver's tasks don't sit orphaned (see C7) | Admin tasks without a terminal | new page + endpoints | M |

---

## P3: Architecture and technical debt

| ID | Task | Why | Where | Size |
|---|---|---|---|---|
| E4 | ✅ **Done.** Alembic with a baseline revision `0001` generated from the models; `migrate(engine)` runs at startup. A database created before Alembic is adopted automatically, once per machine: the old patches are replayed, missing indexes created, the schema **compared with the models** (a missing table or column stops startup; smaller differences are logged), then stamped. Dry run on a copy of the real database: adopted, 6 users and 4 projects intact, 5 missing indexes created. Adoption also fills NULLs and enforces NOT NULL on the five columns the old patches left nullable (lock threshold and lock flag included), so the adopted schema matches the baseline; only 2 type notes remain (see E5). The ~270 lines of `ALTER TABLE` code left `main.py` and `schema_upgrades.py` is gone. Adoption code (`app/core/legacy_schema.py`) removed with C1 once the only pre-Alembic dev database had been adopted; `migrate()` now refuses a pre-Alembic database with instructions. **Later:** with Postgres or several workers (E5), run `alembic upgrade head` as a deploy step instead of at startup | Adding schema at import time won't survive a production database | `backend/alembic.ini`, `backend/migrations/`, `app/core/migrations.py`, `app/core/legacy_schema.py`, `tests/test_migrations.py` | M |
| E1 | **Move Lead/Engineer endpoints into `app/`**, incrementally, under working rule 2 (M+ changes only). Extend the guard test as each feature moves | `main.py` is about 2,800 lines | `backend/main.py` → `backend/app/` | L (spread out) |
| E2 | **Migrate the Lead, Engineer and shared pages** to `features/` + `hooks/` + `api/` with no direct `fetch`, on first M+ change. `ResourceBookingPage` first | Same standard as the BU Head pages | `frontend/src/pages/` | L (spread out) |
| E3 | ✅ **Done.** `npm run lint` has 0 errors (unused imports, state and functions removed in `WbsStructurePage.jsx`, `pages/lead/ExecutiveDashboardPage.jsx`, `EngineerPerformanceDashboardPage.jsx`). 19 older warnings remain (hook dependencies, fast refresh) | `npm run lint` failed | those files | S |
| E5 | **Postgres decided:** the Docker deployment uses Postgres 18 (`psycopg`); the full suite and `alembic check` pass on it (`TEST_DATABASE_URL`, see DEPLOYMENT.md). **Still open:** foreign keys, indexes. Also align two harmless type differences in adopted dev databases: `projects.timesheets_soft_locked` INTEGER vs BOOLEAN, `wbs_nodes.deliverable_status` VARCHAR(60) vs (40) | Production-grade database | `models.py`, config | M |
| E6 | **Performance:** SQL aggregates instead of per-row queries; less polling | Scales badly | `main.py`, pages | M |
| E7 | **Delete dead code:** the `gantt_tasks` table (its endpoints were removed in S3), `project_leads`, the legacy `request-extension` endpoint, `leads_loader.py`, `temp_*.py`, `App.css`, and the unused `recharts` dependency | Noise | various | S |
| E8 | **Tokens in httpOnly cookies** instead of `localStorage` | XSS could steal tokens | `security.py`, `api/client.js`, `AuthContext.jsx` | M |
| E9 | **Production setup.** ✅ Docker Compose: a Caddy container serves the built frontend on ports 80/443 with automatic HTTPS and proxies `/api` to the API container; Postgres in its own container; runbook in `docs/DEPLOYMENT.md`. **Still open:** structured logging, error monitoring | Deployment | `docker-compose.yml`, Dockerfiles | M |

---

## P4: SharePoint (last, by decision)

It has never provisioned successfully, so treat it as unbuilt, not buggy.

| ID | Task | Why | Size |
|---|---|---|---|
| SP1 | Ask IT for **`Sites.Selected`** instead of `Sites.ReadWrite.All` (after S1) | Least privilege | S |
| SP2 | **Name folders by project code** (unique), not project name | `conflictBehavior: rename` silently creates "Name 1" | S |
| SP3 | **Store driveItem IDs**, not URLs | Renames break URLs | S |
| SP4 | **Background provisioning with retry**, and a provisioning status on the project | Create Project mustn't depend on Graph | M |
| SP5 | **Lazy mirror including subfolder files** | Only root files today | M |
| SP6 | **End-to-end test against the real tenant** | Never verified | S |

---

## Open decisions (⚖️)

| # | Question | Recommendation |
|---|---|---|
| D3 | Where do rates come from (N6)? Which currency conversion source and how often? | One rate per designation, with history, maintained by the BU Head; monthly FX rates entered by the BU Head |
| D9 | Should "Blocked" come back as a **flag** (like severity, with a reason), not a status? The status flow has no blocked state; N8 mapped legacy "Blocked" to To Do (no such rows existed) | A flag with a reason, shown on the WBS and the dashboards, if Leads need to report stuck work |
| D4 | The exact moment for the history rewrite (S2) | The first evening after S1 when everyone can push, then re-clone |

---

## Suggested order

1. **Blocked / later (P0):**
   - **S1:** blocked until Azure credentials are available. Do it before any SharePoint work.
   - **S2:** the only other clone is Subhika's; she has moved to another project and won't pull or push. Purge, then ask her to delete her clone.
   - **S7 (go-live item):** the database holds only test data today. Before real use, point `backup_db.py --dir` at an off-machine folder (external drive or restricted OneDrive) and schedule it nightly.
   - S3–S8, N14(d) and E4 are done.
2. **Sprint A:** E4 Alembic ✅, N2 7-day hours ✅, N8 statuses ✅, E3 lint ✅, C1 archive ✅, C2 edit ✅, C4 reject ✅, C8 confirmations ✅, N5 over-budget ✅, then N11, N12, N13.
3. **Sprint B (timesheets and lock):** N9 single approval route, N14 lock rules, C6, C7, C10, C12. Lead/Engineer features move into `app/` as they are touched.
4. **Sprint C (calendar and cost):** N3 office field, N4 EV/SPI/CPI, N6 rate card, N7 disciplines, N10, C3 (after S5), C5.
5. **Sprint D:** W1–W3.
6. **Then:** W4–W6, E5–E9, P4 SharePoint.

---

## Go-live checklist (before the first deployment)

Nothing here is urgent while the app is in development. All of it must be done before real users and real data arrive.

- [ ] **Hours:** engineers keep MAEC open in a browser tab while working, with the site excluded from Edge sleeping tabs / Chrome Memory Saver (user guide §5.2).
- [ ] **S1:** rotate the Azure client secret (needs Azure credentials).
- [ ] **S2:** purge the HR CSV and the old secret from git history; ask Subhika to delete her clone.
- [ ] **E5:** foreign keys, indexes. (Postgres is decided. Migrations run at API start, which is safe with the single API process; with several processes, run `alembic upgrade head` as a deploy step instead.)
- [ ] **E8:** tokens in httpOnly cookies. **E9:** structured logging, error monitoring (the Docker setup is done).
- [ ] **S7:** the nightly `pg_dump` cron from DEPLOYMENT.md §8, copied off the server, plus a restore drill on the production setup.
- [ ] **Server settings:** the root `.env` on the server only (`POSTGRES_PASSWORD`, `SITE_ADDRESS` = the real domain). CORS isn't needed: the web app and the API share one origin.
- [ ] **Clean start:** a fresh production database (no test projects or accounts), real accounts via `create_user.py`, and the legacy `project_leads` seed removed (E7). The only databases that may ever be started are a **fresh one** or **the laptop dev database after its migration**; never a pre-Alembic copy (Subhika's clone, an old backup), which `migrate()` refuses.
- [ ] **SP6:** SharePoint end-to-end test against the real tenant.
- [x] Delete `app/core/legacy_schema.py` (done with C1: the only pre-Alembic dev database was adopted; `migrate()` now refuses pre-Alembic databases).
- [ ] Full test suites, lint and build green on the release commit.

---

## Done (for reference)

| What | Commit |
|---|---|
| Phase 0 foundation: `.gitignore`, lint and format tools, pre-commit, characterization tests, CONTRIBUTING | earlier |
| Phase 1 backend: `app/` package for auth, BU Head and SharePoint; guard test and CLAUDE.md | `bc6ab46` and earlier |
| Phase 2 frontend: API client, TanStack Query, shared components, lazy routes, Vitest; BU Head pages migrated | earlier |
| `create_user.py --discipline` (Lead dropdowns work) | earlier |
| Session expiry (12 h), login throttling, Lead dashboard access check | `0e25947` |
| Only the allocated Lead can request extensions or submit bookings | `4ef95bc` |
| Governance: baseline = target + extensions, alert at threshold, auto-lock at 100%, resume, notifications, header bell | `095de9c` |
| Governance usage counts approved hours only (row or week approval); rejected hours excluded | `288c2ac` |
| `/api/server-date` returns real UTC | Subhika's UTC change |
| P0 S3–S8 and C10: Lead WBS access checks, tracked-time cap, no public uploads, user deactivation, SQLite backups, ownership docs, WBS delete cleans sessions | `cea05fc` |
| N14(d): an extension too small to get below 100% keeps the lock | `7e2c7eb` |
| E4: Alembic migrations (adoption of pre-Alembic dev databases, since removed) | `7bd72ba`, `ceb8f4a` |
| N2: hours on all seven days count | `23eec47` |
| N8 WBS statuses normalized; E3 lint errors fixed | `f682295`, `43f5b8e` |
| C1 project archive (read-only guard, access, cap, governance) | `3168bac`, `2b84106`, `787f9cb` |
| C2 edit project (audit, currency confirmation, lead handover, lock re-check both ways); reopen only on BU Head baseline changes | `4e35c5a`, `09e800f` |
| C4 booking reject with reason | `6ae6f90` |
| C8 Stop/Resume confirmations | `036ce06` |
| N5 over-budget state; N14 scope (e) resume above 100%, (f) Stop dialog text | this sprint |
