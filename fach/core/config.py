"""Einstellungen von Fach (config.json). Menschlich lesbar, atomar geschrieben, versioniert.

Invariante: Das Passwort steht NIE hier, sondern im Passwortspeicher des Systems (core/secrets.py).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


@dataclass
class Course:
    id: str                 # "crs_6997658" bzw. "grp_123" – stabil, kommt aus ILIAS
    title: str              # Titel wie in ILIAS
    folder: str             # Ordnername unter target_dir
    label: str              # Kürzel, z. B. "SWT"
    enabled: bool = True
    semester: str = ""      # "WiSe 2026/27", falls erkennbar
    added_at: float = field(default_factory=time.time)
    synced_once: bool = False
    # Eigene Umbenennungen/Löschungen aus dem Datei-Browser, als PFERD-Regeln:
    # {"src": "Ordner/datei.pdf", "dst": "Ordner/neu.pdf"} bzw. {"src": ..., "dst": None} = nicht mehr laden
    rules: list[dict] = field(default_factory=list)

    @property
    def module(self) -> str:
        return self.folder.split("/", 1)[0]

    @property
    def role(self) -> str:
        return self.folder.split("/", 1)[1] if "/" in self.folder else ""

    @property
    def kind(self) -> str:
        return self.id.split("_", 1)[0]

    @property
    def ref(self) -> int:
        return int(self.id.split("_", 1)[1])


@dataclass
class Schedule:
    enabled: bool = True
    days: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])  # 0 = Montag
    times: list[str] = field(default_factory=lambda: ["07:00"])
    spread_min: int = 20    # zufällige Verzögerung, damit nicht alle um Punkt 7 bei ILIAS anklopfen


@dataclass
class Options:
    notify_new: bool = True
    notify_error: bool = True
    videos: bool = False
    auto_update: bool = True
    native_frame: bool = False   # True = normale Windows-Titelleiste statt der eingebauten


@dataclass
class AppConfig:
    version: int = SCHEMA_VERSION
    university: str = "uni-koeln"
    username: str = ""
    target_dir: str = ""
    courses: list[Course] = field(default_factory=list)
    schedule: Schedule = field(default_factory=Schedule)
    options: Options = field(default_factory=Options)
    onboarded: bool = False
    dismissed_groups: list[str] = field(default_factory=list)   # abgelehnte Vorschläge „Kurse zusammenlegen“

    def course(self, course_id: str) -> Course | None:
        return next((c for c in self.courses if c.id == course_id), None)

    def enabled_courses(self) -> list[Course]:
        return [c for c in self.courses if c.enabled]

    @property
    def target_path(self) -> Path:
        return Path(self.target_dir).expanduser()

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "AppConfig":
        data = _migrate(dict(data))
        known = {f for f in cls.__dataclass_fields__}
        cfg = cls(**{k: v for k, v in data.items() if k in known and k not in ("courses", "schedule", "options")})
        cfg.courses = [_build(Course, c) for c in data.get("courses", [])]
        cfg.schedule = _build(Schedule, data.get("schedule", {}))
        cfg.options = _build(Options, data.get("options", {}))
        return cfg


def _build(cls, data: dict[str, Any]):
    known = cls.__dataclass_fields__
    return cls(**{k: v for k, v in data.items() if k in known})


def _migrate(data: dict[str, Any]) -> dict[str, Any]:
    # Platz für künftige Schema-Änderungen: if data.get("version", 1) < 2: ...
    data["version"] = SCHEMA_VERSION
    return data


class ConfigStore:
    """Lädt und speichert die Einstellungen. Schreiben ist atomar (tmp + replace)."""

    def __init__(self, path: Path):
        self.path = path
        self._cfg: AppConfig | None = None

    def load(self) -> AppConfig:
        try:
            self._cfg = AppConfig.from_json(json.loads(self.path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            self._cfg = AppConfig()
        except (ValueError, TypeError):
            # Kaputte Datei nicht stillschweigend überschreiben: zur Seite legen, neu anfangen.
            self.path.replace(self.path.with_suffix(f".broken-{int(time.time())}.json"))
            self._cfg = AppConfig()
        return self._cfg

    @property
    def config(self) -> AppConfig:
        return self._cfg if self._cfg is not None else self.load()

    def save(self, cfg: AppConfig | None = None) -> None:
        if cfg is not None:
            self._cfg = cfg
        data = json.dumps(self.config.to_json(), ensure_ascii=False, indent=2)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(data, encoding="utf-8")
        os.replace(tmp, self.path)
