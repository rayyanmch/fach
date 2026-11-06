"""Wo Fach seine eigenen Dateien ablegt – getrennt von den Uni-Unterlagen.

Windows:  %APPDATA%\\Fach (Einstellungen), %LOCALAPPDATA%\\Fach (Zustand, Logs)
macOS:    ~/Library/Application Support/Fach

Mit der Umgebungsvariable FACH_HOME landet alles in einem Ordner (Tests, Demo).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_config_path, user_data_path, user_documents_path

from .. import APP_NAME


@dataclass(frozen=True)
class AppPaths:
    config_dir: Path
    data_dir: Path

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.json"

    @property
    def db_file(self) -> Path:
        return self.data_dir / "fach.db"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def pferd_dir(self) -> Path:
        """PFERD-Berichte und Cookies – bewusst nicht im Uni-Ordner (auf Windows wären .dateien sichtbar)."""
        return self.data_dir / "pferd"

    @property
    def sync_lock(self) -> Path:
        return self.data_dir / "sync.lock"

    @property
    def instance_file(self) -> Path:
        return self.data_dir / "instance.json"

    def ensure(self) -> "AppPaths":
        for d in (self.config_dir, self.data_dir, self.log_dir, self.pferd_dir):
            d.mkdir(parents=True, exist_ok=True)
        return self


def app_paths() -> AppPaths:
    home = os.environ.get("FACH_HOME")
    if home:
        root = Path(home).expanduser().resolve()
        return AppPaths(config_dir=root / "config", data_dir=root / "data").ensure()
    return AppPaths(
        config_dir=user_config_path(APP_NAME, appauthor=False, roaming=True),
        data_dir=user_data_path(APP_NAME, appauthor=False),
    ).ensure()


def default_target_dir() -> Path:
    """Vorschlag für den Uni-Ordner: Dokumente/Uni.

    platformdirs fragt unter Windows den echten Dokumente-Ordner ab – auch wenn
    er nach OneDrive umgeleitet ist.
    """
    home = os.environ.get("FACH_HOME")
    if home:
        return Path(home).expanduser().resolve() / "Uni"
    try:
        docs = user_documents_path()
    except Exception:  # pragma: no cover - exotische Systeme
        docs = Path.home() / "Documents"
    return docs / "Uni"


def is_frozen() -> bool:
    """True, wenn Fach als gebaute App (PyInstaller) läuft und nicht aus dem Quellcode."""
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """Ordner mit den mitgelieferten Dateien (Oberfläche, Schriften)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "fach"
    return Path(__file__).resolve().parent.parent
