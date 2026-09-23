# Contributing

Three developers work on this codebase, split by role. This file records how we
avoid stepping on each other while we restructure the monolith.

## ⚠️ Before you pull the "Phase 0 foundation" change

That change stops tracking files that should never have been in git: the
committed virtualenv (`backend/Lib`, `Include`, `Scripts`), `frontend/node_modules`,
`frontend/dist`, both `.env` files, the SQLite databases and the employee CSV.
**When you pull it, git deletes those files from your working copy.** Before
pulling:

1. Copy these somewhere outside the repo if you have them: `backend/.env`,
   `frontend/.env`, `backend/promanage.db`, `backend/data/employee_leads.csv`.
2. Pull, then put the copies back in place. They are git-ignored from now on.
3. Recreate the environments: follow **First-time setup** in [README.md](README.md)
   (new virtualenv in `backend/.venv`, `npm ci` in `frontend/`).
4. Run `backend\.venv\Scripts\pre-commit.exe install`.

Forgot to back up? The files are still in git history, in the last commit
before Phase 0. Restore them (they stay git-ignored) with:

```
git restore --source=f3dfe25 --worktree -- backend/.env frontend/.env backend/promanage.db backend/data/employee_leads.csv
```

Then run `npm ci` in `frontend/`.

The Azure client secret that was committed in `backend/.env` is being rotated.
Ask for the new value; do not reuse the old one.

## Ownership

| Area | Owner | Main files today |
|---|---|---|
| BU Head: projects, governance, resource approval, dashboards | BU Head developer | `pages/bu_head/*`, `backend/app/api/routers/bu_head/*` and the `app/services` they use |
| SharePoint / Microsoft Graph integration | BU Head developer | `backend/app/integrations/sharepoint/*`, `pages/shared/SharePointMirrorPage.jsx` |
| Lead workflows (WBS, bookings, timesheet review, extension requests) | Lead developer | `pages/lead/*`, Lead endpoints |
| Engineer workflows (tasks, timesheets, performance) | Engineer developer | `pages/engineer/*`, Engineer endpoints |
| **Shared**: `main.py`, `models.py`, `schemas.py`, `backend/app/core`, `app/domain`, `app/services/access.py`, `App.jsx`, `AuthContext.jsx`, `MaecHeader.jsx`, `styles.css`, shared pages | Everyone | Announce before changing; keep diffs small |

If a bug in your area is caused by another owner's code, open an issue or tell
them. Don't fix it silently in their files.

## Working on `main`

We all commit directly to `main` (trunk-based development) instead of using
long-lived branches that end in large merges. Conflicts come from two people
editing the same lines, not from branches. Working on `main` keeps them small
only if everyone syncs often:

1. **One-time setup:** `git config pull.rebase true`, so pulls replay your local
   commits on top of everyone else's instead of creating merge commits.
2. **Pull before you start** and **pull again right before you push**
   (`git pull --rebase`). If a rebase stops on a conflict, fix it, `git add` the
   file, then `git rebase --continue`.
3. **Small commits, pushed often.** Push at least once a day. A commit is one
   logical change, with a message that says what changed and why.
4. **Keep `main` working.** Run the backend tests, ruff, and the frontend
   lint/build before pushing. Never push something that doesn't start.
5. **Never force-push `main`.** Never rewrite history that others have pulled.
6. **Shared files:** post a short message in the team chat before editing a
   shared file (see Ownership), and push those edits quickly so the others
   rebase over them the same day.
7. **Big or breaking changes** (restructuring folders, database schema,
   untracking files) are announced before they are pushed, with the steps the
   others need to take after pulling.

## Backend module layout (roadmap Phase 1)

Only the **BU Head and SharePoint** code has moved into the `backend/app/`
package. **Lead and Engineer endpoints stay in `main.py`**, and their owners can
move them into `app/api/routers/lead|engineer` whenever they choose, following
the same pattern. URLs and response shapes did not change.

```
backend/
  main.py                  # startup migrations + seeding, Lead/Engineer endpoints, mounts app routers
  app/
    core/                  # config (settings), database, security (auth, role guards), roles, errors
    domain/                # pure shared rules: timesheets (Mon–Fri totals), calendar (monthly spreading)
    repositories/          # data access only; never commit (services own the transaction)
    services/              # business logic; raise app.core.errors, never HTTPException
    integrations/sharepoint/ # DocumentStorage interface + Microsoft Graph client
    api/
      deps.py              # composition root: builds services from repositories/adapters
      routers/auth.py      # login / logout / me
      routers/bu_head/     # projects & SharePoint, governance, resourcing approval
  database.py, auth.py     # compatibility shims re-exporting app.core (keep old imports working)
```

### Where did shared code go?

`main.py` imports these back under their old names, so Lead/Engineer code runs
unchanged. **Change them in their new home**, not by re-adding them to `main.py`:

