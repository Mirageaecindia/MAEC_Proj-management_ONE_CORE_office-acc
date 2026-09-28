# Deploying MAEC ProManage (Docker)

The whole app runs as three containers from [`docker-compose.yml`](../docker-compose.yml).
The server needs **only Docker and git**. Python, Node, Postgres and the web server
all live inside the images, which are built on the server from the code in GitHub.

| Container | Image | What it does | Reachable from |
|---|---|---|---|
| `frontend` | [`frontend/Dockerfile`](../frontend/Dockerfile): Node builds the React app, then Caddy serves it | Serves the web app, forwards `/api/*` to the backend, gets and renews the HTTPS certificate | The internet, ports 80 and 443 |
| `backend` | [`backend/Dockerfile`](../backend/Dockerfile): Python 3.14 + FastAPI/uvicorn | The API. It applies the Alembic migrations each time it starts | The `frontend` container only |
| `db` | `postgres:18-alpine` | The database, kept in the `db-data` volume | The `backend` container only |

```
browser ──HTTPS──► frontend (Caddy) ──/api/*──► backend:8000 ──► db:5432
                     └── everything else: the React app (index.html, /assets)
```

The browser and the API share one origin, so CORS isn't involved. The database and
the API aren't published on any host port.

Target server: a netcup VPS in Vienna. The steps below assume **Ubuntu 24.04** (a
standard netcup image); any Linux that runs Docker works the same.

---

## 1. Before you start

1. **A domain name** for the app, e.g. `promanage.example.com`. At your DNS provider,
   create an **A record** pointing it at the VPS IPv4 address (and an **AAAA** record for
   its IPv6 address, if you use one). HTTPS certificates are issued only after DNS
   points at the server.
2. **SSH access** to the VPS. The netcup Server Control Panel shows the IP and root password.

## 2. Prepare the server (once)

```bash
ssh root@<server-ip>

apt update && apt upgrade -y

# Docker Engine + the compose plugin (official install script)
curl -fsSL https://get.docker.com | sh

# Firewall: SSH and the web ports only
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw enable
```

Docker writes its own firewall rules for the ports it publishes. Only 80 and 443 are
published, so Postgres and the API stay unreachable from outside.

## 3. Get the code

The repository is on GitHub. If it's private, give the server a read-only **deploy key**:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/maec_deploy -N "" -C "maec-server"
cat ~/.ssh/maec_deploy.pub
```

On GitHub, open the repository → **Settings → Deploy keys → Add deploy key**, paste the
key and leave "Allow write access" **off**. Then:

```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile ~/.ssh/maec_deploy
  IdentitiesOnly yes
EOF

git clone git@github.com:Sajjadahmeddd/MAEC_project_management.git /opt/maec
cd /opt/maec
```

## 4. Configure

```bash
cp .env.example .env
chmod 600 .env
openssl rand -hex 32        # paste the output as POSTGRES_PASSWORD
nano .env
```

| Setting | Value |
|---|---|
| `POSTGRES_PASSWORD` | The generated value. Use letters and digits only, because it goes into a URL. Set it **before the first start**: Postgres stores it when it creates the database. |
| `SITE_ADDRESS` | Your domain, e.g. `promanage.example.com`. With `:80` the app runs on plain HTTP by IP address; use that only for a first test. |
| `AZURE_*`, `SHAREPOINT_*` | SharePoint settings; leave them empty until SharePoint is set up. |

**Employee list (optional).** On first start the employees table is seeded from
`backend/data/employee_leads.csv`. That file holds personal data and isn't in git, so
copy it from your PC:

```powershell
scp backend\data\employee_leads.csv root@<server-ip>:/opt/maec/backend/data/
```

## 5. Build and start

```bash
cd /opt/maec
docker compose up -d --build
docker compose ps           # all three should become "healthy" / "running"
```

The first build takes a few minutes. Open `https://<your-domain>`: Caddy fetches the
certificate on the first request, which takes a few seconds.

## 6. Create the accounts

