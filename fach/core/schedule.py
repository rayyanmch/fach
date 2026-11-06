"""Zeitplan-Rechnung ohne Betriebssystem: Wann ist der nächste automatische Abgleich?"""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta

from .config import Schedule

_TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def parse_time(value: str) -> time:
    m = _TIME.match(value.strip())
    if not m:
        raise ValueError(f"Ungültige Uhrzeit: {value!r}")
    return time(int(m.group(1)), int(m.group(2)))


def validate(s: Schedule) -> Schedule:
    days = sorted({int(d) for d in s.days if 0 <= int(d) <= 6})
    times = sorted({parse_time(t).strftime("%H:%M") for t in s.times})[:4]
    spread = max(0, min(60, int(s.spread_min)))
    return Schedule(enabled=bool(s.enabled) and bool(days) and bool(times), days=days, times=times or ["07:00"],
                    spread_min=spread)


def next_run(s: Schedule, now: datetime) -> datetime | None:
    if not s.enabled or not s.days or not s.times:
        return None
    slots = sorted(parse_time(t) for t in s.times)
    for offset in range(8):
        day = (now + timedelta(days=offset)).date()
        if day.weekday() not in s.days:
            continue
        for t in slots:
            candidate = datetime.combine(day, t)
            if candidate > now:
                return candidate
    return None
