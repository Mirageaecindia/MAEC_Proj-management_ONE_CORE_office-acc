# MAEC Create Project API

## Run locally

```powershell
cd ..
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
uvicorn backend.main:app --reload
```

The default SQLite database is `promanage.db` in the `backend/` directory. Set `DATABASE_URL` to a SQLAlchemy-compatible Postgres URL when deploying to Postgres.