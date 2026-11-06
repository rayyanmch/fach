"""Windows: Aufgabenplanung (schtasks + XML), Toast-Mitteilungen, Explorer.

Alles ohne Administratorrechte: Die Aufgabe läuft als angemeldeter Benutzer, die App-ID für
Mitteilungen steht unter HKEY_CURRENT_USER.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from ..core.config import Schedule
from ..core.paths import is_frozen
from .base import app_command

TASK_NAME = "Fach ILIAS-Abgleich"
APP_ID = "Fach.Desktop"
_POWERSHELL_APP_ID = "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe"
_NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW

_DAY_TAGS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def task_xml(schedule: Schedule, command: list[str], workdir: Path, today: date | None = None) -> str:
    """XML für schtasks /Create /XML. Reine Funktion – auf jedem System testbar."""
    today = today or date.today()
    if sorted(schedule.days) == list(range(7)):
        rhythm = "<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>"
    else:
        days = "".join(f"<{_DAY_TAGS[d]} />" for d in sorted(schedule.days))
        rhythm = f"<ScheduleByWeek><DaysOfWeek>{days}</DaysOfWeek><WeeksInterval>1</WeeksInterval></ScheduleByWeek>"
    triggers = "".join(
        f"<CalendarTrigger><StartBoundary>{today.isoformat()}T{t}:00</StartBoundary>"
        f"<Enabled>true</Enabled>{rhythm}</CalendarTrigger>"
        for t in schedule.times
    )
    exe, args = command[0], subprocess.list2cmdline(command[1:])
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Fach: holt neue Unterlagen aus ILIAS. Einstellungen in der App Fach.</Description>
  </RegistrationInfo>
  <Triggers>{triggers}</Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(exe)}</Command>
      <Arguments>{escape(args)}</Arguments>
      <WorkingDirectory>{escape(str(workdir))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def toast_xml(title: str, body: str) -> str:
    return (
        '<toast><visual><binding template="ToastGeneric">'
        f"<text>{escape(title)}</text><text>{escape(body)}</text>"
        "</binding></visual></toast>"
    )


# Daten kommen per Umgebungsvariable, nicht per String-Einbau – keine Anführungszeichen-Probleme, keine Injektion.
_TOAST_PS = r"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($env:FACH_TOAST_XML)
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:FACH_TOAST_APPID).Show($toast)
"""


class WindowsPlatform:
    name = "windows"

    def __init__(self) -> None:
        self._register_app_id()

    # --- Zeitplan -------------------------------------------------------------

    def _schtasks(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["schtasks", *args], capture_output=True, text=True, creationflags=_NO_WINDOW)

    def apply_schedule(self, schedule: Schedule) -> None:
        if not schedule.enabled:
            self.remove_schedule()
            return
        command, workdir = app_command("--sync")
        xml = task_xml(schedule, command, workdir)
        tmp = Path(os.environ.get("TEMP", ".")) / "fach-task.xml"
        tmp.write_text(xml, encoding="utf-16")  # schtasks verlangt UTF-16 mit BOM
        try:
            res = self._schtasks("/Create", "/TN", TASK_NAME, "/XML", str(tmp), "/F")
            if res.returncode != 0:
                raise RuntimeError((res.stderr or res.stdout).strip() or "schtasks fehlgeschlagen")
        finally:
            tmp.unlink(missing_ok=True)

    def remove_schedule(self) -> None:
        self._schtasks("/Delete", "/TN", TASK_NAME, "/F")

    def schedule_installed(self) -> bool:
        return self._schtasks("/Query", "/TN", TASK_NAME).returncode == 0

    # --- Mitteilungen ----------------------------------------------------------

    def _register_app_id(self) -> None:
        """App-ID unter HKCU registrieren, damit Toasts mit Namen „Fach“ erscheinen (ohne Admin)."""
        if not is_frozen():
            return
        try:
            import winreg

            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\AppUserModelId\{APP_ID}")
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "Fach")
            icon = Path(sys.executable).with_name("fach.ico")
            if icon.exists():
                winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, str(icon))
            winreg.CloseKey(key)
        except OSError:
            pass

    def notify(self, title: str, body: str) -> None:
        env = {**os.environ, "FACH_TOAST_XML": toast_xml(title, body),
               "FACH_TOAST_APPID": APP_ID if is_frozen() else _POWERSHELL_APP_ID}
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", _TOAST_PS],
            env=env, capture_output=True, timeout=20, creationflags=_NO_WINDOW,
        )

    # --- Dateien -----------------------------------------------------------

    def open_path(self, path: Path) -> None:
        os.startfile(str(path))  # type: ignore[attr-defined]

    def reveal_path(self, path: Path) -> None:
        if path.is_dir():
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            # explorer erwartet /select,"Pfad" als ein Stück; Windows-Pfade enthalten kein ".
            subprocess.Popen(f'explorer /select,"{path}"', creationflags=_NO_WINDOW)


def set_process_app_id() -> None:
    """Taskleiste: Fenster gehört zur Verknüpfung „Fach“ (gleiche App-ID wie der Installer)."""
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)  # type: ignore[attr-defined]
    except Exception:
        pass
