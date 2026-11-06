"""„Semester-Takt“: Wann hat welcher Kurs Material hochgeladen? Woche für Woche.

Quelle sind die Dateien selbst: PFERD setzt das Änderungsdatum auf das Upload-Datum aus ILIAS.
So steht die Zeitleiste schon nach dem ersten Abgleich komplett da – ohne eigene Historie.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path

from ..core.config import AppConfig
from ..core.university import University, lecture_week, semester_for

MAX_FILES_PER_COURSE = 5000


def _walk(root: Path):
    stack = [root]
    seen = 0
    while stack and seen < MAX_FILES_PER_COURSE:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    if entry.name.startswith(".") or entry.name.startswith("~$"):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        seen += 1
                        yield entry
        except OSError:
            continue


def semester_timeline(cfg: AppConfig, uni: University, today: date | None = None) -> dict:
    today = today or date.today()
    sem = semester_for(uni, today)
    monday0 = sem.lectures_start - timedelta(days=sem.lectures_start.weekday())
    weeks = (sem.lectures_end - monday0).days // 7 + 1
    current = lecture_week(sem, today)

    courses = []
    for course in cfg.enabled_courses():
        counts = [0] * weeks
        before = total = size = 0
        last = 0.0
        for entry in _walk(cfg.target_path / course.folder):
            try:
                st = entry.stat()
            except OSError:
                continue
            total += 1
            size += st.st_size
            last = max(last, st.st_mtime)
            d = datetime.fromtimestamp(st.st_mtime).date()
            idx = (d - monday0).days // 7
            if idx < 0:
                before += 1
            elif idx < weeks:
                counts[idx] += 1
        courses.append({"id": course.id, "counts": counts, "before": before, "total": total,
                        "bytes": size, "last": last or None})

    return {
        "semester": sem.name,
        "estimated": sem.estimated,
        "lectures_start": sem.lectures_start.isoformat(),
        "lectures_end": sem.lectures_end.isoformat(),
        "week_starts": [(monday0 + timedelta(weeks=i)).isoformat() for i in range(weeks)],
        "current_week": current,
        "today_index": (today - monday0).days // 7,
        "courses": courses,
    }
