# CLAUDE.md: rules for AI assistants working in this repo

MAEC ProManage: FastAPI backend (`backend/`) + React/Vite frontend (`frontend/`).
Since 2026-09-26 one owner (Sajjad) is responsible for all roles (BU Head, Lead,
Engineer) and SharePoint. Work happens **directly on `main`**. Earlier the work
was split between three developers, and they may still push, so the merge rules
below still apply. Details: `CONTRIBUTING.md`; full project docs:
`docs/PROJECT_GUIDE.md`; prioritised backlog and working rules: `docs/TODO.md`.

## Where code lives (do not move it back)

| Code | Location |
|---|---|
| Auth, all BU Head endpoints, SharePoint integration | `backend/app/` (routers → services → repositories) |
| Shared helpers: access rules, dashboard metrics, timesheet totals, booking approval status, BU Head notifications | `backend/app/services/`, `backend/app/domain/`, `backend/app/core/` |
| Lead and Engineer endpoints, startup migrations and seeding | `backend/main.py` (moving into `backend/app/` feature by feature, per the working rules in `docs/TODO.md`) |
| BU Head and SharePoint pages, shared data layer | `frontend/src/features/`, `api/`, `hooks/`, `components/` |
| Lead / Engineer / shared pages | `frontend/src/pages/` |

`main.py` **imports** the shared helpers from `app/` under their old names
(`require_role`, `user_can_access_project`, `time_entry_total`,
`executive_dashboard_data`, …). The full old-name → new-home table is in
CONTRIBUTING.md, "Where did shared code go?".

## Hard rules for `backend/main.py`

1. **Never re-add** BU Head endpoints (auth, projects, executive-dashboard,
   work-summary, resource-summary, resource-bookings approve/reject,
   notifications, governance, extension-request decisions) or **redefine** the
   shared helpers listed above. To change one, edit its file under `backend/app/`.
2. `register_exception_handlers(app)` and `app.include_router(api_router)` stay
   **directly after** the CORS middleware setup, before any `@app` route.
   There is no public `/uploads` mount; files are served only through an
   authenticated endpoint (`tests/test_uploads.py`).
3. `backend/tests/test_route_ownership.py` enforces 1 and 2. **Never delete or
   weaken it** to make a merge pass. A failure means code was re-added: remove it.

## Resolving merge conflicts

- Resolve **block by block**. Never take one side's whole file
  ("accept ours/theirs" for an entire file). That is how 1,100 lines of moved
  code once came back into `main.py`.
- If one side deleted or moved code, do **not** restore it. Apply the other
  side's intended change in the code's new location instead.
- After resolving: run the backend and frontend tests (below), then check
  `git diff --stat origin/main`. If a file grew by hundreds of lines nobody
  wrote, stop and investigate.
- If unsure, `git rebase --abort` (nothing is lost) and ask the developer.

## Commands (run before every push)

```powershell
cd backend
<venv>\Scripts\python.exe -m pytest        # all tests must pass
<venv>\Scripts\ruff.exe check .            # lint (legacy files are excluded in pyproject.toml)
cd ..\frontend
npm test                                   # Vitest
npm run lint
npm run build
```
`<venv>` is `backend\.venv` or the repo-root `..\.venv`, depending on the machine.

## Git workflow

- Commit directly to `main`; small commits; `git pull --rebase` before starting and before pushing.
- Never force-push `main`; never rewrite pushed history. The one planned exception is the
  coordinated history purge in `docs/TODO.md` (S2).
- Never commit `.env`, `*.db`, logs, or `backend/data/*.csv` (employee personal data).

## Conventions

- Layering: routers/components stay thin; business rules in services (backend) and hooks (frontend); DB access in repositories.
- Services raise `app.core.errors` exceptions, never `HTTPException`.
- Timestamps are stored and returned as **UTC**: `datetime.now(UTC)`, never naive `datetime.now()`.
- Frontend pages never call `fetch` directly: use a hook from `hooks/` that calls `api/`.
- New business rules come with tests; update `KNOWN (roadmap X.Y)` assertions deliberately when fixing them.
- Legacy files are on a lint/format "ratchet" list: never add to it, remove a file from it when you refactor it.
- Schema changes: no new entries in `app/core/schema_upgrades.py`; they go through Alembic (`docs/TODO.md` E4).
- Changing Lead/Engineer code in `main.py`: small (S) fixes are patched in place with a test; bigger changes
  first get characterization tests, then the feature moves into `app/`, then it changes.
