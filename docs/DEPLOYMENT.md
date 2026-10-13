# Deploying MAEC ProManage (Docker, behind MAEC One)

The app runs as three containers from [`docker-compose.yml`](../docker-compose.yml), compose
project **`maec-pm`**. Nobody signs in to it: **MAEC One Core** does
(`auth.mirageaec.com`), and on every request the backend asks Core who the browser is
([backend/app/api/gate.py](../backend/app/api/gate.py)). The server needs **only Docker and
git**: Python, Node, Postgres and the web server live inside the images, built on the
server from the code in GitHub.

It runs on the VPS **next to** what is already there and changes none of it:

| Stack | Compose project | Host port | Network |
|---|---|---|---|
| Old Project Management (`promanage.mirageaec.com`) | `promanage` | 127.0.0.1:8081 | its own |
| Old Engineering Tools | `maec` | 127.0.0.1:8080 | 172.30.57.0/24 |
| MAEC One Core | `maec-core` | 127.0.0.1:8001 | 10.231.0.0/24, and `maec_core_net` 10.231.1.0/24 |
| New Engineering Tools | `maec-et` | 127.0.0.1:8082 | 10.231.2.0/24 |
| **This stack (`pm.mirageaec.com`)** | **`maec-pm`** | **127.0.0.1:8083** (`PM_PORT`) | **10.231.3.0/24** (`PM_NET_SUBNET`) |

| Container | Image | What it does | Reachable from |
|---|---|---|---|
| `frontend` | `maec-pm-frontend` ([`frontend/Dockerfile`](../frontend/Dockerfile)): Node builds the React app, then Caddy serves it on plain HTTP | Serves the web app, forwards `/api/*` to the backend with the host's `X-Forwarded-Proto`/`-Host` | The host's Caddy, through 127.0.0.1:8083 |
| `backend` | `maec-pm-backend` ([`backend/Dockerfile`](../backend/Dockerfile)): Python 3.14 + FastAPI/uvicorn | The API. Asks Core about every request; applies the Alembic migrations each time it starts | `frontend` (on `maec_pm_net`); Core (on `maec_core_net`) |
| `db` | `postgres:18-alpine`, volume `maec-pm_db` | The database. Never the old stack's volume | `backend` only |

```
browser ─HTTPS─► host Caddy ─► 127.0.0.1:8083 ─► frontend (Caddy, HTTP) ─/api/*─► backend:8000 ─► db:5432
                 (TLS for pm.mirageaec.com)                                          │
                                                        maec_core_net: GET http://maec-core:8000/api/gate/check
```

Core's session cookie (`maec_one_session`) is set for `.mirageaec.com`, so the browser sends it
to `pm.mirageaec.com` by itself. The browser and the API share one origin, so CORS isn't
involved. Nothing in this stack publishes 80 or 443.

**Every compose command for this stack passes the settings file explicitly**, from its folder:
`docker compose -f docker-compose.yml --env-file .env ...`. No `docker-compose.override.yml` is
needed on the server, and none should exist there.

---

## 1. Before you start

1. **MAEC One Core is running** (its `deploy/RUNBOOK.md`), and the shared network exists:
   `docker network inspect maec_core_net` answers. This stack joins it and never creates it.
2. **Core knows Project Management**: its seed registers the application `projects`. Making
   it live with `base_url` `https://pm.mirageaec.com`, and adding `projects=<secret>` to Core's
   `GATE_SECRETS`, are the last steps of Core's runbook ("Make Project Management live").
3. **The port and range are free**: nothing listens on 8083, and no Docker network uses
   10.231.3.0/24:
   `docker network inspect $(docker network ls -q) --format '{{.Name}} {{range .IPAM.Config}}{{.Subnet}}{{end}}'`
4. **DNS**: an A record for `pm.mirageaec.com` pointing at the VPS.

## 2. Get the code

A folder of its own, never the old stack's:

```bash
git clone --branch gate-client git@github.com:Sajjadahmeddd/MAEC_project_management.git /opt/maec-pm
cd /opt/maec-pm
```

## 3. Configure

```bash
cp .env.example .env
chmod 600 .env
openssl rand -hex 32                                            # POSTGRES_PASSWORD
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # MAEC_GATE_SECRET
nano .env
```

| Setting | Value |
|---|---|
| `POSTGRES_PASSWORD` | The generated value; letters and digits only, because it goes into a URL. Set it **before the first start**: Postgres stores it when it creates the database. |
| `CORE_URL` | `http://maec-core:8000` (Core inside Docker; the check never leaves the machine) |
| `CORE_PUBLIC_URL` | `https://auth.mirageaec.com` (where Sign out and Change password point) |
| `MAEC_APP_KEY` | `projects` |
| `MAEC_GATE_SECRET` | The generated value; the same one goes into Core's `GATE_SECRETS` as `projects=<value>`. At least 32 characters; the backend refuses to start with the placeholder. |
| `AZURE_*`, `SHAREPOINT_*` | SharePoint settings, as for the old stack. |
| `PM_PORT`, `PM_NET_SUBNET` | Leave unset: the defaults (8083, 10.231.3.0/24) are the VPS's values. |

## 4. The data

