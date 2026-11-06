"""Uni-Profile. Alles, was an einer Hochschule anders ist, steht hier – sonst nirgends.

Neue ILIAS-Uni = neues Profil (base_url, client_id, Login-Art, Semesterdaten).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Semester:
    name: str              # "WiSe 2026/27"
    start: date            # Semesterbeginn (offiziell)
    end: date
    lectures_start: date   # Vorlesungsbeginn
    lectures_end: date
    estimated: bool = False


@dataclass(frozen=True)
class University:
    key: str
    name: str
    base_url: str          # ohne abschließenden Schrägstrich
    client_id: str
    login_type: str        # "local" (Formular) – "shibboleth" wird von PFERD unterstützt, hier noch nicht getestet
    username_hint: str     # Beispiel im Anmeldefeld
    username_help: str
    semesters: tuple[Semester, ...] = field(default_factory=tuple)

    @property
    def host(self) -> str:
        return urlsplit(self.base_url).hostname or ""

    @property
    def port(self) -> int:
        parts = urlsplit(self.base_url)
        return parts.port or (443 if parts.scheme == "https" else 80)

    def keyring_service(self) -> str:
        return f"Fach · ILIAS {self.name}"


# Quelle Semesterdaten: uni-koeln.de, „Termine und Fristen“ (WiSe 2026/27: Vorlesungen 12.10.2026–05.02.2027).
# SoSe 2027 war beim Anlegen nicht eindeutig belegt → wird geschätzt (siehe semester_for).
KOELN = University(
    key="uni-koeln",
    name="Uni Köln",
    base_url="https://www.ilias.uni-koeln.de/ilias",
    client_id="uk",
    login_type="local",
    username_hint="z. B. jmuster1",
    username_help="Deine Uni-Kennung – dieselbe wie für KLIPS und die Uni-Mail.",
    semesters=(
        Semester("WiSe 2026/27", date(2026, 10, 1), date(2027, 3, 31), date(2026, 10, 12), date(2027, 2, 5)),
    ),
)

UNIVERSITIES: dict[str, University] = {KOELN.key: KOELN}


def get_university(key: str | None) -> University:
    return UNIVERSITIES.get(key or "", KOELN)


def _first_weekday(year: int, month: int, day: int, weekday: int) -> date:
    d = date(year, month, day)
    while d.weekday() != weekday:
        d = date.fromordinal(d.toordinal() + 1)
    return d


def semester_for(uni: University, today: date) -> Semester:
    """Das Semester, in dem `today` liegt. Bekannte Daten aus dem Profil, sonst eine Schätzung."""
    for s in uni.semesters:
        if s.start <= today <= s.end:
            return s
    if today.month >= 10 or today.month <= 3:
        y = today.year if today.month >= 10 else today.year - 1
        return Semester(
            f"WiSe {y}/{str(y + 1)[2:]}", date(y, 10, 1), date(y + 1, 3, 31),
            _first_weekday(y, 10, 8, 0), _first_weekday(y + 1, 2, 1, 4), estimated=True,
        )
    y = today.year
    return Semester(
        f"SoSe {y}", date(y, 4, 1), date(y, 9, 30),
        _first_weekday(y, 4, 1, 0), _first_weekday(y, 7, 10, 4), estimated=True,
    )


def lecture_week(sem: Semester, today: date) -> int | None:
    """1-basierte Vorlesungswoche oder None außerhalb der Vorlesungszeit."""
    if not (sem.lectures_start <= today <= sem.lectures_end):
        return None
    monday = date.fromordinal(sem.lectures_start.toordinal() - sem.lectures_start.weekday())
    return (today.toordinal() - monday.toordinal()) // 7 + 1
