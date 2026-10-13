# Runbook: Project Management's data in the new stack (maec-pm)

For the person on the VPS. It copies the live database of the **old** Project Management
(compose project `promanage`, `promanage.mirageaec.com`) into the **new** stack's own
database (compose project `maec-pm`, volume `maec-pm_db`), renames two usernames in the copy
to match MAEC One, and applies the new stack's migration (`users.core_user_id`).

- The old stack is **never stopped and never written to**. Its database is only read, by
  `pg_dump` in a read-only transaction.
- The dump goes straight through a pipe from the old database into the new one: no file is
  written, so there is nothing to shred.
- No secret appears in any command: each container uses its own credentials.

Every command below has its explanation under it. Run them in order.

Before you start: the new stack is cloned and configured as in
[docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md) (sections 1 to 3), with its `.env` filled in.

---

## 1. Find the old database, and check the new one is empty

```bash
cd /opt/maec-pm
```
```
# The new stack's folder. Every docker compose command below runs from here and passes
# --env-file .env. The old stack is reached with plain `docker exec`, by its container.
```

```bash
docker ps --filter label=com.docker.compose.project=promanage --format '{{.Names}}  {{.Image}}  {{.Status}}'
```
```
# Lists the old stack's containers. Note the one whose image is postgres: that is
# <OLD_DB> below (with the old compose file it is promanage-db-1). The old stack keeps
# running throughout; nothing here stops it.
```

```bash
OLD_DB=promanage-db-1
```
```
# Puts the name you noted into a variable for the commands below. Change it if yours differs.
```

```bash
docker exec "$OLD_DB" psql -U promanage -d promanage -Atc "SELECT count(*) FROM users"
```
```
# Asks the old database how many accounts it holds: a read, nothing else. Expect 61 (the
# count MAEC One's import expects). Write the number down. If psql says the role or the
# database doesn't exist, the old stack uses other names: stop and find out which.
```

```bash
docker compose -f docker-compose.yml --env-file .env up -d db
```
```
# Starts ONLY the new stack's database (volume maec-pm_db), empty on the first run. The
# backend stays down: on start it would create empty tables, and the copy must go first.
```

```bash
docker compose -f docker-compose.yml --env-file .env exec -T db psql -U promanage -d promanage -Atc "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'"
```
```
# Counts the tables in the new database. Must print 0. Anything else means it already
# holds data: for a repeat, follow section 5 first; otherwise stop and find out why.
```

## 2. Copy the old database into the new one

```bash
docker exec -e PGOPTIONS='-c default_transaction_read_only=on' "$OLD_DB" pg_dump -U promanage -d promanage --format=custom --no-owner --no-privileges | docker compose -f docker-compose.yml --env-file .env exec -T db pg_restore -U promanage -d promanage --no-owner --no-privileges --exit-on-error
```
```
# Reads the whole old database in one consistent, read-only snapshot and streams it into
# the new database. Nothing is written to disk, and the old database cannot be changed:
# every transaction in that pg_dump session is read-only. It prints nothing when it works.
# Any error stops it (--exit-on-error): then empty the new database (section 5, step 2)
# and run this again.
```

```bash
docker compose -f docker-compose.yml --env-file .env exec -T db psql -U promanage -d promanage -Atc "SELECT count(*) FROM users"
```
```
# Counts the accounts in the copy. Must be the number you wrote down in section 1.
```

## 3. Rename the two plain BU Head usernames, in the copy only

MAEC One's import turned `bu.anitha` and `bu.mohan` into their `@mirageaec.com` addresses.
The copy must match, so these two people are linked to their MAEC One accounts at their first
visit. Nothing else is renamed, and the old database still has the old names.