Copy the old stack's database into this one, read-only on the old side, with
[`deploy/RUNBOOK-PM.md`](../deploy/RUNBOOK-PM.md). It also renames the two plain BU Head usernames
to their MAEC One emails (in the copy only) and applies this stack's migration.

## 5. Build and start

```bash
cd /opt/maec-pm
docker compose -f docker-compose.yml --env-file .env up -d --build
docker compose -f docker-compose.yml --env-file .env ps
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8083/api/auth/me
```

All three containers should become healthy / running. The `curl` answering `401` means the whole
chain works (frontend, backend, Core: "not signed in"); `503` means the backend can't reach Core:
check `maec_core_net` and `CORE_URL`. The backend refuses to start without the four gate
settings, and its log names what is missing.

## 6. The host's Caddy

Add a block for the new name next to the existing ones (keep a dated copy of the Caddyfile
first, as in Core's runbook). `promanage.mirageaec.com` is not touched.

```
pm.mirageaec.com {
	reverse_proxy 127.0.0.1:8083
}
```

Caddy sets `X-Forwarded-Proto: https` and `X-Forwarded-Host: pm.mirageaec.com`; this stack's
frontend passes them on, and the backend believes them only from its own network, so it tells
Core the address the browser used.

## 7. Deploy an update

```bash
cd /opt/maec-pm
git pull
docker compose -f docker-compose.yml --env-file .env up -d --build
docker image prune -f
```

The backend applies any new Alembic migrations when it starts. The database is in its volume,
so it is kept. `docker image prune -f` removes the previous images.

## 8. Backups

Create `/opt/maec-pm-backups` first (`mkdir -p`, `chmod 700`): the dumps hold everyone's work.

```cron
0 2 * * * cd /opt/maec-pm && docker compose -f docker-compose.yml --env-file .env exec -T db pg_dump -U promanage -d promanage -Fc > /opt/maec-pm-backups/promanage-$(date +\%F).dump && find /opt/maec-pm-backups -name '*.dump' -mtime +14 -delete
```

A backup only on the same server doesn't protect against losing the server: copy it elsewhere too.

**Restore** (replaces the current data):

```bash
cd /opt/maec-pm
docker compose -f docker-compose.yml --env-file .env stop backend
docker compose -f docker-compose.yml --env-file .env exec -T db pg_restore -U promanage -d promanage --clean --if-exists < /opt/maec-pm-backups/promanage-2026-10-01.dump
docker compose -f docker-compose.yml --env-file .env start backend
```

## 9. Day-to-day

Run these from `/opt/maec-pm`:

| Task | Command or place |
|---|---|
| Status | `docker compose -f docker-compose.yml --env-file .env ps` |
| Logs (follow) | `docker compose -f docker-compose.yml --env-file .env logs -f backend` |
| Database shell | `docker compose -f docker-compose.yml --env-file .env exec db psql -U promanage -d promanage` |
| Someone has no access, or forgot their password | MAEC One: sign-in, access (a seat) and passwords are managed there |
| Someone has a seat but "no profile" | A BU Head adds them under People (Add one person) |

**Never run `docker compose down -v`** here: `-v` deletes the volume, which is the database.

## 10. Troubleshooting

| Symptom | Check |
|---|---|
| Every page says "Project Management is unavailable"; the API answers 503 | The backend can't reach Core: the backend's logs, `docker network inspect maec_core_net`, `CORE_URL`. |
| The API answers 403 `bad_app` | `MAEC_APP_KEY` / `MAEC_GATE_SECRET` don't match Core's `GATE_SECRETS`, or `projects` isn't live in Core. |
| After signing in, the browser lands on Core's launcher instead of the app | Core's `projects` `base_url` isn't `https://pm.mirageaec.com`, or the forwarded headers didn't arrive (the host's Caddy block). |
| `backend` restarts in a loop | Its logs: a missing gate setting, a migration error or a wrong `POSTGRES_PASSWORD` shows up there. |

## Local development

Run MAEC One Core locally at `http://auth.maec.local:8000` (its README), with
`SESSION_COOKIE_DOMAIN=.maec.local` and `GATE_SECRETS=projects=<secret>`, and the `projects`
application live with `base_url` `http://pm.maec.local:5173`. Add `auth.maec.local` and
`pm.maec.local` to the hosts file as `127.0.0.1`. Then run the backend as in the
[README](../README.md), with the gate settings in `backend/.env` (see `backend/.env.example`),
and `npm run dev`, opened at `http://pm.maec.local:5173` (never `localhost`: Core's cookie is
set for `.maec.local`). Vite forwards `/api` to the backend.

To run the backend tests against Postgres, start an empty, throwaway Postgres and set
`TEST_DATABASE_URL` (the tests wipe every table; Core is faked in-process):

```powershell
docker run -d --rm --name maec-pgtest -e POSTGRES_USER=t -e POSTGRES_PASSWORD=t -e POSTGRES_DB=t -p 15433:5432 postgres:18-alpine
$env:TEST_DATABASE_URL = "postgresql+psycopg://t:t@127.0.0.1:15433/t"; .venv\Scripts\python.exe -m pytest
docker stop maec-pgtest
```
