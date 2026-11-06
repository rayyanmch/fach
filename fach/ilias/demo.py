"""Demo-ILIAS: zum Ausprobieren der Oberfläche ohne Uni-Zugang (python -m fach --demo).

Jede Kennung funktioniert, außer das Passwort ist „falsch“ (zeigt den Fehlerfall).
Der Abgleich legt kleine Platzhalter-PDFs an – mit realistischen Namen und Upload-Daten.
"""

from __future__ import annotations

import asyncio
import os
import random
from datetime import datetime, timedelta
from pathlib import Path

from ..core.config import Course
from .discover import course_id_from_url
from .models import AuthFailed, CourseResult, FoundCourse, IliasError, ProgressFn

_COURSES = [
    ("crs_6999275", "Mathematik für Studierende der Informatik I (WiSe 2026/27)"),
    ("crs_6999276", "Übung zu Mathematik für Studierende der Informatik I (WiSe 2026/27)"),
    ("crs_6997658", "Softwaretechnik (WiSe 2026/27)"),
    ("crs_6996734", "Visualisierung (WiSe 2026/27)"),
    ("crs_6997182", "Information Systems Management (WiSe 2026/27)"),
    ("crs_6999750", "Grundlagen der Betriebswirtschaftslehre (WiSe 2026/27)"),
    ("crs_6612001", "Algorithmen und Datenstrukturen (SoSe 2026)"),
]

# (Ordner, Dateiname, Wochentag des Uploads relativ zum Vorlesungsbeginn) – grob wie ein echtes Semester
_PLAN: dict[str, list[tuple[str, str, int]]] = {
    "crs_6997658": [("Vorlesung", f"{i:02d}_{n}.pdf", 1 + 7 * (i - 1)) for i, n in enumerate(
        ["Introduction", "Requirements", "Modelling_UML", "Architecture_I", "Architecture_II",
         "Version Control with git", "Testing", "Design Patterns"], 1)]
        + [("Übungen/Folien", f"SSE_Exercise{i:02d}.pdf", 8 + 7 * (i - 1)) for i in range(1, 6)],
    "crs_6999275": [("Vorlesung", f"Kapitel_{i}_{n}.pdf", 2 + 7 * (i - 1)) for i, n in enumerate(
        ["Aussagenlogik", "Mengenlehre", "Beweisverfahren", "Relationen", "Komplexe_Zahlen"], 1)]
        + [("Mitschriften", f"Mitschrift_VL{i:02d}.pdf", 3 + 7 * (i - 1)) for i in range(1, 7)],
    "crs_6999276": [("Übungsblätter", f"Blatt_{i:02d}.pdf", 0 + 7 * (i - 1)) for i in range(1, 7)]
        + [("Übungsblätter", f"Blatt_{i:02d}_Lösung.pdf", 9 + 7 * (i - 1)) for i in range(1, 5)],
    "crs_6996734": [("Vorlesungsfolien", f"VIS_{i:02d}.pdf", 3 + 14 * (i - 1)) for i in range(1, 4)],
    "crs_6997182": [(f"2026-10-{14 + 7 * (i - 1):02d}, 10:00 - 11:30: ISM - Vorlesung", f"ISM_Lecture_{i}.pdf",
                     2 + 7 * (i - 1)) for i in range(1, 3)]
        + [("Material", f"ISM_Lecture_{i}.pdf", 2 + 7 * (i - 1)) for i in range(3, 6)],
    "crs_6999750": [(f"Woche {i}/Vorlesung", f"BWL_Woche_{i}_Folien.pdf", 0 + 7 * (i - 1)) for i in range(1, 6)]
        + [(f"Woche {i}/Übung", f"BWL_Fall_Woche_{i}.pdf", 1 + 7 * (i - 1)) for i in range(1, 6)]
        + [(f"Woche {i}/Begleittext", f"Begleittext_Kapitel_{i}.pdf", 0 + 7 * (i - 1)) for i in range(1, 5)],
}

_PDF = b"%PDF-1.4\n% Fach Demo\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


class DemoIlias:
    # In diesen Kursen hält die Demo beim ersten Abgleich die zwei jüngsten Dateien zurück –
    # so findet „Jetzt abgleichen“ danach etwas Neues.
    HOLD_BACK = ("crs_6997658", "crs_6999750")

    def __init__(self, lectures_start: datetime | None = None):
        self.start = lectures_start or datetime(2026, 10, 12, 9, 0)

    async def reachable(self, timeout: float = 8.0) -> bool:
        return True

    async def discover(self, username: str, password: str, fresh_login: bool = False) -> list[FoundCourse]:
        await asyncio.sleep(0.9)
        if password == "falsch":
            raise AuthFailed("Kennung oder Passwort stimmen nicht.")
        return [FoundCourse(cid, title, f"https://ilias.example/goto.php/crs/{cid[4:]}") for cid, title in _COURSES]

    async def resolve(self, username: str, password: str, url: str) -> FoundCourse:
        cid = course_id_from_url(url)
        if not cid:
            raise IliasError("Das sieht nicht nach einem Kurs-Link aus. Kopiere den Link aus der Adresszeile des Kurses.")
        await asyncio.sleep(0.4)
        return FoundCourse(cid, f"Kurs {cid.split('_')[1]}", url)

    def _due(self, course_id: str) -> list[tuple[str, str, datetime]]:
        now = datetime.now()
        items = [(f, n, self.start + timedelta(days=d, hours=random.Random(n).randint(0, 9)))
                 for f, n, d in _PLAN.get(course_id, [])]
        due = [i for i in items if i[2] <= now] or items[:2]
        return sorted(due, key=lambda i: i[2])

    async def sync_course(self, username: str, password: str, course: Course, target_dir: Path,
                          videos: bool, on_progress: ProgressFn) -> CourseResult:
        root = target_dir / course.folder
        due = self._due(course.id)
        hold = set()
        if not course.synced_once and course.id in self.HOLD_BACK:
            hold = {f"{f}/{n}" for f, n, _ in due[-2:]}
        result = CourseResult(course.id, initial=not course.synced_once)
        for folder, name, when in due:
            rel = f"{folder}/{name}"
            on_progress("scan", folder)
            await asyncio.sleep(0.05)
            path = root / rel
            if rel in hold or path.exists():
                continue
            on_progress("download", rel)
            await asyncio.sleep(random.uniform(0.08, 0.25))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(_PDF)
            ts = when.timestamp()
            os.utime(path, (ts, ts))
            result.added.append(rel)
        return result

    def set_log_stream(self, stream) -> None:
        pass

    def forget(self, course_id: str) -> None:
        pass

    def logout(self) -> None:
        pass
