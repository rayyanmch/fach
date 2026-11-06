"""Alles, was zwischen Windows und macOS verschieden ist, hinter einer Schnittstelle.

Der Zeitplan im Betriebssystem ist abgeleiteter Zustand: Er wird bei jedem App-Start und bei jeder
Einstellungsänderung aus config.json neu geschrieben (apply_schedule ist idempotent). So stimmt er auch
nach einem Update, wenn die App an einem anderen Ort liegt.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Protocol

from ..core.config import Schedule
from ..core.paths import is_frozen

# Dateien, die Fach nie per Klick startet, sondern nur im Ordner zeigt. Was aus ILIAS kommt,
# kann jemand mit Schreibrechten im Kurs hochgeladen haben.
RISKY_SUFFIXES = {
    ".exe", ".msi", ".bat", ".cmd", ".com", ".scr", ".pif", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse",
    ".wsf", ".wsh", ".hta", ".lnk", ".url", ".reg", ".jar", ".app", ".command", ".sh", ".pkg", ".dmg",
    ".appimage", ".cpl", ".msc", ".dll", ".iso", ".img", ".vhd", ".vhdx", ".scf", ".library-ms", ".xll",
    ".docm", ".xlsm", ".pptm",
}


def is_risky(path: Path) -> bool:
    return path.suffix.lower() in RISKY_SUFFIXES


class Platform(Protocol):
    name: str

    def apply_schedule(self, schedule: Schedule) -> None: ...

    def remove_schedule(self) -> None: ...

    def schedule_installed(self) -> bool: ...

    def notify(self, title: str, body: str) -> None: ...

    def open_path(self, path: Path) -> None: ...

    def reveal_path(self, path: Path) -> None: ...


def app_command(*args: str) -> tuple[list[str], Path]:
    """Wie startet man diese App erneut (für die Aufgabenplanung)? → (Befehl, Arbeitsordner)."""
    extra = list(args)
    if os.environ.get("FACH_HOME"):
        extra += ["--home", os.environ["FACH_HOME"]]
    if os.environ.get("FACH_DEMO"):
        extra += ["--demo"]
    if is_frozen():
        exe = Path(sys.executable)
        return [str(exe), *extra], exe.parent
    python = Path(sys.executable)
    if sys.platform == "win32" and python.with_name("pythonw.exe").exists():
        python = python.with_name("pythonw.exe")  # kein Konsolenfenster
    project_root = Path(__file__).resolve().parents[2]
    return [str(python), "-m", "fach", *extra], project_root


def get_platform() -> Platform:
    if sys.platform == "win32":
        from .windows import WindowsPlatform

        return WindowsPlatform()
    if sys.platform == "darwin":
        from .macos import MacPlatform

        return MacPlatform()
    from .other import OtherPlatform

    return OtherPlatform()
