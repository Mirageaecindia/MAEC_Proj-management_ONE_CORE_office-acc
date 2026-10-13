"""One clock: the app and its tests never read the machine's local date or a naive "now".

Every day in the app is the UTC date (`today_utc` in app/domain/timesheets.py) and every
timestamp is UTC (`datetime.now(UTC)`). A local `date.today()` or naive `datetime.now()`
gives a different day between midnight and 05:30 India time, which has already broken two
tests. This test fails on any new one, in app code or in tests.
"""

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SOURCES = [
    *BACKEND.glob("app/**/*.py"),
    *BACKEND.glob("tests/*.py"),
    *(BACKEND / name for name in ("main.py", "schemas.py", "models.py", "auth.py")),
]
LOCAL_CLOCK = re.compile(r"\bdate\.today\(\)|\bdatetime\.now\(\)|\bdatetime\.utcnow\(\)")
ALLOWED = {"tests/test_clock_hygiene.py"}  # this file names the patterns


def test_nothing_reads_the_local_date_or_a_naive_now():
    offenders = []
    for path in SOURCES:
        relative = path.relative_to(BACKEND).as_posix()
        if relative in ALLOWED:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if LOCAL_CLOCK.search(line):
                offenders.append(f"{relative}:{number}: {line.strip()}")
    assert not offenders, "Use today_utc() or datetime.now(UTC) instead:\n" + "\n".join(offenders)
