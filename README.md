# MAEC Project Management (ProManage)

Project governance tool for MAEC with three roles (BU Head, Lead, Engineer):
project creation with automatic SharePoint folder provisioning, resource
booking, WBS planning, weekly timesheets and an executive governance dashboard.

| Part | Stack | Folder |
|---|---|---|
| API | FastAPI · SQLAlchemy · SQLite (Postgres-ready) · Microsoft Graph (MSAL) | [backend/](backend/) |
| Web app | React 19 · Vite · React Router | [frontend/](frontend/) |

**New to the project?** Read the [Project Guide](docs/PROJECT_GUIDE.md) for the
product, roles, end-to-end lifecycle, architecture, data model, business rules,
full API reference and known issues.

## Prerequisites
- Python 3.12+ (developed on 3.14)
- Node.js 20+ (developed on 24) and npm

## First-time setup

### Backend
```powershell
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
copy .env.example .env                                  # then fill in Azure/SharePoint values
copy data\employee_leads.example.csv data\employee_leads.csv   # or the real HR export
```
macOS/Linux: use `.venv/bin/python` and `cp`.

The employees table is seeded from `backend/data/employee_leads.csv` on first
start. The real HR export contains personal data and is git-ignored. Never
commit it.

### Frontend
```powershell
cd frontend
npm ci
copy .env.example .env
```

### Git hooks (once per clone)
```powershell
backend\.venv\Scripts\pre-commit.exe install
```

### Accounts
Accounts are created from the command line. See [backend/USERS.md](backend/USERS.md).

## Running locally
```powershell
# terminal 1 — API on http://localhost:8000 (docs at /docs)
# Recommended: the script frees port 8000 (a leftover uvicorn from a previous
# run keeps it bound, which makes every new start fail with "address already
# in use") and launches the API with the repo venv. Stop it with stop_backend.ps1.
cd backend
.\start_backend.ps1

# ...or run it manually in the foreground (the venv can be backend\.venv or the repo-root .venv):
cd backend
..\.venv\Scripts\python.exe -m uvicorn main:app --reload

# terminal 2 — web app on http://localhost:5173
cd frontend
npm run dev
```
The database defaults to `backend/promanage.db` wherever you start uvicorn from.
Set `DATABASE_URL` in `backend/.env` to use another database.

## Quality checks
| Command (run inside the folder) | What it does |
|---|---|
| `backend> .venv\Scripts\python.exe -m pytest` | BU Head API characterization suite |
| `backend> .venv\Scripts\ruff.exe check .` / `ruff.exe format .` | Lint / format Python |
| `frontend> npm test` | Vitest: unit tests + BU Head page render tests |
| `frontend> npm run lint` | ESLint |
| `frontend> npm run format:check` / `npm run format` | Prettier |
| `frontend> npm run build` | Production build |

Pre-commit runs ruff, Prettier and ESLint on the files you stage. It also blocks
`.env` files, databases and employee CSVs from being committed.

See [CONTRIBUTING.md](CONTRIBUTING.md) for code ownership, the working-on-main workflow and the
legacy-file lint ratchet.
