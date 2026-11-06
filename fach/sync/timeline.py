"""„Semester-Takt“ und Speicher: Wann hat welcher Kurs was hochgeladen, und wie viel Platz belegt es?

Quelle sind die Dateien selbst: PFERD setzt das Änderungsdatum auf das Upload-Datum aus ILIAS.
So steht die Zeitleiste schon nach dem ersten Abgleich komplett da – ohne eigene Historie.
"""

from __future__ import annotations

import os
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

from ..core.config import AppConfig
from ..core.university import University, lecture_week, semester_for

MAX_FILES_PER_COURSE = 5000
NAMES_PER_WEEK = 4


def walk_files(root: Path):
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
    total_bytes = total_files = 0
    for course in cfg.courses:
        counts = [0] * weeks
        week_bytes = [0] * weeks
        week_names: list[list[tuple[float, str]]] = [[] for _ in range(weeks)]
        weekdays = [0] * 7
        before = total = size = 0
        last = 0.0
        exts: dict[str, int] = {}
        for entry in walk_files(cfg.target_path / course.folder):
            try:
                st = entry.stat()
            except OSError:
                continue
            total += 1
            size += st.st_size
            last = max(last, st.st_mtime)
            ext = os.path.splitext(entry.name)[1].lower().lstrip(".") or "andere"
            exts[ext] = exts.get(ext, 0) + 1
            stamp = datetime.fromtimestamp(st.st_mtime)
            weekdays[stamp.weekday()] += 1
            idx = (stamp.date() - monday0).days // 7
            if idx < 0:
                before += 1
            elif idx < weeks:
                counts[idx] += 1
                week_bytes[idx] += st.st_size
                week_names[idx].append((st.st_mtime, entry.name))
        names = [[n for _, n in sorted(w, reverse=True)[:NAMES_PER_WEEK]] for w in week_names]
        total_bytes += size
        total_files += total
        courses.append({"id": course.id, "counts": counts, "bytes_by_week": week_bytes, "names": names,
                        "before": before, "total": total, "bytes": size, "last": last or None,
                        "weekdays": weekdays, "types": dict(sorted(exts.items(), key=lambda kv: -kv[1])[:4])})

    try:
        disk = shutil.disk_usage(cfg.target_path if cfg.target_path.exists() else cfg.target_path.anchor or "/")
        free, capacity = disk.free, disk.total
    except OSError:
        free = capacity = None

    return {
        "semester": sem.name,
        "estimated": sem.estimated,
        "lectures_start": sem.lectures_start.isoformat(),
        "lectures_end": sem.lectures_end.isoformat(),
        "week_starts": [(monday0 + timedelta(weeks=i)).isoformat() for i in range(weeks)],
        "current_week": current,
        "today_index": (today - monday0).days // 7,
        "courses": courses,
        "storage": {"bytes": total_bytes, "files": total_files, "free": free, "capacity": capacity},
    }
