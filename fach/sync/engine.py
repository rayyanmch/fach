"""Der Abgleich: Kurs für Kurs über das ILIAS-Backend, mit Fortschritt, Verlauf und Mitteilungen.

Invarianten
- Höchstens ein Abgleich gleichzeitig – prozessübergreifend (ProcessLock), auch gegen die Aufgabenplanung.
- Eigene Dateien der Studierenden werden nie überschrieben oder gelöscht (on_conflict=local-first in PFERD).
- Der erste Abgleich eines Kurses zählt nicht als „neu“ (sonst 200 Dateien im Eingang).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import IO, Callable, Optional

from ..core.config import ConfigStore
from ..core.events import EventBus
from ..core.lock import ProcessLock
from ..core.paths import AppPaths
from ..core.secrets import SecretStore
from ..core.store import RunRecord, Store
from ..core.university import University
from ..ilias import AuthFailed, IliasBackend, IliasError
from .progress import Estimator

Notifier = Callable[[str, str], None]


@dataclass
class SyncProgress:
    running: bool = False
    external: bool = False      # ein anderer Prozess (Aufgabenplanung) gleicht gerade ab
    run_id: Optional[int] = None
    trigger: str = ""
    started: float = 0.0
    phase: str = "idle"         # idle | network | course
    course_index: int = 0
    course_total: int = 0
    course_id: str = ""
    current: str = ""
    found: int = 0              # neue Dateien in diesem Lauf (ohne ersten Abgleich)
    fraction: float = 0.0       # 0..1, wächst nie rückwärts
    eta: Optional[float] = None  # Restzeit in Sekunden, None = wird noch geschätzt
    bytes: int = 0              # in diesem Lauf geladen
    downloads: int = 0          # Dateien in diesem Lauf geladen (inkl. erstem Abgleich)
    course_downloads: int = 0   # davon im aktuellen Kurs


class SyncEngine:
    def __init__(self, config: ConfigStore, store: Store, backend: IliasBackend, secrets: SecretStore,
                 uni: University, paths: AppPaths, bus: EventBus, notify: Optional[Notifier] = None):
        self.config = config
        self.store = store
        self.backend = backend
        self.secrets = secrets
        self.uni = uni
        self.paths = paths
        self.bus = bus
        self.notify = notify
        self.progress = SyncProgress()
        self._lock = ProcessLock(paths.sync_lock)
        self._task: Optional[asyncio.Task] = None
        self._last_emit = 0.0
        self._estimator: Optional[Estimator] = None
        self._ticker: Optional[asyncio.Task] = None

    # --- Zustand ------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def snapshot(self) -> dict:
        p = asdict(self.progress)
        if not self.progress.running:
            p["external"] = self._lock.is_held_elsewhere()
        return p

    def _emit(self, force: bool = False) -> None:
        now = time.monotonic()
        if force or now - self._last_emit > 0.12:  # höchstens ~8 Updates pro Sekunde an die Oberfläche
            self._last_emit = now
            self._update_estimate()
            self.bus.emit("sync", progress=asdict(self.progress))

    # --- Steuerung ---------------------------------------------------------

    def start(self, trigger: str, only: Optional[list[str]] = None) -> bool:
        """Abgleich im Hintergrund starten. False, wenn schon einer läuft."""
        if self.running or self._lock.is_held_elsewhere():
            return False
        self._task = asyncio.get_running_loop().create_task(self.run(trigger, only))
        return True

    def cancel(self) -> bool:
        if self.running and self._task:
            self._task.cancel()
            return True
        return False

    async def wait(self) -> None:
        if self._task:
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def run(self, trigger: str, only: Optional[list[str]] = None) -> Optional[RunRecord]:
        if not self._lock.acquire():
            return None
        log_fh: Optional[IO[str]] = None
        run_id = self.store.start_run(trigger)
        self.progress = SyncProgress(running=True, run_id=run_id, trigger=trigger, started=time.time(),
                                     phase="network")
        self._emit(force=True)
        status, message = "ok", ""
        added_total = changed_total = initial_total = 0
        details: dict = {"courses": []}
        new_by_course: dict[str, list[str]] = {}
        try:
            log_fh = self._open_log(trigger)
            cfg = self.config.load()
            courses = [c for c in cfg.enabled_courses() if not only or c.id in only]
            password = self.secrets.get(self.uni.keyring_service(), cfg.username) if cfg.username else None
            if not password:
                status, message = "auth", "Bitte melde dich erneut an"
                return self._finish(run_id, status, 0, 0, message, details, new_by_course, trigger)
            if not courses:
                status, message = "ok", "Keine Kurse ausgewählt"
                return self._finish(run_id, status, 0, 0, message, details, new_by_course, trigger)

            if not await self._wait_for_network(300 if trigger == "auto" else 15):
                status, message = "offline", "ILIAS war nicht erreichbar"
                return self._finish(run_id, status, 0, 0, message, details, new_by_course, trigger)

            self.progress.course_total = len(courses)
            target = cfg.target_path
            target.mkdir(parents=True, exist_ok=True)
            stats = self.store.course_durations()
            self._estimator = Estimator.for_run([
                ((stats.get(c.id, {}).get("regular_s") if c.synced_once else stats.get(c.id, {}).get("initial_s")),
                 not c.synced_once) for c in courses])
            self._ticker = asyncio.get_running_loop().create_task(self._tick())
            self.backend.set_byte_hook(self._on_bytes)
            failed = offline = 0
            for i, course in enumerate(courses, 1):
                self.progress.phase = "course"
                self.progress.course_index = i
                self.progress.course_id = course.id
                self.progress.current = ""
                self.progress.course_downloads = 0
                self._estimator.start(i - 1)
                self._emit(force=True)
                self._log(log_fh, f"--- {course.title} ({course.id}) → {course.folder}")

                def on_progress(kind: str, path: str) -> None:
                    self.progress.current = path
                    if kind == "download":
                        self.progress.downloads += 1
                        self.progress.course_downloads += 1
                    self._emit()

                result = await self.backend.sync_course(cfg.username, password, course, target,
                                                        cfg.options.videos, on_progress)
                took = self._estimator.finish(i - 1)
                if not result.errors:
                    self.store.record_duration(course.id, took, result.initial)
                self.store.add_files(run_id, course.id, "added", result.added, result.initial)
                self.store.add_files(run_id, course.id, "changed", result.changed, result.initial)
                if result.initial:
                    initial_total += len(result.added)
                else:
                    added_total += len(result.added)
                    changed_total += len(result.changed)
                    if result.added:
                        new_by_course[course.id] = result.added
                    self.progress.found = added_total
                if result.errors:
                    failed += 1
                    offline += int(result.offline)
                    self._log(log_fh, "Fehler: " + " | ".join(result.errors[:5]))
                elif not course.synced_once:
                    # Erst nach einem fehlerfreien Lauf gilt der Kurs als eingerichtet.
                    live = self.config.load()
                    if (c := live.course(course.id)) is not None:
                        c.synced_once = True
                        self.config.save(live)
                details["courses"].append({
                    "id": course.id, "added": len(result.added), "changed": len(result.changed),
                    "initial": result.initial, "errors": result.errors[:3], "warnings": len(result.warnings),
                })
                self.bus.emit("course_done", course_id=course.id, added=len(result.added), initial=result.initial)

            if failed and offline == failed == len(courses):
                status, message = "offline", "Verbindung zu ILIAS abgebrochen"
            elif failed == len(courses):
                status, message = "error", "Kein Kurs ließ sich abgleichen"
            elif failed:
                status, message = "partial", f"{failed} von {len(courses)} Kursen mit Fehlern"
            else:
                message = _summary(added_total, changed_total, initial_total)
            return self._finish(run_id, status, added_total, changed_total, message, details, new_by_course, trigger)

        except AuthFailed as e:
            return self._finish(run_id, "auth", added_total, changed_total, e.message, details, new_by_course, trigger)
        except IliasError as e:
            return self._finish(run_id, "error", added_total, changed_total, e.message, details, new_by_course, trigger)
        except asyncio.CancelledError:
            self._finish(run_id, "cancelled", added_total, changed_total, "Abgebrochen", details, new_by_course,
                         trigger)
            raise
        except Exception as e:  # unerwartet: festhalten, nicht abstürzen
            self._log(log_fh, f"Unerwarteter Fehler: {type(e).__name__}: {e}")
            return self._finish(run_id, "error", added_total, changed_total, "Unerwarteter Fehler beim Abgleich",
                                details, new_by_course, trigger)
        finally:
            if self._ticker is not None:
                self._ticker.cancel()
                self._ticker = None
            self.backend.set_byte_hook(None)
            self._estimator = None
            self.progress = SyncProgress()
            self._emit(force=True)
            if log_fh:
                self._set_backend_log(None)
                log_fh.close()
            self._lock.release()

    # --- Hilfen ---------------------------------------------------------------

    def _on_bytes(self, n: int) -> None:
        self.progress.bytes += n
        self._emit()

    def _update_estimate(self) -> None:
        if self._estimator is not None:
            self.progress.fraction, self.progress.eta = self._estimator.snapshot()

    async def _tick(self) -> None:
        """Einmal pro Sekunde Restzeit neu rechnen – auch wenn PFERD gerade lange an einer Seite hängt."""
        while True:
            self._update_estimate()
            self._emit(force=True)
            await asyncio.sleep(1.0)

    async def _wait_for_network(self, timeout_s: int) -> bool:
        deadline = time.monotonic() + timeout_s
        while True:
            if await self.backend.reachable(timeout=6):
                return True
            if time.monotonic() > deadline:
                return False
            await asyncio.sleep(10)

    def _open_log(self, trigger: str) -> IO[str]:
        self.paths.log_dir.mkdir(parents=True, exist_ok=True)
        fh = open(self.paths.log_dir / f"{datetime.now():%Y-%m-%d}.log", "a", encoding="utf-8")
        fh.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} Abgleich ({trigger})\n")
        self._set_backend_log(fh)
        for old in self.paths.log_dir.glob("20*.log"):
            if time.time() - old.stat().st_mtime > 30 * 86400:
                old.unlink(missing_ok=True)
        return fh

    def _set_backend_log(self, fh: Optional[IO[str]]) -> None:
        self.backend.set_log_stream(fh)

    @staticmethod
    def _log(fh: Optional[IO[str]], line: str) -> None:
        if fh:
            fh.write(line + "\n")
            fh.flush()

    def _finish(self, run_id: int, status: str, added: int, changed: int, message: str, details: dict,
                new_by_course: dict[str, list[str]], trigger: str) -> RunRecord:
        self.store.finish_run(run_id, status, added, changed, message, details)
        record = next(r for r in self.store.runs(5) if r.id == run_id)
        self.bus.emit("run_done", run={"id": run_id, "status": status, "added": added, "message": message})
        if trigger == "auto":
            self._notify(status, message, new_by_course)
        return record

    def _notify(self, status: str, message: str, new_by_course: dict[str, list[str]]) -> None:
        if not self.notify:
            return
        opts = self.config.config.options
        try:
            if status in ("ok", "partial") and new_by_course and opts.notify_new:
                self.notify(*new_files_text(self.config.config, new_by_course))
            elif status in ("auth", "error") and opts.notify_error:
                self.notify("Fach braucht dich kurz", message)
            elif status == "offline" and opts.notify_error:
                last_ok = self.store.last_ok_run()
                if last_ok is None or time.time() - last_ok.started > 2 * 86400:
                    self.notify("ILIAS seit zwei Tagen nicht erreicht", "Öffne Fach, um es erneut zu versuchen.")
        except Exception:
            pass  # eine Mitteilung darf nie den Abgleich als fehlgeschlagen erscheinen lassen


def _summary(added: int, changed: int, initial: int = 0) -> str:
    parts = []
    if initial:
        parts.append(f"{initial} Datei{'en' if initial != 1 else ''} erstmals abgelegt")
    if not added and not changed:
        return parts[0] if parts else "Nichts Neues"
    if added:
        parts.append(f"{added} neue Datei{'en' if added != 1 else ''}")
    if changed:
        parts.append(f"{changed} aktualisiert")
    return ", ".join(parts)


def new_files_text(cfg, new_by_course: dict[str, list[str]]) -> tuple[str, str]:
    total = sum(len(v) for v in new_by_course.values())
    title = f"{total} neue Datei{'en' if total != 1 else ''} in ILIAS"
    parts = []
    for cid, files in sorted(new_by_course.items(), key=lambda kv: -len(kv[1])):
        course = cfg.course(cid)
        name = course.folder if course else cid
        first = files[0].rsplit("/", 1)[-1]
        parts.append(f"{name}: {first}" + (f" und {len(files) - 1} weitere" if len(files) > 1 else ""))
    return title, "\n".join(parts[:3])
