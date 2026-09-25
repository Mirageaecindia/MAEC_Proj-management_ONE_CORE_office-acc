# MAEC API (backend)

FastAPI service for MAEC Project Management. Setup and run instructions live in
the [root README](../README.md).

- API docs (when running): http://localhost:8000/docs
- Code layout: auth, BU Head and SharePoint code live in the layered `app/`
  package (routers → services → repositories). Lead/Engineer endpoints are in
  `main.py`. See the [Project Guide](../docs/PROJECT_GUIDE.md) §6.4 and
  [CONTRIBUTING](../CONTRIBUTING.md).
- Configuration: typed settings in `app/core/config.py`, read from the
  environment and `.env` (template: `.env.example`). `DATABASE_URL` defaults to
  `backend/promanage.db`, resolved relative to this folder.
- SharePoint / Microsoft Graph setup: [SHAREPOINT_SETUP.md](SHAREPOINT_SETUP.md)
- Accounts: [USERS.md](USERS.md)
- Tests: `..\.venv\Scripts\python.exe -m pytest` (from `backend/`; the venv lives at
  the repo root). Uses a throwaway database with SharePoint faked or disabled;
  never touches `promanage.db` or Microsoft Graph
