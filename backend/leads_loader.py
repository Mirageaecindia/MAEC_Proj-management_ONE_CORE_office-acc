import csv
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

CSV_PATH = Path(__file__).parent / "data" / "employee_leads.csv"
DISCIPLINE_VALUES = ("electrical", "mechanical", "bim")

_cache_lock = threading.Lock()
_cached_mtime: float | None = None
_cached_leads: list[dict[str, str]] = []


def _normalise(value: str | None) -> str:
    return " ".join((value or "").split()).casefold()


def _discipline_for_designation(designation: str) -> str | None:
    normalised = _normalise(designation)
    if "elect" in normalised or "electrical" in normalised:
        return "electrical"
    if "lead - bim" in normalised or "bim modeller" in normalised or ("bim" in normalised and "mech" not in normalised):
        return "bim"
    if "mechanical" in normalised or "lead - mech" in normalised or "mech" in normalised:
        return "mechanical"
    return None


def _parse_csv_file(csv_path: Path) -> list[dict[str, str]]:
    leads: list[dict[str, str]] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        required_columns = {"Emp No", "Emp Name", "Designation"}
        if not reader.fieldnames or not required_columns.issubset(reader.fieldnames):
            logger.warning(
                "Skipping lead import: CSV must contain columns %s; found %s",
                sorted(required_columns),
                reader.fieldnames,
            )
            return leads

        seen_names = set()
        for row_number, row in enumerate(reader, start=2):
            employee_number = (row.get("Emp No") or "").strip()
            name = (row.get("Emp Name") or "").strip()
            designation = (row.get("Designation") or "").strip()
            discipline = _discipline_for_designation(designation)
            if not employee_number or not name or not designation:
                continue
            if discipline is None:
                continue
            name_key = _normalise(name)
            if name_key in seen_names:
                continue
            seen_names.add(name_key)
            leads.append(
                {
                    "name": name,
                    "title": designation,
                    "discipline": discipline,
                }
            )
    return leads


def get_or_reload_leads(csv_path: Path = CSV_PATH) -> tuple[list[dict[str, str]], bool]:
    """
    Check the file's last-modified timestamp.
    If the file has been modified since the last load, re-read the file and update the in-memory cache.
    If it hasn't changed or if reading fails due to file locking/saving, serve the cached data.
    Returns (leads, reloaded_bool).
    """
    global _cached_mtime, _cached_leads

    with _cache_lock:
        if not csv_path.exists():
            logger.warning("Lead CSV not found at %s; serving %d cached leads", csv_path, len(_cached_leads))
            return list(_cached_leads), False

        try:
            current_mtime = csv_path.stat().st_mtime
        except OSError as err:
            logger.warning("Could not check employee leads file mtime (%s); serving %d cached leads", err, len(_cached_leads))
            return list(_cached_leads), False

        # If already loaded and file has not been modified, return cached data
        if _cached_mtime is not None and current_mtime <= _cached_mtime:
            return list(_cached_leads), False

        # File is new or has been modified -> attempt reload
        try:
            new_leads = _parse_csv_file(csv_path)
            # Guard against temporary empty/partially written file during active Excel save
            if not new_leads and _cached_leads:
                logger.warning(
                    "Employee leads file returned 0 rows while saving/locked; retaining %d cached rows",
                    len(_cached_leads),
                )
                return list(_cached_leads), False

            _cached_leads = new_leads
            _cached_mtime = current_mtime
            logger.info("Reloaded employee leads from file, %d rows found", len(_cached_leads))
            print(f"[leads_loader] Reloaded employee leads from file, {len(_cached_leads)} rows found", flush=True)
            return list(_cached_leads), True
        except (PermissionError, OSError) as err:
            logger.warning(
                "Employee leads file is temporarily locked or being written (%s); serving %d cached leads",
                err,
                len(_cached_leads),
            )
            return list(_cached_leads), False


def load_leads(csv_path: Path = CSV_PATH) -> list[dict[str, str]]:
    leads, _ = get_or_reload_leads(csv_path)
    return leads


load_electrical_leads = load_leads
