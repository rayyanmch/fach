"""Was die ILIAS-Schicht nach außen gibt. Der Rest der App kennt nur diese Typen – nicht PFERD."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Callable, Protocol

from ..core.config import Course

ProgressFn = Callable[[str, str], None]  # (art: "scan" | "download", ILIAS-Pfad)


@dataclass
class FoundCourse:
    id: str                 # "crs_6997658"
    title: str
    url: str
    semester: str = ""      # "WiSe 2026/27", wenn erkennbar
    period: str = ""        # Rohtext, z. B. "12.10.2026 - 05.02.2027"


@dataclass
class CourseResult:
    course_id: str
    added: list[str] = field(default_factory=list)      # relativ zum Kursordner, mit "/" getrennt
    changed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    initial: bool = False   # erster Abgleich dieses Kurses
    offline: bool = False


class IliasError(Exception):
    """Fehler mit einer Meldung, die man Studierenden zeigen kann."""

    code = "error"

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail


class AuthFailed(IliasError):
    code = "auth"


class Unreachable(IliasError):
    code = "offline"


class IliasBackend(Protocol):
    async def reachable(self, timeout: float = 8.0) -> bool: ...

    async def discover(self, username: str, password: str, fresh_login: bool = False) -> list[FoundCourse]: ...

    async def resolve(self, username: str, password: str, url: str) -> FoundCourse: ...

    async def sync_course(self, username: str, password: str, course: Course, target_dir: Path,
                          videos: bool, on_progress: ProgressFn) -> CourseResult: ...

    def set_log_stream(self, stream: IO[str] | None) -> None: ...

    def set_byte_hook(self, fn: Callable[[int], None] | None) -> None: ...

    def forget(self, course_id: str) -> None: ...

    def logout(self) -> None: ...
