# MAEC API (backend)

FastAPI service for MAEC Project Management. Setup and run instructions live in
the [root README](../README.md).

- API docs (when running): http://localhost:8000/docs
- Database: `DATABASE_URL` in `.env`; defaults to `backend/promanage.db`,
  resolved relative to this folder rather than the working directory.
- SharePoint / Microsoft Graph setup: [SHAREPOINT_SETUP.md](SHAREPOINT_SETUP.md)
- Accounts: [USERS.md](USERS.md)
- Tests: `.venv\Scripts\python.exe -m pytest` (uses a throwaway database with
  SharePoint disabled; never touches `promanage.db` or Microsoft Graph)
