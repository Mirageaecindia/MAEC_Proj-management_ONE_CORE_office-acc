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
| BU Head: projects, governance, resource approval, dashboards | BU Head developer | `pages/bu_head/*`, BU Head endpoints in `main.py` |
| SharePoint / Microsoft Graph integration | BU Head developer | `sharepoint_service.py`, `pages/shared/SharePointMirrorPage.jsx` |
| Lead workflows (WBS, bookings, timesheet review, extension requests) | Lead developer | `pages/lead/*`, Lead endpoints |
| Engineer workflows (tasks, timesheets, performance) | Engineer developer | `pages/engineer/*`, Engineer endpoints |
| **Shared**: `main.py`, `models.py`, `schemas.py`, `auth.py`, `database.py`, `App.jsx`, `AuthContext.jsx`, `MaecHeader.jsx`, `styles.css`, shared pages | Everyone | Announce before changing; keep diffs small |

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

## Planned module layout (for agreement, roadmap Phase 1)

URLs and response shapes stay identical during the move, so the frontend keeps working.

```
backend/app/
  main.py                  # create_app(): middleware + routers only
  core/                    # settings, database session, security (auth + require_roles), errors
  models/  schemas/        # one module per domain
  repositories/            # database access only (aggregate SQL, no per-row query loops)
  services/                # business rules
  integrations/sharepoint/ # DocumentStorage interface + Microsoft Graph implementation
  api/routers/
    bu_head/  lead/  engineer/  shared/
alembic/                   # schema migrations (replaces ALTER TABLE-on-import)

frontend/src/
  api/          # single HTTP client + one module per domain
  hooks/        # data hooks (caching, refetch)
  components/   # shared UI
  features/bu-head/  features/lead/  features/engineer/
  utils/        # formatting helpers
```

Each role's routers, services and feature folders are owned by that role's
developer. `core/`, `models/`, `integrations/` and `components/` are shared.

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