```bash
docker compose -f docker-compose.yml --env-file .env exec -T db psql -U promanage -d promanage -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;
UPDATE users SET username = 'bu.anitha@mirageaec.com' WHERE username = 'bu.anitha';
UPDATE users SET username = 'bu.mohan@mirageaec.com' WHERE username = 'bu.mohan';
DO $$
BEGIN
  IF (SELECT count(*) FROM users WHERE username IN ('bu.anitha@mirageaec.com', 'bu.mohan@mirageaec.com')) <> 2 THEN
    RAISE EXCEPTION 'expected exactly the two renamed accounts: nothing was changed';
  END IF;
END $$;
COMMIT;
SQL
```
```
# Renames the two accounts in one transaction. Must print, in order: BEGIN, UPDATE 1,
# UPDATE 1, DO, COMMIT. If either says UPDATE 0, or the check raises its error, psql stops
# before COMMIT and nothing is changed: stop and look (has it been run already? see
# section 5). The unique index on users.username refuses the rename if either address is
# already taken by another account.
```

## 4. Start the new stack: the migration runs, then check

```bash
docker compose -f docker-compose.yml --env-file .env up -d --build
```
```
# Builds and starts the backend and frontend. The backend refuses to start without MAEC
# One's gate settings in .env; when it starts it applies the new migration (0023:
# users.core_user_id) to the copy. Wait until `ps` below shows it healthy.
```

```bash
docker compose -f docker-compose.yml --env-file .env ps
```
```
# All three containers: running, backend and db "healthy". If the backend restarts in a
# loop, `docker compose -f docker-compose.yml --env-file .env logs backend` says why.
```

```bash
docker compose -f docker-compose.yml --env-file .env exec -T db psql -U promanage -d promanage -Atc "SELECT version_num FROM alembic_version"
```
```
# The schema version of the copy. Must print 0023.
```

```bash
docker compose -f docker-compose.yml --env-file .env exec -T db psql -U promanage -d promanage -Atc "SELECT count(*) AS accounts, count(core_user_id) AS linked FROM users"
```
```
# The accounts, and how many are already linked to MAEC One. Must print the number from
# section 1, then 0: each person is linked by email at their first visit.
```

```bash
for table in projects wbs_nodes resource_bookings time_log_entries audit_events; do printf '%-18s old %-8s new %s\n' "$table" "$(docker exec "$OLD_DB" psql -U promanage -d promanage -Atc "SELECT count(*) FROM $table")" "$(docker compose -f docker-compose.yml --env-file .env exec -T db psql -U promanage -d promanage -Atc "SELECT count(*) FROM $table")"; done
```
```
# Compares the row counts of the main tables, old against new. They must be equal (the old
# side may be a few rows ahead if people kept working during the copy: that is expected,
# and section 5 takes a fresh copy at switch-over).
```

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8083/api/auth/me
```
```
# Asks the new stack who an anonymous browser is. Must print 401: the request went
# frontend -> backend -> MAEC One, and MAEC One said "not signed in". 503 means the backend
# cannot reach MAEC One (maec_core_net, CORE_URL).
```

The copy is a **test copy** until switch-over: people keep working on
`promanage.mirageaec.com`, and anything done in the new stack meanwhile is thrown away by the
fresh copy below.

## 5. At switch-over: a fresh copy that replaces the test copy

Repeat the copy with the data as it is at that moment. Ask people to stop using
`promanage.mirageaec.com` for these few minutes (the old stack itself is not stopped).

```bash
docker compose -f docker-compose.yml --env-file .env stop backend frontend
```
```
# Stops the NEW stack's backend and frontend, so nothing writes to the test copy while it
# is replaced. The old stack is not touched.
```

```bash
docker compose -f docker-compose.yml --env-file .env exec -T db psql -U promanage -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE promanage WITH (FORCE)" -c "CREATE DATABASE promanage OWNER promanage"
```
```
# Empties the NEW database by dropping and recreating it: the test copy, and anything done
# in it, is gone. Prints DROP DATABASE and CREATE DATABASE. Run it in /opt/maec-pm only:
# the old stack's database lives in another container and is never named here.
```

```bash
docker compose -f docker-compose.yml --env-file .env exec -T db psql -U promanage -d promanage -Atc "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'"
```
```
# Must print 0: the new database is empty again.
```

Then run **section 1** from `docker exec "$OLD_DB" psql ... count(*) FROM users` (write the
new number down), **section 2**, **section 3** and **section 4** again, exactly as before. The
fresh copy replaces the test copy.
