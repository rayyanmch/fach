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

# Orga-Folien mit echtem Text – damit der Klausuren-Tab in der Demo etwas findet.
# BWL Termin A kollidiert absichtlich mit Mathe (16.02.).
_ORGA: dict[str, tuple[str, str, int, list[str]]] = {
    "crs_6997658": ("Vorlesung", "00_Organisatorisches.pdf", 0, [
        "Softwaretechnik – Organisatorisches", "",
        "Klausur", "1. Termin: Do 11.02.2027, 12:00–14:00 Uhr, Kurt-Alder-Hörsaal",
        "2. Termin: Mo 08.03.2027, 09:30–11:30 Uhr, Kurt-Alder-Hörsaal", "",
        "Anmeldung zur Klausur bis 15.01.2027 in KLIPS"]),
    "crs_6999275": ("Vorlesung", "Kapitel_0_Organisatorisches.pdf", 1, [
        "Mathematik für Studierende der Informatik I", "",
        "Klausur: Di 16.02.2027, 09:00–11:00 Uhr, Hörsaal 1 Physik",
        "Nachklausur: Do 18.03.2027, 9–11 Uhr", "",
        "Bonustest 1 am 02.12.2026, 12:00–12:30 Uhr"]),
    "crs_6999750": ("Woche 1/Vorlesung", "Grundlegende_Informationen.pdf", 0, [
        "Grundlagen der BWL – Grundlegende Informationen", "",
        "Klausurtermin A: 16.02.2027, 14:00 Uhr, Aula 1",
        "Klausurtermin B: 24.03.2027, 10:00 Uhr, Aula 2",
        "Sie wählen bei der Anmeldung einen der beiden Termine."]),
    "crs_6996734": ("Vorlesungsfolien", "VIS_00_Organisation.pdf", 2, [
        "Visualisierung – Organisation", "",
        "Klausur: Mo 15.02.2027, 08:00–11:00 Uhr",
        "Nachklausur: Mo 15.03.2027, 09:00–12:00 Uhr",
        "Zulassung: Designübung bestanden, Abgabe 21.01.2027"]),
}


def text_pdf(lines: list[str]) -> bytes:
    """Minimales, gültiges PDF mit einer Textseite (Helvetica, WinAnsi) – ohne Zusatzpakete."""
    def lit(s: str) -> bytes:
        raw = s.encode("cp1252", "replace")
        return b"(" + raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"

    body = b"BT /F1 13 Tf 60 780 Td 20 TL " + b" ".join(lit(line) + b" Tj T*" for line in lines) + b" ET"
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(body)).encode() + b" >>\nstream\n" + body + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


class DemoIlias:
    # In diesen Kursen hält die Demo beim ersten Abgleich die zwei jüngsten Dateien zurück –
    # so findet „Jetzt abgleichen“ danach etwas Neues.
    HOLD_BACK = ("crs_6997658", "crs_6999750")

    def __init__(self, lectures_start: datetime | None = None):
        self.start = lectures_start or datetime(2026, 10, 12, 9, 0)
        self._on_bytes = None

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
        plan = list(_PLAN.get(course_id, []))
        if course_id in _ORGA:
            folder, name, day, _ = _ORGA[course_id]
            plan.append((folder, name, day))
        items = [(f, n, self.start + timedelta(days=d, hours=random.Random(n).randint(0, 9))) for f, n, d in plan]
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
            size = random.Random(rel).randint(90_000, 1_400_000)  # plausible PDF-Größen
            for _ in range(4):
                await asyncio.sleep(random.uniform(0.03, 0.08))
                if self._on_bytes:
                    self._on_bytes(size // 4)
            path.parent.mkdir(parents=True, exist_ok=True)
            orga = _ORGA.get(course.id)
            if orga and orga[1] == name:
                path.write_bytes(text_pdf(orga[3]))
            else:
                with open(path, "wb") as fh:
                    fh.write(_PDF)
                    fh.truncate(size)  # Platzhalter in realistischer Größe (meist ohne echten Platzverbrauch)
            ts = when.timestamp()
            os.utime(path, (ts, ts))
            result.added.append(rel)
        return result

    def set_log_stream(self, stream) -> None:
        pass

    def set_byte_hook(self, fn) -> None:
        self._on_bytes = fn

    def forget(self, course_id: str) -> None:
        pass

    def logout(self) -> None:
        pass
