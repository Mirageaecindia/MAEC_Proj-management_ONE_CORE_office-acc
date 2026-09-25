# MAEC ProManage: prioritised to-do list

Last updated: 2026-09-26. Owner: Sajjad, who now owns all three roles
(BU Head, Lead, Engineer) plus the SharePoint integration.

This list combines three sources:
- the open roadmap items;
- the external code review of September 2026;
- known issues in the Lead and Engineer code.

Background for every item is in [PROJECT_GUIDE.md](PROJECT_GUIDE.md).

**How to read it**
- Priority groups:
  - **P0** is security and data, fixed now.
  - **P1** makes the numbers correct and closes gaps in control.
  - **P2** completes the workflows.
  - **P3** is architecture and technical debt.
  - **P4** is SharePoint, which comes last by decision.
- Work top to bottom inside each group.
- Size: **S** is under half a day, **M** is 1–3 days, **L** is a week or more.
- ⚖️ means a product decision is needed before starting. These are listed in the "Decisions needed" section.
- Items with IDs from the old list keep those IDs in brackets, e.g. (P1 #7), so older notes still match.

---

## P0: Security and data (do now)

| ID | Task | Why | Where | Size |
|---|---|---|---|---|
| S1 | **Rotate the Azure client secret.** Update `.env` on every machine, then check that the GitHub repo is **private** | The secret leaked in git history (commit `1b40874`). Anyone with the repo can use Graph with it | Azure portal, `.env` | S |
| S2 | ⚖️ **Purge the HR CSV and the old secret from git history** with `git filter-repo`. Force-push once, then everyone re-clones | Rotating the secret doesn't remove employee personal data from history. This is the only planned exception to "never force-push main". Pick one moment with the whole team | whole repo | M |
| S3 | **Project-access check on Lead WBS create, update and delete** | A Lead can currently change WBS nodes on projects they aren't allocated to | `main.py` WBS endpoints | S |
| S4 | **Limit tracked time to real time elapsed.** On session sync and end, `active_seconds` must not exceed the time since `login_at` | Today the only limit is the 8-hour daily cap. Anyone calling the API can claim 8 h a minute after starting | `main.py` `sync_subtask_tracking`, `end_subtask_tracking` | S |
| S5 | **Update ownership docs:** CLAUDE.md, CONTRIBUTING.md and the guide still describe three owners split by role. Keep the guard test, but reword it as "code lives in `app/`" | New owner: rules must match reality | `CLAUDE.md`, `CONTRIBUTING.md`, `docs/PROJECT_GUIDE.md` | S |

---

## P1: Correct numbers and gaps in control

### P1a: Numbers the BU Head can trust

| ID | Task | Why | Where | Size |
|---|---|---|---|---|
| N1 | ⚖️ **Fix under-counted working time.** Tracking stops when the tab is hidden or idle for 2 minutes, and manual subtask hours are refused | Engineers model in Revit and AutoCAD, not the browser, so the tracker records close to zero. Governance only sees approved hours, so every figure is too low and no alert fires. **This is the biggest domain problem** | `frontend/src/pages/shared/TaskDetailsPage.jsx` (`IDLE_TIMEOUT_MS`), `main.py` tracking, `submit_time_log` | M–L |
| N2 | ⚖️ **Working week per project (or per office)** instead of hard-coded Mon–Fri | KSA works Sun–Thu, and Indian offices often work Saturday. Hours on those days are silently dropped (`WEEKDAY_FIELDS`, tracking skips Sat/Sun) | `app/domain/timesheets.py`, `main.py` tracking, all totals | M–L |
| N3 | **Time zone per project or user** for day boundaries | The 8-hour cap and "today" use the server date, so IST and GST days split differently | `main.py` tracking (`date.today()`), `app/domain/calendar.py` | M |
| N4 | **Fix "SPI".** Rename it to "Earned %" now; later calculate a real EV/PV against planned-to-date | It's approved ÷ WBS hours with no time element, so a BU Head reads it wrongly | `app/services/metrics.py` `_spi`, `GovernanceSummaryCards.jsx` | S / M |
| N5 | **Budget burn: add an over-budget state.** Burn can exceed the contract value when approved hours pass the target. Show it clearly and cap the bar | Misleading figure today | `metrics.py`, `GovernanceSummaryCards.jsx` | S |
| N6 | ⚖️ **Rate card:** cost = hours × the rate of whoever logged them. Also fill the resource summary's commercial figures, which are hard-coded zeros today (roadmap 7.4) | Budget burn and resourcing are hours ratios, not cost | new `rates` table, `metrics.py`, `booking_approval.py` | M |
| N7 | **Map "discipline" to Electrical / Mechanical / BIM** instead of the employee's job title (P1 #13) | The per-discipline view groups by designation | `metrics.py`, `employees.discipline` / mapping table | S–M |
| N8 | **Normalise WBS statuses** (P1 #13): Work Summary completion counts only the legacy "Completed", so it shows 0%. New nodes default to the legacy "Not Started" instead of "To Do" | Completion figures are wrong | `app/services/work_summary.py`, `main.py` WBS create, `models.py` | S |
| N9 | ⚖️ **One timesheet approval route.** Today there are two, per row and per week. Keep one, migrate the data, and have the Engineer dashboard reuse `effective_status` instead of its own copy | Two routes double the rules and the bugs. Governance already combines both | `main.py` weekly-hours + time-log review, Engineer dashboard | M |
| N10 | **Monthly chart: spread planned hours by working days, not evenly per calendar month** | A task running 28 Sep to 31 Oct puts half its hours in September, so the chart and KPIs don't reconcile | `app/domain/calendar.py` `distribute_hours_over_months` | S |
| N11 | **Booking planned hours should respect the booking %** (20% means 1.6 h a day, not 8) | Resourcing figures are overstated | `main.py` `estimated_hours_from_dates` / booking create and edit | S |
| N12 | **The allocation cap must only add up bookings whose dates overlap** | An engineer booked 100% in January can't be booked anywhere in June | `main.py` `engineer_total_allocation` | S |

### P1b: BU Head control and project lifecycle

| ID | Task | Why | Where | Size |
|---|---|---|---|---|
| C1 | **Archive / soft delete plus project status** (P1 #8). Hard delete stays admin-only, or is removed | Delete wipes the governance audit log, which defeats having one | `app/repositories/projects.py`, `services/projects.py`, Created Projects UI | M |
| C2 | **Edit project** with PUT and a UI (P1 #7). Record changes to target hours or threshold in the audit log and re-run `GovernanceMonitor` | A typo in the contract value can only be fixed by deleting the project | `routers/bu_head/projects.py`, `CreateProjectPage` reused as an edit form | M |
| C3 | **Create Project: add end date, scope, project type and SOW upload** (P1 #9). Show the SharePoint failure message; today it's lost on redirect | Missing baseline data | `createProjectForm.js`, `services/projects.py` | M |
| C4 | **Reject button and rejection reason on the Resource Booking page** (P1 #10). The API already exists | The BU Head can approve but not send back | `ResourceBookingPage.jsx`, `booking_approval.py` (reason) | S |
| C5 | **Approve or reject bookings per engineer**, not all-or-nothing per project | You can't approve three engineers and reject one | `booking_approval.py`, `main.py` submit, UI | M |
| C6 | **Editing an approved booking sends it back for approval** | Today a Lead can change an allocation after approval and bypass the BU Head | `main.py` booking update | S |
| C7 | **Assignment must match access.** Only engineers with an approved booking can be assigned WBS tasks. Removing a booking must reassign or block if tasks remain | Today a Lead can assign tasks to engineers who can't open the project, and removing a booking orphans their tasks | `main.py` assignable-engineers query, booking delete | S–M |
| C8 | **Confirmation dialog on Stop Execution** (and on Resume) | Prevents clicking it by accident | `GovernanceControls.jsx` + `ConfirmDialog` | S |
| C9 | ⚖️ **Leads may reject (not approve) hours while a project is locked** | Rejecting can only lower usage, so it's safe, and it lets Leads clear bad entries | `main.py` `lead_review_time_log`, `lead_review_weekly_hours` | S |
| C10 | **Deleting a WBS node also deletes its `time_sessions`** | Leaves orphan rows today | `main.py` WBS delete | S |
| C11 | **Engineers can log hours in a week with no existing entry** | The timesheet UI only shows rows that already exist | `EngineerWeeklyLogsPage.jsx` / `TimelineLogsPage.jsx` | S–M |

---

## P2: Workflows and visibility

| ID | Task | Why | Where | Size |
|---|---|---|---|---|
| W1 | **BU Head Timeline view** (P1 #15): Timeline & Logs is empty for the BU Head, the Gantt is hard-coded to Sep–Dec 2026, and the Submission phase is missing | The BU Head has no schedule view | `TimelineLogsPage.jsx`, `main.py` timeline endpoints | M |
| W2 | **BU Head Weekly Logs view** (P1 #16), read-only across all projects | The BU Head can't see timesheets | new BU Head page + endpoint | M |
| W3 | **One notification system:** the Resource Booking page has its own banner that polls every 5 s. Move it to the header bell | Duplicate code and polling load | `ResourceBookingPage.jsx`, `NotificationBell.jsx` | S |
| W4 | **Portfolio dashboard:** all projects, with level, burn and locks at a glance | The BU Head's home screen | new BU Head page, aggregate endpoint | L |
| W5 | **Exports** (CSV/PDF) of the dashboard, Work Summary and timesheets | Reporting upward | backend export endpoints | M |
| W6 | **User management UI** to replace `create_user.py` (create users, set discipline, reset password, deactivate) | Admin tasks without a terminal | new BU Head/admin page + endpoints | M |

---

## P3: Architecture and technical debt

| ID | Task | Why | Where | Size |
|---|---|---|---|---|
| E1 | **Move the Lead and Engineer endpoints out of `main.py` into `app/`** (routers → services → repositories), one feature at a time: bookings, WBS, timesheets, tracking, dashboards. Keep the guard test and extend it | `main.py` is about 2,800 lines with per-row queries and `HTTPException` in business logic. It is now possible because all roles have one owner | `backend/main.py` → `backend/app/` | L |
| E2 | **Migrate the Lead, Engineer and shared pages** to `features/`, `hooks/` and `api/`, with no direct `fetch` calls. Start with `ResourceBookingPage` | Same standard as the BU Head pages; caching instead of polling | `frontend/src/pages/` | L |
| E3 | **Fix the 6 ESLint errors** in `WbsStructurePage.jsx`, `pages/lead/ExecutiveDashboardPage.jsx` and `EngineerPerformanceDashboardPage.jsx`. Shrink the lint "ratchet" list as files are refactored | `npm run lint` fails today | those files, `backend/pyproject.toml` ratchet | S |
| E4 | **Alembic migrations** to replace `ALTER TABLE` at import and `app/core/schema_upgrades.py` | Won't survive a production database | `backend/alembic/` | M |
| E5 | **Postgres decision, foreign keys, indexes** | SQLite plus no foreign keys isn't production-grade | `models.py`, config | M |
| E6 | **Performance:** replace per-row queries with SQL aggregates, and replace 5 s / 15 s polling with longer intervals or push | Scales badly with more projects | `main.py`, pages | M |
| E7 | **Delete dead code:** `gantt_tasks`, `project_leads`, the legacy `request-extension` endpoint, `leads_loader.py`, `temp_*.py`, `App.css`, the unused `recharts` dependency | Noise and confusion | various | S |
| E8 | **Tokens in httpOnly cookies** instead of `localStorage` | XSS could steal tokens | `app/core/security.py`, `api/client.js`, `AuthContext.jsx` | M |
| E9 | **Production setup:** single-port build (FastAPI serves the built frontend), structured logging, error monitoring | Deployment | `main.py` static mount, `vite build` | M |

---

## P4: SharePoint (last, by decision)

It has never provisioned successfully, so treat it as unbuilt, not buggy.

| ID | Task | Why | Size |
|---|---|---|---|
| SP1 | Ask IT for **`Sites.Selected`** instead of `Sites.ReadWrite.All` (after S1) | Least privilege | S |
| SP2 | **Name folders by project code** (unique), not project name | `conflictBehavior: rename` silently creates "Name 1" | S |
| SP3 | **Store driveItem IDs**, not URLs | Renames and moves break URLs | S |
| SP4 | **Background provisioning with retry**, and a provisioning status on the project | Create Project mustn't depend on Graph being up | M |
| SP5 | **Lazy mirror including subfolder files** | Only root files are shown today | M |
| SP6 | **End-to-end test against the real tenant** | Never verified | S |

---

## Decisions needed (⚖️)

| # | Question | My recommendation |
|---|---|---|
| D1 | How do we capture engineers' real working time (N1)? | Keep the tracking session running while it's open (heartbeat, no idle cut-off), plus allow **manual subtask hours that the Lead approves**. Lead approval is the real check, and governance already counts only approved hours |
| D2 | Working week and time zone (N2, N3): per project or per office? | **Per project** (a KSA project follows KSA days), with the office as the default |
| D3 | Where do the rates for the rate card come from (N6)? | One rate per designation, maintained by the BU Head |
| D4 | When do we do the history rewrite (S2)? | A quiet evening. Everyone pushes first, then we rewrite and everyone re-clones |
| D5 | Which timesheet approval route stays (N9)? | **Weekly** (the newer flow), with per-row reject kept for corrections |
| D6 | Can Leads reject hours while a project is locked (C9)? | Yes: reject only, never approve |

---

## Suggested order for the next sprints

1. **Now:** S1, then S3 and S4 (small security fixes), S5 (docs), and decide D1–D6.
2. **Sprint A:** C1 archive, C2 edit, C4 reject button, C6, C8, N4, N5, N8, N10, N11, N12, E3.
3. **Sprint B:** N1 time capture and N9 single approval route (after D1 and D5), C5, C7, C9–C11.
4. **Sprint C:** N2 and N3 working week and time zone (after D2), N6 and N7 rate card and disciplines.
5. **Sprint D:** W1–W3, then E1 and E2 (move Lead/Engineer code), E4 Alembic.
6. **Then:** W4–W6, E5–E9, S2 history rewrite (at the agreed moment), P4 SharePoint.

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
| `/api/server-date` returns real UTC (review item already fixed) | Subhika's UTC change |
