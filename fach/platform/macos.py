"""macOS: launchd-Agent, Mitteilungen per osascript, Finder.

Noch nicht auf einem frischen Mac mit gebauter App getestet (Signierung/Notarisierung fehlen) –
siehe docs/IDEEN.md, Abschnitt Verteilung.
"""

from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path

from ..core.config import Schedule
from .base import app_command

LABEL = "de.fach.sync"


def plist_data(schedule: Schedule, command: list[str], workdir: Path) -> dict:
    intervals = []
    for t in schedule.times:
        hour, minute = (int(x) for x in t.split(":"))
        if sorted(schedule.days) == list(range(7)):
            intervals.append({"Hour": hour, "Minute": minute})
        else:
            # launchd: 0 = Sonntag; Fach: 0 = Montag
            intervals += [{"Weekday": (d + 1) % 7, "Hour": hour, "Minute": minute} for d in sorted(schedule.days)]
    return {
        "Label": LABEL,
        "ProgramArguments": command,
        "WorkingDirectory": str(workdir),
        "StartCalendarInterval": intervals,
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "StandardOutPath": "/dev/null",
        "StandardErrorPath": "/dev/null",
    }


class MacPlatform:
    name = "macos"

    @property
    def _plist(self) -> Path:
        return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"

    def _launchctl(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["launchctl", *args], capture_output=True, text=True)

    def apply_schedule(self, schedule: Schedule) -> None:
        if not schedule.enabled:
            self.remove_schedule()
            return
        command, workdir = app_command("--sync")
        data = plistlib.dumps(plist_data(schedule, command, workdir))
        if self._plist.exists() and self._plist.read_bytes() == data:
            return
        self._plist.parent.mkdir(parents=True, exist_ok=True)
        domain = f"gui/{os.getuid()}"
        self._launchctl("bootout", domain, str(self._plist))
        self._plist.write_bytes(data)
        res = self._launchctl("bootstrap", domain, str(self._plist))
        if res.returncode != 0:
            raise RuntimeError(res.stderr.strip() or "launchctl bootstrap fehlgeschlagen")

    def remove_schedule(self) -> None:
        if self._plist.exists():
            self._launchctl("bootout", f"gui/{os.getuid()}", str(self._plist))
            self._plist.unlink(missing_ok=True)

    def schedule_installed(self) -> bool:
        return self._plist.exists()

    def notify(self, title: str, body: str) -> None:
        # Text als Argumente übergeben (on run argv) – kein Zusammenbauen von AppleScript-Strings.
        script = 'on run argv\ndisplay notification (item 2 of argv) with title (item 1 of argv)\nend run'
        subprocess.run(["osascript", "-e", script, title, body], capture_output=True, timeout=10)

    def open_path(self, path: Path) -> None:
        subprocess.Popen(["open", str(path)])

    def reveal_path(self, path: Path) -> None:
        subprocess.Popen(["open", str(path)] if path.is_dir() else ["open", "-R", str(path)])

    def _osascript(self, script: str, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["osascript", "-e", script, *args], capture_output=True, text=True, timeout=120)

    def open_with(self, path: Path) -> None:
        res = self._osascript("on run argv\nreturn POSIX path of (choose application as alias)\nend run")
        app = res.stdout.strip()
        if res.returncode == 0 and app:
            subprocess.Popen(["open", "-a", app, str(path)])

    def copy_files(self, paths: list[Path]) -> None:
        script = "on run argv\nset the clipboard to (POSIX file (item 1 of argv))\nend run"
        self._osascript(script, str(paths[0]))

    def trash(self, path: Path) -> None:
        res = self._osascript('on run argv\ntell application "Finder" to delete (POSIX file (item 1 of argv))\nend run', str(path))
        if res.returncode != 0:
            raise OSError(res.stderr.strip() or "In den Papierkorb verschieben fehlgeschlagen.")