Accounts are never seeded. Create them in the backend container (the password is
prompted for):

```bash
docker compose exec backend python create_user.py --username bu.head --role bu_head --full-name "Your Name"
docker compose exec backend python create_user.py --username lead.anita --role lead --full-name "Anita Kumar" --discipline Electrical
docker compose exec backend python create_user.py --username eng.arjun --role engineer --employee-id 1
```

All options are in [backend/USERS.md](../backend/USERS.md).

## 7. Deploy an update

```bash
cd /opt/maec
git pull
docker compose up -d --build
docker image prune -f       # remove the previous images
```

Only the containers whose code changed are rebuilt and restarted. The backend applies
any new Alembic migrations when it starts. The database and certificates are in volumes,
so they are kept.

## 8. Backups

Take a nightly database dump and keep 14 days of dumps:

```bash
mkdir -p /opt/maec-backups
crontab -e
```

```cron
0 2 * * * cd /opt/maec && docker compose exec -T db pg_dump -U promanage -d promanage -Fc > /opt/maec-backups/promanage-$(date +\%F).dump && find /opt/maec-backups -name '*.dump' -mtime +14 -delete
```

A backup that exists only on the same server doesn't protect against losing the server.
Copy `/opt/maec-backups` somewhere else as well, e.g. pull it to another machine with
`rsync` or `scp`, and use netcup's snapshots.

**Restore** (this replaces the current data):

```bash
cd /opt/maec
docker compose stop backend
docker compose exec -T db pg_restore -U promanage -d promanage --clean --if-exists < /opt/maec-backups/promanage-2026-10-01.dump
docker compose start backend
```

## 9. Day-to-day commands

Run these from `/opt/maec`.

| Task | Command |
|---|---|
| Status | `docker compose ps` |
| Logs (follow) | `docker compose logs -f backend` (or `frontend`, `db`) |
| Restart everything | `docker compose restart` |
| Stop / start | `docker compose down` / `docker compose up -d` (the data is kept) |
| Database shell | `docker compose exec db psql -U promanage -d promanage` |
| Deactivate a leaver | `docker compose exec backend python create_user.py --username eng.arjun --deactivate` |

Logs are rotated automatically: each container keeps at most 5 × 10 MB.

**Never run `docker compose down -v`** on the server. `-v` deletes the volumes, which
means the database and the certificates.

## 10. Troubleshooting

| Symptom | Check |
|---|---|
| The browser shows a certificate error, or the site doesn't load over HTTPS | `docker compose logs frontend`. Usually DNS doesn't point at the server yet, or port 80/443 is blocked. Let's Encrypt must reach port 80 or 443 from the internet. |
| The page loads but login fails with a network error | `docker compose ps`: is `backend` healthy? Then check `docker compose logs backend`. |
| `backend` restarts in a loop | `docker compose logs backend`. A migration error or a wrong `POSTGRES_PASSWORD` shows up there. |
| You changed `POSTGRES_PASSWORD` after the first start | Postgres keeps the original password. Change it back, or change it in the database: `docker compose exec db psql -U promanage -c "ALTER USER promanage PASSWORD '<new>'"`. |

## Local development

Nothing changes for development. The backend uses SQLite, and `npm run dev` points at
`http://localhost:8000` (see the [README](../README.md)). To try the production stack on a
PC with Docker Desktop, create a root `.env` as in step 4 with `SITE_ADDRESS=:80`, then
run `docker compose up -d --build` and open `http://localhost`.

To run the backend tests against Postgres, start an empty, throwaway Postgres and set
`TEST_DATABASE_URL` (the tests wipe every table):

```powershell
docker run -d --rm --name maec-pgtest -e POSTGRES_USER=t -e POSTGRES_PASSWORD=t -e POSTGRES_DB=t -p 55432:5432 postgres:18-alpine
$env:TEST_DATABASE_URL = "postgresql+psycopg://t:t@127.0.0.1:55432/t"; .venv\Scripts\python.exe -m pytest
docker stop maec-pgtest
```
