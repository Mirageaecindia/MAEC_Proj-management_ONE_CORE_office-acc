"""Back up the SQLite database and keep the newest copies. Run from the backend directory.

Safe while the server is running: it uses SQLite's online backup API, which
takes a consistent snapshot (WAL included), unlike copying the .db file.

    .venv\\Scripts\\python.exe backup_db.py                 (backups\\, keeps the newest 14)
    .venv\\Scripts\\python.exe backup_db.py --keep 30 --dir D:\\maec-backups

Nightly, with Windows Task Scheduler (one-time setup, adjust the paths):
    schtasks /Create /SC DAILY /ST 23:00 /TN "MAEC DB backup" ^
        /TR "C:\\path\\to\\backend\\.venv\\Scripts\\python.exe C:\\path\\to\\backend\\backup_db.py"

Restore: stop the server, copy the chosen backup over the database file
(promanage.db by default), delete any promanage.db-wal / -shm files next to it,
then start the server.
"""

import argparse
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import BACKEND_DIR, get_settings


def database_path() -> Path:
    url = make_url(get_settings().database_url)
    if url.get_backend_name() != "sqlite" or not url.database:
        raise SystemExit("backup_db.py only backs up a SQLite file database.")
    return Path(url.database).resolve()


def backup(db_path: Path, backup_dir: Path, keep: int) -> Path:
    """Snapshot `db_path` into `backup_dir` and delete all but the newest `keep` snapshots."""
    if keep < 1:
        raise SystemExit("--keep must be at least 1.")
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"{db_path.stem}-{datetime.now(UTC):%Y%m%dT%H%M%S%fZ}.db"
    with closing(sqlite3.connect(db_path)) as source, closing(sqlite3.connect(target)) as copy:
        source.backup(copy)
    # Timestamped names sort chronologically.
    for old in sorted(backup_dir.glob(f"{db_path.stem}-*.db"))[:-keep]:
        old.unlink()
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up the MAEC SQLite database.")
    parser.add_argument("--dir", type=Path, default=BACKEND_DIR / "backups", help="Backup folder.")
    parser.add_argument("--keep", type=int, default=14, help="How many backups to keep (default 14).")
    args = parser.parse_args()
    print(f"Backed up to {backup(database_path(), args.dir, args.keep)}")


if __name__ == "__main__":
    main()
