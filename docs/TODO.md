# MAEC ProManage: prioritised to-do list

Last updated: 2026-09-26. Sajjad is the only person pushing to `main`. **The app is not deployed:** it will be deployed once, when the whole app is developed (see the go-live checklist). All databases today hold test data. Owner:
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
| D1: how hours are recorded | **Manual timesheet per main task, entered daily, submitted and approved weekly.** Engineers fill a weekly grid (seven days, today highlighted) as they go; each entry saves as pending; they submit the week; the Lead approves or rejects the week in one action (single rows can still be rejected). Subtasks track progress only. The tracker is downgraded (see N1). Tell the previous Engineer developer **before** the tracker changes | this file |
| D2: calendar and time zone | Per **person**, through their office: working-week pattern + time zone. The project calendar only matters for planned hours | this file |
| C7: task assignment | Leads may assign WBS tasks after booking; the engineer sees them once the booking is approved. Safeguards in C7 | this file |
| D8: while locked | **Logging is allowed** (flagged as over-baseline); **approval is blocked**; Leads may still **reject**. Rules in N14 | this file |
| Warning on approved + pending | When approved + pending hours reach the alert threshold: a **warning only**, never a lock | this file (N13) |

---

## P0: Security and data (do now, in this order)

| ID | Task | Why | Where | Size |
|---|---|---|---|---|
| S1 | **Rotate the Azure client secret.** Update `.env` on every machine. Check whether the GitHub repo is private, **and whether it was ever public** | The secret leaked in git history (commit `1b40874`) | Azure portal, `.env`, GitHub settings | S |
| S2 | **Purge the HR CSV and the old secret from git history** with `git filter-repo`, **right after S1**. Force-push once (the only planned exception to "never force-push main"), then everyone re-clones. If the repo was ever public, assume both were copied and **inform whoever handles HR / data protection**: the CSV is employee personal data and India's DPDP Act applies | Every week it waits, the data sits in more clones | whole repo | M |
| S3 | ✅ **Done.** Project-access checks added to Lead WBS node create, **update** and delete. The unused legacy `gantt_tasks` endpoints (`GET /api/projects/{id}/wbs-tasks`, `PUT /api/wbs-tasks/{id}`), which had no access check, were removed. Advance-status was already limited to nodes in the Lead's scope | A Lead could change WBS data on projects they weren't allocated to | `main.py`, `tests/test_lead_wbs_access.py` | S |
| S4 | ✅ **Done.** Tracked time is capped at the wall-clock time since `login_at` on session sync and end | Anyone calling the API could claim 8 h a minute after starting | `main.py` `cap_to_elapsed`, `tests/test_tracking_cap.py` | S |
| S5 | ✅ **Done.** The public `/uploads` mount was removed: nothing was ever stored there. The authenticated, project-checked download endpoint is built with the first real files (C3, SOW upload). A test fails if any public mount comes back | Anyone with a file URL could have downloaded it | `main.py`, `tests/test_uploads.py`, `CLAUDE.md` | S |
| S6 | ✅ **Done.** `users.is_active` (the last change via `schema_upgrades.py`). Login and existing sessions refuse inactive users (generic error); inactive leads are hidden from the Create Project dropdowns and can't be assigned; `create_user.py --deactivate / --activate` (deactivating ends their sessions at once) | A leaver could only be removed by editing the database | `models.py`, `app/core/security.py`, `app/services/auth.py`, `app/repositories/users.py`, `create_user.py`, `tests/test_user_deactivation.py` | S |
| S7 | ✅ **Script done and restore-tested.** `backup_db.py` takes a consistent snapshot via the SQLite backup API (safe while running) and keeps the newest 14. Drill run on 2026-09-26: back up the live DB, restore it to a copy, start the real server on it, log in, load projects and a dashboard: passed. **Still to do by hand:** (1) choose an **off-machine** target (another drive or a restricted OneDrive folder; the backups contain personal data, so only you should have access) and pass it with `--dir`; (2) create the nightly scheduled task on the machine that holds the real database | Backups on the same disk die with it (disk failure, ransomware) | `backend/backup_db.py`, `tests/test_backup_db.py` | S |
| S8 | ✅ **Done.** CLAUDE.md, CONTRIBUTING.md, USERS.md and the guide describe the single owner, the working rules and the new commands | Rules must match reality | docs | S |

