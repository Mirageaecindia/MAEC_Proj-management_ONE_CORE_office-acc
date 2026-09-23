"""Month bucketing used by the planned-vs-consumed charts."""

from datetime import date


def month_key(value: date) -> str:
    """YYYY-MM key for monthly grouping."""
    return value.strftime("%Y-%m")


def month_label(key: str) -> str:
    """'2026-09' -> 'Sep 2026' (falls back to the key if it is malformed)."""
    try:
        year, month = map(int, key.split("-"))
        return date(year, month, 1).strftime("%b %Y")
    except ValueError:
        return key


def distribute_hours_over_months(
    total_hours: float, start_date: date | None, end_date: date | None
) -> dict[str, float]:
    """Spread hours evenly over every calendar month from start to end (inclusive)."""
    if not start_date or not end_date or total_hours <= 0:
        return {}
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    months = []
    current = date(start_date.year, start_date.month, 1)
    end_month = date(end_date.year, end_date.month, 1)
    while current <= end_month:
        months.append(current)
        current = date(current.year + 1, 1, 1) if current.month == 12 else date(current.year, current.month + 1, 1)

    hours_per_month = round(total_hours / len(months), 2)
    return {month_key(month_start): hours_per_month for month_start in months}
