"""Linux & Co.: Dateien öffnen geht, Zeitplan und Mitteilungen bewusst nicht (nicht Zielplattform)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..core.config import Schedule


class OtherPlatform:
    name = "other"

    def apply_schedule(self, schedule: Schedule) -> None:
        pass

    def remove_schedule(self) -> None:
        pass

    def schedule_installed(self) -> bool:
        return False

    def notify(self, title: str, body: str) -> None:
        subprocess.run(["notify-send", title, body], capture_output=True)

    def open_path(self, path: Path) -> None:
        subprocess.Popen(["xdg-open", str(path)])

    def reveal_path(self, path: Path) -> None:
        subprocess.Popen(["xdg-open", str(path if path.is_dir() else path.parent)])