---

## P1: Correct numbers and gaps in control

### P1a: Numbers the BU Head can trust

| ID | Task | Why | Where | Size |
|---|---|---|---|---|
| N1 | 🚧 **Go-live blocker. Timesheet entry screen (D1).** Until it ships, the only hour source is the tracker, which records close to zero, so every governance figure sits near 0. Build: a weekly grid with seven day columns (today highlighted, fill daily), add rows for the engineer's main tasks, entries save as pending, **Submit week**, and the week's approval state per row. Backend manual entry already exists (`POST /timesheet-entries`, main tasks only); **no page calls it today**. Then downgrade the tracker to an optional pre-fill or remove it (⚖️ D1a); tell the previous Engineer developer first | The browser tracker records about zero while engineers work in Revit/AutoCAD | new engineer page (`features/`), `main.py` `submit_time_log` (move to `app/` per rule 2), tracking endpoints, `TaskDetailsPage.jsx` | M–L |
| N2 | ✅ **Done.** Hours on all seven days are accepted and counted: row totals, approved usage (SQL), monthly buckets, "has tracked hours" filters, the Timeline & Logs weekly total, and tracking no longer discards weekend sessions. Planned-hours maths stays Mon–Fri until N3 | KSA works Sun–Thu, Indian offices often Saturday; those hours were silently dropped | `app/domain/timesheets.py`, `app/repositories/work.py`, `main.py`, `TimelineLogsPage.jsx`, `tests/test_weekend_hours.py` | S |
| N3 | **Office field (prerequisite for D2):** an `offices` table (week pattern, time zone) and `employees.office_id`. **Default everyone to one office now** so nothing breaks. Then use it for the daily cap and day boundaries, and later for planned-hours maths | The 8 h cap and "today" use the server date; IST and GST days split differently | new table + Alembic, `main.py` tracking, `app/domain/calendar.py` | M |
| N4 | **Real earned value:** EV = estimated hours of **finished** WBS tasks; PV = planned-to-date from the WBS dates. Show SPI = EV / PV and CPI = EV / approved hours. Replaces the current "SPI" (approved ÷ WBS hours), which isn't SPI | The only honest progress figure. Needs N8 first | `app/services/metrics.py`, `GovernanceSummaryCards.jsx` | M |
| N5 | **Budget burn: add an over-budget state.** Burn can exceed the contract value once approved hours pass the target. Show it and cap the bar | Misleading figure today | `metrics.py`, `GovernanceSummaryCards.jsx` | S |
| N6 | ⚖️ **Rate card:** cost = hours × the rate of whoever logged them. It needs **rate history** (`effective_from`, so changing a rate doesn't rewrite past burn) and **currency conversion** (contracts are in AED/SAR/INR/USD; rates are probably INR). Also fill the resource summary's hard-coded zeros (roadmap 7.4) | Budget burn and resourcing are hours ratios, not cost | new `rates` / `fx_rates` tables, `metrics.py`, `booking_approval.py` | M |
| N7 | **Map "discipline" to Electrical / Mechanical / BIM** instead of the job title (P1 #13). Remove the "exceptions / exceeded" wording from the per-discipline view | It groups by designation, and "exceeded" suggests it triggers something (it doesn't, see Decided) | `metrics.py`, mapping table | S–M |
| N8 | ✅ **Done.** One status vocabulary (`app/domain/wbs.py`): tasks To Do → In-Progress → Submitted for Approval → Approved, subtasks To Do → In-Progress → Done. A guard on `WbsNode.deliverable_status` normalizes legacy names on every write (form, edit, Excel upload, API); migration `0002` converted existing rows; one `is_finished` rule for Work Summary, Timeline and both Engineer dashboards; the Lead's WBS form no longer sends "Not Started". Work Summary completion and engineer progress now show real values | Completion showed 0% | `app/domain/wbs.py`, `models.py`, `migrations/versions/0002_*`, `app/services/work_summary.py`, `main.py`, `WbsStructurePage.jsx`, `tests/test_wbs_statuses.py` | S |
| N9 | **One timesheet approval route:** weekly, at main-task level (fits D1). Per-row reject stays for corrections. Migrate the data. The Engineer dashboard reuses `effective_status` instead of its own copy, and so must `project_timeline_logs` (Lead/Engineer Timeline & Logs) and the older `engineer_performance` endpoint, which today count by row status only, so week-approved hours still show as pending there | Two routes double the rules and the bugs | `main.py` weekly-hours + time-log review, Engineer dashboard | M |
| N10 | **Monthly chart: spread planned hours by working days**, not evenly per calendar month | A task running 28 Sep to 31 Oct puts half its hours in September | `app/domain/calendar.py` | S |
| N11 | **Booking planned hours respect the booking %** (20% means 1.6 h a day, not 8) | Resourcing figures are overstated | `main.py` `estimated_hours_from_dates` / booking create and edit | S |
| N12 | **Allocation cap checked per day:** for each day in the new booking's range, the sum of that day's bookings must stay at or below 100%. Rule: the highest daily total, not the sum of every overlapping booking | Today it adds up every booking regardless of dates. A pairwise-overlap sum is also wrong (A: Jan–Mar 50%, B: Feb 50%, C: Mar 50% plus a new Jan–Mar booking sums to 150%, but no single day exceeds 100%) | `main.py` `engineer_total_allocation` | S |
| N13 | **Governance visibility:** (1) pending hours as their own prominent figure; (2) **approval lag**, the age of the oldest pending entry; (3) a **warning-only** alert when approved + pending reach the threshold; (4) an "over-baseline, awaiting extension" figure (N14) | Without these the BU Head can't tell "under budget" from "the Lead hasn't approved anything" | `metrics.py`, `governance_monitor.py`, dashboard cards | M |
| N14 | **Lock behaviour (D8).** Rules: (a) while locked, engineers can log and track; those hours are flagged **over-baseline** and shown in the N13(4) figure; (b) approval (row and week) is blocked while locked; **reject stays allowed** (was C9); (c) after Resume or an extension, approving backlogged hours re-runs the lock check, e.g. a 10 h extension followed by 60 h of backlog approvals must lock again; (d) ✅ **done 2026-09-26:** an approved extension that leaves usage at or above 100% keeps the lock, and the Lead is told why. Tests for every rule | Blocking logging hides work instead of stopping it; rules (c) and (d) stop the lock being bypassed | `main.py` logging and review endpoints (move per rule 2), `app/services/governance.py` `decide_extension`, `governance_monitor.py` | M |

### P1b: BU Head control and project lifecycle

| ID | Task | Why | Where | Size |
|---|---|---|---|---|
| C1 | **Archive / soft delete plus project status** (P1 #8). Hard delete becomes admin-only or is removed | Delete wipes the governance audit log | `app/repositories/projects.py`, `services/projects.py`, Created Projects UI | M |
| C2 | **Edit project** with PUT and a UI (P1 #7). Changes to target hours or threshold go in the audit log and re-run the lock check **in both directions**: raising the target can move usage under 100% (unlock, same rule as N14(d)); **lowering it can push usage to 100% or more, which must lock**. Test both directions, so editing is never a way round the lock | A typo in the contract value can only be fixed by deleting the project | `routers/bu_head/projects.py`, `services/projects.py`, `GovernanceMonitor`, Create Project form reused as an edit form | M |
| C3 | **Create Project: add end date, scope, project type and SOW upload** (P1 #9); the SOW goes through the authenticated file endpoint (S5). Show the SharePoint failure message, which is lost on redirect today | Missing baseline data; contracts must not be public | `createProjectForm.js`, `services/projects.py` | M |
| C4 | **Reject button and rejection reason on the Resource Booking page** (P1 #10). The API exists | The BU Head can approve but not send back | `ResourceBookingPage.jsx`, `booking_approval.py` | S |
| C5 | **Approve or reject bookings per engineer**, not all-or-nothing | You can't approve three engineers and reject one | `booking_approval.py`, `main.py` submit, UI | M |
| C6 | **Editing an approved booking creates a pending change; the last approved version stays active** (dates, %, access) until the BU Head approves the change | Otherwise the engineer loses project access mid-project, and today edits bypass approval entirely | `models.py` (pending-change fields), `main.py` booking update, `booking_approval.py` | M |
| C7 | **Assignment vs access (decided):** Leads assign after booking; the engineer sees tasks once the booking is approved. Safeguards: (a) a **badge on WBS tasks** saying "assigned engineer not approved"; (b) when the BU Head rejects or reduces a booking, the Lead is told **which tasks are affected**; (c) removing a booking can't leave tasks assigned silently | Today tasks can end up with someone who will never see them | `main.py` WBS + booking delete, `booking_approval.py` notification, `WbsStructurePage.jsx` | S–M |
| C8 | **Confirmation dialog on Stop and Resume** | Prevents clicking by accident | `GovernanceControls.jsx` + `ConfirmDialog` | S |
| C9 | *(merged into N14 rule b)* | | | |
| C10 | ✅ **Done** (with S3). Deleting a WBS node also deletes its `time_sessions` | Left orphan rows | `main.py` WBS delete | S |
| C11 | **Engineers can log hours in a week that has no entry yet.** This becomes part of N1's main-task weekly timesheet | The timesheet UI only shows rows that already exist | N1 | – |
| C13 | **WBS edit dialog must respect the status flow.** Today a Lead can set any status directly (Approved, Done), skipping the engineer's steps and the dedicated approve action. Limit the edit dialog to non-status fields, or to transitions the flow allows | Workflow bypass | `WbsStructurePage.jsx`, `main.py` `update_wbs_node` | S |
| C12 | **Audit log for booking approvals, rejections and edits** (who, when, before/after) | The governance log doesn't cover resourcing decisions | `booking_approval.py`, `main.py` booking edit, new audit table or `governance_actions` | S–M |

---

## P2: Workflows and visibility

| ID | Task | Why | Where | Size |
|---|---|---|---|---|
| W1 | **BU Head Timeline view** (P1 #15): Timeline & Logs is empty for the BU Head, the Gantt is hard-coded to Sep–Dec 2026, and the Submission phase is missing | The BU Head has no schedule view | `TimelineLogsPage.jsx`, timeline endpoints | M |
| W2 | **BU Head Weekly Logs view** (P1 #16), read-only across all projects | The BU Head can't see timesheets | new page + endpoint | M |
| W3 | **One notification system:** move the Resource Booking page's own 5 s-polling banner to the header bell | Duplicate code and polling load | `ResourceBookingPage.jsx`, `NotificationBell.jsx` | S |
| W4 | **Portfolio dashboard:** all projects with level, burn, locks and approval lag | The BU Head's home screen | new page + aggregate endpoint | L |
| W5 | **Exports** (CSV/PDF) of the dashboard, Work Summary and timesheets | Reporting upward | export endpoints | M |
| W6 | **User management page:** create users, set discipline and office, reset password, deactivate (the CLI covers deactivation until then via S6). **Deactivating must list the person's bookings and WBS assignments for reassignment**, so a leaver's tasks don't sit orphaned (see C7) | Admin tasks without a terminal | new page + endpoints | M |

---

## P3: Architecture and technical debt

| ID | Task | Why | Where | Size |
|---|---|---|---|---|
| E4 | ✅ **Done.** Alembic with a baseline revision `0001` generated from the models; `migrate(engine)` runs at startup. A database created before Alembic is adopted automatically, once per machine: the old patches are replayed, missing indexes created, the schema **compared with the models** (a missing table or column stops startup; smaller differences are logged), then stamped. Dry run on a copy of the real database: adopted, 6 users and 4 projects intact, 5 missing indexes created. Adoption also fills NULLs and enforces NOT NULL on the five columns the old patches left nullable (lock threshold and lock flag included), so the adopted schema matches the baseline; only 2 type notes remain (see E5). The ~270 lines of `ALTER TABLE` code left `main.py` and `schema_upgrades.py` is gone. **Later:** delete `app/core/legacy_schema.py` once every database has started once on the new code; with Postgres or several workers (E5), run `alembic upgrade head` as a deploy step instead of at startup | Adding schema at import time won't survive a production database | `backend/alembic.ini`, `backend/migrations/`, `app/core/migrations.py`, `app/core/legacy_schema.py`, `tests/test_migrations.py` | M |
| E1 | **Move Lead/Engineer endpoints into `app/`**, incrementally, under working rule 2 (M+ changes only). Extend the guard test as each feature moves | `main.py` is about 2,800 lines | `backend/main.py` → `backend/app/` | L (spread out) |
| E2 | **Migrate the Lead, Engineer and shared pages** to `features/` + `hooks/` + `api/` with no direct `fetch`, on first M+ change. `ResourceBookingPage` first | Same standard as the BU Head pages | `frontend/src/pages/` | L (spread out) |
| E3 | ✅ **Done.** `npm run lint` has 0 errors (unused imports, state and functions removed in `WbsStructurePage.jsx`, `pages/lead/ExecutiveDashboardPage.jsx`, `EngineerPerformanceDashboardPage.jsx`). 19 older warnings remain (hook dependencies, fast refresh) | `npm run lint` failed | those files | S |
| E5 | **Postgres decision, foreign keys, indexes** (after E4). Also align two harmless type differences in adopted dev databases: `projects.timesheets_soft_locked` INTEGER vs BOOLEAN, `wbs_nodes.deliverable_status` VARCHAR(60) vs (40) | Production-grade database | `models.py`, config | M |
| E6 | **Performance:** SQL aggregates instead of per-row queries; less polling | Scales badly | `main.py`, pages | M |
| E7 | **Delete dead code:** the `gantt_tasks` table (its endpoints were removed in S3), `project_leads`, the legacy `request-extension` endpoint, `leads_loader.py`, `temp_*.py`, `App.css`, the unused `recharts` dependency, and the tracker if D1a says remove | Noise | various | S |
| E8 | **Tokens in httpOnly cookies** instead of `localStorage` | XSS could steal tokens | `security.py`, `api/client.js`, `AuthContext.jsx` | M |
| E9 | **Production setup:** single-port build (FastAPI serves the built frontend), structured logging, error monitoring | Deployment | `main.py`, `vite build` | M |

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
| D1a | Tracker after N1: keep it as an optional pre-fill of the weekly timesheet, or remove it? | Ask the engineers. If nobody would use it, remove it (less code, S4 no longer needed) |
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
2. **Sprint A:** E4 Alembic ✅, N2 7-day hours ✅, N8 statuses ✅, E3 lint ✅, then C1 archive, C2 edit, C4 reject button, C8, N5, N8, N11, N12, N13.
3. **Sprint B (timesheets and lock):** N1 timesheet model (tell the previous Engineer developer first), N9 single approval route, N14 lock rules, C6, C7, C10, C12. Lead/Engineer features move into `app/` as they are touched.
4. **Sprint C (calendar and cost):** N3 office field, N4 EV/SPI/CPI, N6 rate card, N7 disciplines, N10, C3 (after S5), C5.
5. **Sprint D:** W1–W3.
6. **Then:** W4–W6, E5–E9, P4 SharePoint.

---

## Go-live checklist (before the first deployment)

Nothing here is urgent while the app is in development. All of it must be done before real users and real data arrive.

- [ ] **N1:** the timesheet entry screen exists and engineers use it (otherwise every governance figure is near 0).
- [ ] **S1:** rotate the Azure client secret (needs Azure credentials).
- [ ] **S2:** purge the HR CSV and the old secret from git history; ask Subhika to delete her clone.
- [ ] **E5:** database decision (SQLite or Postgres), foreign keys, indexes. With Postgres or several workers, run `alembic upgrade head` as a deploy step instead of at startup.
- [ ] **E8:** tokens in httpOnly cookies. **E9:** single-port production build, structured logging, error monitoring.
- [ ] **S7:** `backup_db.py --dir <off-machine folder>` scheduled nightly (or the managed database's own backups), plus a restore drill on the production setup.
- [ ] **CORS and settings:** production origin in the CORS list, `DATABASE_URL`, `.env` values on the server only.
- [ ] **Clean start:** a fresh production database (no test projects or accounts), real accounts via `create_user.py`, and the legacy `project_leads` seed removed (E7).
- [ ] **SP6:** SharePoint end-to-end test against the real tenant.
- [ ] Delete `app/core/legacy_schema.py` (only needed to adopt pre-Alembic development databases).
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
| E4: Alembic migrations; pre-Alembic databases adopted automatically at startup | `7bd72ba`, `ceb8f4a` |
| N2: hours on all seven days count | `23eec47` |
| N8 WBS statuses normalized; E3 lint errors fixed | this sprint |
