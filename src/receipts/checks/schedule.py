"""Schedule check: the schedule must be preserved and must not hit a DST gap or overlap."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..config import Settings
from ..models import CheckResult, Status, Translation

NAME = "schedule"
_HEADER = re.compile(r"^#\s*(schedule|tz):\s*(.+?)\s*$", re.M)


def source_schedule(source: str) -> tuple[str | None, str | None]:
    found = {k: v for k, v in _HEADER.findall(source)}
    return found.get("schedule"), found.get("tz")


def _ints(field: str) -> list[int] | None:
    parts = field.split(",")
    return [int(p) for p in parts] if all(p.isdigit() for p in parts) else None


def dst_issues(hour: int, minute: int, tz: str, year: int) -> set[str]:
    """Return {'skipped','repeated'} for any day of `year` on which this local time misbehaves."""
    zone, issues, day = ZoneInfo(tz), set(), date(year, 1, 1)
    while day.year == year:
        naive = datetime(year, day.month, day.day, hour, minute)
        aware = naive.replace(tzinfo=zone)
        if aware.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != naive:
            issues.add("skipped")
        elif aware.replace(fold=0).utcoffset() != aware.replace(fold=1).utcoffset():
            issues.add("repeated")
        day += timedelta(days=1)
    return issues


def check(source: str, t: Translation, cfg: Settings) -> CheckResult:
    cron, tz = source_schedule(source)
    if not cron or not tz:
        return CheckResult(NAME, Status.NEEDS_INFO, "source declares no schedule/tz header")
    if (t.cron.strip(), t.tz.strip()) != (cron, tz):
        return CheckResult(NAME, Status.FAIL, "schedule or timezone changed during migration")
    fields = cron.split()
    if len(fields) != 5:
        return CheckResult(NAME, Status.NEEDS_INFO, "unsupported cron expression")
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return CheckResult(NAME, Status.NEEDS_INFO, f"unknown timezone {tz!r}")
    minutes, hours = _ints(fields[0]), _ints(fields[1])
    if minutes is None or hours is None:
        return CheckResult(NAME, Status.PASS, "interval schedule; DST impact negligible")
    found: set[str] = set()
    for h in hours:
        for m in minutes:
            found |= dst_issues(h, m, tz, date.today().year)
    if found:
        return CheckResult(NAME, Status.NEEDS_INFO,
                           f"local time in {tz} is {' and '.join(sorted(found))} on DST change days; "
                           "confirm intended behavior or use UTC")
    return CheckResult(NAME, Status.PASS, "schedule preserved; no DST gap or overlap")