| Old name in `main.py` | New home |
|---|---|
| `require_role` | `app/core/security.py` (plus guards `require_bu_head`, `require_lead_or_bu_head`, `require_any_role`) |
| `get_current_user`, `hash_password`, `verify_password` | `app/core/security.py` (`auth.py` re-exports them) |
| `time_entry_total` (Mon–Fri rule) | `app/domain/timesheets.py` → `entry_total` |
| `_get_month_key`, `_distribute_hours_over_months` | `app/domain/calendar.py` |
| `engineer_wbs_condition`, `engineer_wbs_ids`, `lead_project_ids`, `user_can_access_project` | `app/services/access.py` |
| `executive_dashboard_data` | `app/services/metrics.py` |
| `extension_request_output`, `find_pending_extension_request` | `app/services/governance.py` |
| `booking_approval_status`, `BOOKING_APPROVAL_LABELS` | `app/services/booking_approval.py` |
| `create_bu_head_notification` | `app/services/notifications.py` |
| `sharepoint_service.py` | `app/integrations/sharepoint/graph.py` |

Removed as dead code: `POST /governance/approve-extension` and
`/governance/reject-extension` (duplicates of the extension decision endpoint,
unused by the UI).

### Frontend layout (roadmap Phase 2)

BU Head and SharePoint pages moved to `src/features/` and use the shared data
layer below. Lead, Engineer and shared pages (`src/pages/`) are unchanged and
can adopt it whenever their owners choose.

```
frontend/src/
  api/          client.js (base URL, token, ApiError) + one module per domain; queryClient.js
  hooks/        TanStack Query hooks (useProjects, useGovernance, useSharePointMirror,
                useProjectSelection) and queryKeys.js
  components/   shared UI: PageHeader, ProjectSwitcher, StatCard, MonthlyHoursChart,
                ConfirmDialog, Feedback (ErrorBanner, Notice, EmptyState)
  constants/    currencies, SharePoint disciplines
  utils/        format.js (hours, %, money, dates, bytes)
  providers/    QueryProvider (cache, 401 -> logout, cleared on user change)
  features/bu-head/     Created/Create Project, Executive Dashboard (+ governance/), Work Summary
  features/sharepoint/  SharePoint Mirror
  pages/        Login + Lead/Engineer/shared pages (not yet migrated)
```

Rules for new frontend code: pages never call `fetch` directly. They use a hook
from `hooks/`, which calls `api/`. Formatting goes through `utils/format.js`.
Routes are lazy-loaded in `App.jsx`. Tests (`npm test`, Vitest) sit next to the
code as `*.test.js(x)`.

Each role's routers, services and feature folders are owned by that role's
developer. `core/`, `domain/`, `repositories/`, `integrations/` and
`components/` are shared.

## Coding standards
- **Layering:** routers and components stay thin. Business rules live in
  services (backend) and hooks (frontend). Database access lives in repositories.
- **SOLID:** depend on small interfaces (for example `DocumentStorage` for
  SharePoint) passed in through FastAPI dependencies, so they can be faked in tests.
- **Performance:** no queries inside loops. Use aggregate SQL. Reuse HTTP
  clients and tokens. Don't poll every few seconds when refetch-on-focus will do.
- **Constants:** statuses, roles and phases come from shared enums/constants,
  never string literals scattered through the code.
- **Tests:** new business rules come with tests. The backend suite runs against
  a throwaway database and never touches Microsoft Graph.

## Lint and format ratchet

Legacy files predate the standards. Reformatting them all at once would conflict
with everyone's in-progress work, so they are listed as exceptions:

- Python: `extend-exclude` in [backend/pyproject.toml](backend/pyproject.toml)
- Frontend formatting: [frontend/.prettierignore](frontend/.prettierignore)

Rules:
1. **Never add** a file to these lists.
2. When you refactor a legacy file, **remove it** from the list in the same commit and make it pass.
3. ESLint applies to every file you stage. If you touch a legacy frontend file,
   fix its lint errors (mostly unused variables) in that commit.

## Characterization tests

`backend/tests/` records the current behaviour of the BU Head API so
refactoring can't silently change it. Assertions marked **`KNOWN (roadmap X.Y)`**
record behaviour that is currently wrong and scheduled to be fixed. When you fix
one, update that assertion in the same commit.

## Known cross-team items

The BU Head suite found these in Lead/Engineer code:
- Any lead can read any project's Executive Dashboard, including contract value
  (`GET /executive-dashboard` has no project-access check for leads).
- Any lead can file an extension request on any project.
- Lead endpoints that create, update or delete WBS nodes, and submit bookings,
  have no project-access check.
- New WBS nodes default to the legacy status "Not Started" (current flow: "To Do").
- Engineers can't log hours in a week with no existing entry (the timesheet UI
  only shows rows that already exist).
