"""HTTP-Schnittstelle für die Oberfläche. Übersetzt zwischen JSON und den Diensten aus app.py.

Sicherheitsregeln
- Dateien werden nur über IDs aus dem Verlauf oder Kurs-IDs geöffnet, nie über Pfade aus der Anfrage.
- Jeder aufgelöste Pfad muss im Uni-Ordner liegen.
- Ausführbare Dateien werden nie gestartet, nur im Ordner gezeigt (platform.is_risky).
- Das Passwort wird erst gespeichert, wenn ILIAS es akzeptiert hat.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from aiohttp import web

from .. import __version__
from ..app import Services
from ..core import schedule as sched
from ..core.config import AppConfig, Course, Options, Schedule
from ..core.naming import (clean_title, course_label, folder_name, is_valid_relpath, module_key, plan_layout,
                           semester_from_title)
from ..core.paths import default_target_dir
from ..core.secrets import password_store_name
from ..core.university import semester_for
from ..ilias import FoundCourse, IliasError
from ..platform import is_risky
from ..sync.timeline import semester_timeline


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class UiHooks:
    """Was nur das Desktop-Fenster kann (nativer Ordner-Dialog, Fenster nach vorne holen, Titelleiste …)."""

    choose_folder: Optional[Callable[[str], Optional[str]]] = None
    focus: Optional[Callable[[], None]] = None
    quit: Optional[Callable[[], None]] = None
    chrome: Any = None                                          # platform.windows_window.WindowsChrome
    start_file_drag: Optional[Callable[[list[str]], bool]] = None


def _within(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


class Api:
    def __init__(self, services: Services, hooks: UiHooks):
        self.s = services
        self.hooks = hooks
        self._schedule_error = ""
        self._schedule_installed: Optional[bool] = None

    # --- Hilfen ---------------------------------------------------------------

    @property
    def cfg(self):
        return self.s.config.config

    async def _json(self, request: web.Request) -> dict[str, Any]:
        try:
            data = await request.json()
        except (ValueError, json.JSONDecodeError):
            raise ApiError(400, "bad_json", "Ungültige Anfrage.")
        if not isinstance(data, dict):
            raise ApiError(400, "bad_json", "Ungültige Anfrage.")
        return data

    @staticmethod
    def _copy(cfg: AppConfig) -> AppConfig:
        return AppConfig.from_json(cfg.to_json())

    def _password(self) -> str:
        pw = self.s.secrets.get(self.s.uni.keyring_service(), self.cfg.username) if self.cfg.username else None
        if not pw:
            raise ApiError(401, "auth", "Bitte melde dich erneut an.")
        return pw

    def _changed(self, what: str) -> None:
        self.s.bus.emit("changed", what=what)

    def reconcile_schedule(self) -> None:
        """OS-Zeitplan aus config.json ableiten (idempotent)."""
        cfg = self.cfg
        try:
            if cfg.onboarded and cfg.schedule.enabled:
                self.s.platform.apply_schedule(cfg.schedule)
            else:
                self.s.platform.remove_schedule()
            self._schedule_error = ""
        except Exception as e:  # Zeitplan kaputt ≠ App kaputt – anzeigen statt abstürzen
            self._schedule_error = str(e)[:300]
        self._schedule_installed = None

    def _course_json(self, c: Course, unopened: dict[str, int]) -> dict[str, Any]:
        data = asdict(c)
        data.pop("rules", None)
        return {**data, "display_title": clean_title(c.title), "unopened": unopened.get(c.id, 0),
                "module": c.module, "role": c.role}

    def _suggest(self, found: list[FoundCourse]) -> list[dict[str, Any]]:
        """Vorschläge für die Kursauswahl: Ordner, Kürzel, vorausgewählt ja/nein."""
        current = semester_for(self.s.uni, datetime.now().date()).name
        for f in found:
            f.semester = f.semester or semester_from_title(f.title)
        any_semester = any(f.semester for f in found)
        # Neue Kurse gemeinsam planen, damit Vorlesung + Übung eines Moduls in einen Ordner kommen
        fresh = [f for f in found if not self.cfg.course(f.id)]
        layout = plan_layout([(f.id, f.title) for f in fresh], {c.module for c in self.cfg.courses})
        out = []
        for f in found:
            known = self.cfg.course(f.id)
            if known:
                folder, label, selected = known.folder, known.label, known.enabled
            else:
                folder, label = layout[f.id]
                selected = (f.semester == current) if any_semester else True
            out.append({
                "id": f.id, "title": f.title, "display_title": clean_title(f.title), "url": f.url,
                "semester": f.semester, "period": f.period, "folder": folder, "label": label,
                "selected": selected, "known": known is not None, "current": f.semester == current,
            })
        # Kurse eines Moduls stehen nebeneinander (Vorlesung vor Übung)
        out.sort(key=lambda c: (not c["current"], c["folder"].split("/")[0].lower(), c["folder"].lower()))
        return out

    # --- Zustand ----------------------------------------------------------------

    async def state(self, request: web.Request) -> web.Response:
        cfg = self.cfg
        last, last_ok = self.s.store.last_run(), self.s.store.last_ok_run()
        nxt = sched.next_run(cfg.schedule, datetime.now()) if cfg.onboarded else None
        if self._schedule_installed is None and cfg.onboarded:
            self._schedule_installed = self.s.platform.schedule_installed()
        unopened = self.s.store.unopened_counts()
        target = cfg.target_path if cfg.target_dir else default_target_dir()
        return web.json_response({
            "app": {"version": __version__, "demo": self.s.demo, "platform": self.s.platform.name,
                    "password_store": password_store_name(), "can_choose_folder": self.hooks.choose_folder is not None,
                    "custom_chrome": self.hooks.chrome is not None, "can_drag": self.hooks.start_file_drag is not None},
            "uni": {"name": self.s.uni.name, "username_hint": self.s.uni.username_hint,
                    "username_help": self.s.uni.username_help, "host": self.s.uni.host},
            "onboarded": cfg.onboarded,
            "username": cfg.username,
            "has_password": bool(cfg.username and self.s.secrets.get(self.s.uni.keyring_service(), cfg.username)),
            "target_dir": str(target),
            "target_exists": target.exists(),
            "courses": [self._course_json(c, unopened) for c in cfg.courses],
            "schedule": asdict(cfg.schedule),
            "next_run": nxt.isoformat() if nxt else None,
            "schedule_installed": self._schedule_installed,
            "schedule_error": self._schedule_error,
            "options": asdict(cfg.options),
            "sync": self.s.engine.snapshot(),
            "last_run": asdict(last) if last else None,
            "last_ok": asdict(last_ok) if last_ok else None,
            "new_7d": self.s.store.count_new(time.time() - 7 * 86400),
        })

    async def feed(self, request: web.Request) -> web.Response:
        module = request.query.get("module") or None
        ids = [c.id for c in self.cfg.courses if c.module == module] if module else None
        days = min(int(request.query.get("days", "21")), 120)
        events = self.s.store.feed(limit=300, since=time.time() - days * 86400, course_ids=ids)
        root = self.cfg.target_path
        out = []
        for e in events:
            course = self.cfg.course(e.course_id)
            if not course:
                continue
            path = root / course.folder / e.rel_path
            parts = e.rel_path.rsplit("/", 1)
            out.append({
                "id": e.id, "course_id": e.course_id, "name": parts[-1], "dir": parts[0] if len(parts) == 2 else "",
                "kind": e.kind, "at": e.at, "opened": e.opened_at is not None, "exists": path.exists(),
            })
        return web.json_response(out)

    async def timeline(self, request: web.Request) -> web.Response:
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, semester_timeline, self.cfg, self.s.uni)
        return web.json_response(data)

    async def runs(self, request: web.Request) -> web.Response:
        return web.json_response([asdict(r) for r in self.s.store.runs(30)])

    # --- Anmeldung & Kurse ------------------------------------------------------

    async def login(self, request: web.Request) -> web.Response:
        data = await self._json(request)
        username = str(data.get("username", "")).strip().lower()
        password = str(data.get("password", ""))
        if not username or not password:
            raise ApiError(400, "missing", "Bitte Kennung und Passwort eingeben.")
        if len(username) > 64 or any(ch.isspace() for ch in username):
            raise ApiError(400, "username", "Die Kennung enthält keine Leerzeichen.")
        found = await self.s.backend.discover(username, password, fresh_login=True)
        # Erst jetzt, nach erfolgreichem Login, speichern
        if self.cfg.username and self.cfg.username != username:
            self.s.secrets.delete(self.s.uni.keyring_service(), self.cfg.username)
        self.s.secrets.set(self.s.uni.keyring_service(), username, password)
        cfg = self.cfg
        cfg.username = username
        if not cfg.target_dir:
            cfg.target_dir = str(default_target_dir())
        self.s.config.save(cfg)
        self._changed("account")
        return web.json_response({"courses": self._suggest(found)})

    async def discover(self, request: web.Request) -> web.Response:
        found = await self.s.backend.discover(self.cfg.username, self._password())
        return web.json_response({"courses": self._suggest(found)})

    async def resolve(self, request: web.Request) -> web.Response:
        data = await self._json(request)
        url = str(data.get("url", "")).strip()[:500]
        found = await self.s.backend.resolve(self.cfg.username, self._password(), url)
        return web.json_response({"course": self._suggest([found])[0]})

    def _apply_courses(self, work: AppConfig, items: list[dict[str, Any]]) -> list[tuple[Course, str]]:
        """Änderungen auf eine Kopie der Konfig anwenden und prüfen. Gibt ausstehende Umbenennungen zurück.

        Erst wenn alles gültig ist, verschiebt der Aufrufer Ordner und speichert – so bleibt bei einem
        Fehler weder die Konfig noch die Festplatte halb geändert.
        """
        renames: list[tuple[Course, str]] = []
        for item in items:
            cid = str(item.get("id", ""))
            course = work.course(cid)
            folder = "/".join(p.strip() for p in str(item.get("folder", "")).replace("\\", "/").split("/")).strip("/")
            label = str(item.get("label", "")).strip()[:5]
            if folder and not is_valid_relpath(folder):
                raise ApiError(400, "folder", f"„{folder}“ ist kein gültiger Ordnername.")
            if course is None:
                if not item.get("title") or not re.fullmatch(r"(crs|grp)_\d+", cid):
                    continue
                title = str(item["title"])[:300]
                course = Course(id=cid, title=title,
                                folder=folder or folder_name(title, {c.module for c in work.courses}),
                                label=label or course_label(title), semester=str(item.get("semester", ""))[:20])
                work.courses.append(course)
            elif folder and folder != course.folder:
                renames.append((course, folder))
            if label:
                course.label = label.upper()
            if "enabled" in item:
                course.enabled = bool(item["enabled"])

        pending = {c.id: new for c, new in renames}
        final = [(c, pending.get(c.id, c.folder)) for c in work.courses]
        for i, (a, fa) in enumerate(final):
            for b, fb in final[i + 1:]:
                la, lb = fa.lower(), fb.lower()
                if la == lb:
                    raise ApiError(400, "folder", f"Zwei Kurse wollen in den Ordner „{fa}“.")
                if lb.startswith(la + "/") or la.startswith(lb + "/"):
                    inner = fb if len(fb) > len(fa) else fa
                    raise ApiError(400, "folder", f"„{inner}“ läge im Ordner eines anderen Kurses. Nutze einen eigenen Unterordner.")
        if renames and self.s.engine.running:
            raise ApiError(409, "busy", "Während des Abgleichs lassen sich Ordner nicht umbenennen.")
        root = work.target_path
        leaving = [(root / c.folder) for c, _ in renames if (root / c.folder).exists()]
        for course, new in renames:
            new_path = root / new
            if new_path.exists() and not any(new_path == old or _within(old, new_path) for old in leaving):
                raise ApiError(409, "exists", f"Den Ordner „{new}“ gibt es schon.")
        return renames

    def _commit(self, work: AppConfig, renames: list[tuple[Course, str]]) -> None:
        """Ordner in zwei Phasen verschieben (erst alle zur Seite, dann ans Ziel).

        So klappt auch „Visualisierung“ → „Visualisierung/Vorlesung“, wo das Ziel im alten Ordner liegt.
        """
        root = work.target_path
        parked: list[tuple[Course, Path, str]] = []
        try:
            for i, (course, new) in enumerate(renames):
                old = root / course.folder
                if old.exists():
                    tmp = root / f".fach-verschieben-{int(time.time())}-{i}"
                    old.rename(tmp)
                    parked.append((course, tmp, new))
                else:
                    parked.append((course, Path(), new))
            for course, tmp, new in parked:
                if tmp != Path():
                    target = root / new
                    target.parent.mkdir(parents=True, exist_ok=True)
                    tmp.rename(target)
                course.folder = new
        except OSError as e:
            # Zurückrollen, was schon zur Seite gelegt wurde
            for course, tmp, _ in parked:
                if tmp != Path() and tmp.exists():
                    tmp.rename(root / course.folder)
            raise ApiError(409, "move", f"Ordner ließ sich nicht verschieben: {e.strerror or e}. Ist eine Datei darin geöffnet?")
        self.s.config.save(work)

    # --- Module zusammenlegen ---------------------------------------------------

    def _group_suggestions(self) -> list[dict[str, Any]]:
        cfg = self.cfg
        active = cfg.courses
        layout = plan_layout([(c.id, c.title) for c in active], set())
        groups: dict[str, list[Course]] = {}
        for c in active:
            groups.setdefault(module_key(c.title), []).append(c)
        out = []
        for key, members in groups.items():
            if len(members) < 2 or key in cfg.dismissed_groups:
                continue
            modules = {c.module for c in members}
            if len(modules) == 1 and all("/" in c.folder for c in members):
                continue  # schon zusammengelegt
            module = layout[members[0].id][0].split("/", 1)[0]
            # Ordnername darf nicht mit einem fremden Kurs kollidieren
            others = {c.module.lower() for c in active if c not in members}
            if module.lower() in others:
                module = folder_name(module, {c.module for c in active if c not in members})
            out.append({
                "key": key, "module": module, "label": layout[members[0].id][1],
                "members": [{"id": c.id, "title": clean_title(c.title), "from": c.folder,
                             "to": f"{module}/{layout[c.id][0].split('/', 1)[1]}"} for c in members],
            })
        return out

    async def groups(self, request: web.Request) -> web.Response:
        return web.json_response(self._group_suggestions())

    async def apply_group(self, request: web.Request) -> web.Response:
        data = await self._json(request)
        key = str(data.get("key", ""))
        suggestion = next((g for g in self._group_suggestions() if g["key"] == key), None)
        if suggestion is None:
            raise ApiError(404, "unknown", "Diesen Vorschlag gibt es nicht mehr.")
        work = self._copy(self.cfg)
        if not data.get("apply"):
            work.dismissed_groups = sorted({*work.dismissed_groups, key})
            self.s.config.save(work)
        else:
            items = [{"id": m["id"], "folder": m["to"], "label": suggestion["label"]} for m in suggestion["members"]]
            self._commit(work, self._apply_courses(work, items))
        self._changed("courses")
        return web.json_response({"ok": True})

    async def setup(self, request: web.Request) -> web.Response:
        """Abschluss des Onboardings: Kurse, Ordner, Zeitplan speichern und ersten Abgleich starten."""
        data = await self._json(request)
        self._password()
        cfg = self.cfg
        target = str(data.get("target_dir", "")).strip() or str(default_target_dir())
        target_path = Path(target).expanduser()
        if not target_path.is_absolute():
            raise ApiError(400, "target", "Bitte einen vollständigen Ordnerpfad angeben.")
        items = data.get("courses") or []
        if not isinstance(items, list) or not any(i.get("enabled") for i in items if isinstance(i, dict)):
            raise ApiError(400, "courses", "Wähle mindestens einen Kurs.")
        work = self._copy(cfg)
        work.target_dir = str(target_path)
        renames = self._apply_courses(work, [i for i in items if isinstance(i, dict)])
        if isinstance(data.get("schedule"), dict):
            work.schedule = sched.validate(Schedule(**{**asdict(work.schedule), **data["schedule"]}))
        work.onboarded = True
        target_path.mkdir(parents=True, exist_ok=True)
        self._commit(work, renames)
        self.reconcile_schedule()
        self.s.engine.start("onboarding")
        self._changed("config")
        return web.json_response({"ok": True})

    async def update_courses(self, request: web.Request) -> web.Response:
        data = await self._json(request)
        items = data.get("courses")
        if not isinstance(items, list):
            raise ApiError(400, "courses", "Ungültige Kursliste.")
        work = self._copy(self.cfg)
        renames = self._apply_courses(work, [i for i in items if isinstance(i, dict)])
        self._commit(work, renames)
        self._changed("courses")
        return web.json_response({"ok": True})

    async def remove_course(self, request: web.Request) -> web.Response:
        cid = request.match_info["course_id"]
        cfg = self.cfg
        if self.s.engine.running:
            raise ApiError(409, "busy", "Bitte warte, bis der Abgleich fertig ist.")
        if not cfg.course(cid):
            raise ApiError(404, "unknown", "Kurs nicht gefunden.")
        cfg.courses = [c for c in cfg.courses if c.id != cid]
        self.s.config.save(cfg)
        self.s.backend.forget(cid)
        self.s.store.forget_course(cid)
        self._changed("courses")
        return web.json_response({"ok": True})

    # --- Einstellungen -------------------------------------------------------

    async def update_settings(self, request: web.Request) -> web.Response:
        data = await self._json(request)
        cfg = self.cfg
        if isinstance(data.get("schedule"), dict):
            try:
                cfg.schedule = sched.validate(Schedule(**{**asdict(cfg.schedule), **data["schedule"]}))
            except (TypeError, ValueError) as e:
                raise ApiError(400, "schedule", str(e))
        if isinstance(data.get("options"), dict):
            cfg.options = Options(**{**asdict(cfg.options),
                                     **{k: bool(v) for k, v in data["options"].items() if k in asdict(cfg.options)}})
        if "target_dir" in data:
            await self._move_target(Path(str(data["target_dir"])).expanduser())
        self.s.config.save(cfg)
        if "schedule" in data:
            self.reconcile_schedule()
        self._changed("config")
        return await self.state(request)

    async def _move_target(self, new_root: Path) -> None:
        """Uni-Ordner wechseln und die Kursordner mitnehmen (sonst lädt der nächste Abgleich alles neu)."""
        cfg = self.cfg
        if not new_root.is_absolute():
            raise ApiError(400, "target", "Bitte einen vollständigen Ordnerpfad angeben.")
        old_root = cfg.target_path
        if new_root.resolve() == old_root.resolve():
            return
        if self.s.engine.running:
            raise ApiError(409, "busy", "Bitte warte, bis der Abgleich fertig ist.")
        if _within(old_root, new_root) or _within(new_root, old_root):
            raise ApiError(400, "target", "Der neue Ordner darf nicht im alten liegen (und umgekehrt).")
        clashes = [c.folder for c in cfg.courses if (old_root / c.folder).exists() and (new_root / c.folder).exists()]
        if clashes:
            raise ApiError(409, "exists", f"Im neuen Ordner gibt es schon „{clashes[0]}“.")
        new_root.mkdir(parents=True, exist_ok=True)

        def move_all() -> None:
            for c in cfg.courses:
                src = old_root / c.folder
                if src.exists():
                    shutil.move(str(src), str(new_root / c.folder))

        await asyncio.get_running_loop().run_in_executor(None, move_all)
        cfg.target_dir = str(new_root)

    async def choose_folder(self, request: web.Request) -> web.Response:
        if not self.hooks.choose_folder:
            raise ApiError(501, "unsupported", "Ordnerauswahl gibt es nur im App-Fenster.")
        data = await self._json(request)
        start = str(data.get("start") or self.cfg.target_dir or default_target_dir())
        path = await asyncio.get_running_loop().run_in_executor(None, self.hooks.choose_folder, start)
        return web.json_response({"path": path})

    async def logout(self, request: web.Request) -> web.Response:
        if self.s.engine.running:
            self.s.engine.cancel()
            await self.s.engine.wait()
        cfg = self.cfg
        if cfg.username:
            self.s.secrets.delete(self.s.uni.keyring_service(), cfg.username)
        self.s.backend.logout()
        cfg.onboarded = False
        self.s.config.save(cfg)
        self.reconcile_schedule()
        self._changed("account")
        return web.json_response({"ok": True})

    # --- Abgleich -----------------------------------------------------------------

    async def sync(self, request: web.Request) -> web.Response:
        data = await self._json(request) if request.can_read_body else {}
        only = data.get("courses") if isinstance(data.get("courses"), list) else None
        trigger = "auto" if data.get("trigger") == "auto" else "manual"
        self._password()
        if not self.s.engine.start(trigger, only):
            raise ApiError(409, "busy", "Es läuft schon ein Abgleich.")
        return web.json_response({"ok": True})

    async def cancel(self, request: web.Request) -> web.Response:
        return web.json_response({"ok": self.s.engine.cancel()})

    # --- Dateien -----------------------------------------------------------------

    def _resolve_target(self, data: dict[str, Any]) -> tuple[Path, Optional[int]]:
        root = self.cfg.target_path
        if "event_id" in data:
            event = self.s.store.file_event(int(data["event_id"]))
            course = self.cfg.course(event.course_id) if event else None
            if not event or not course:
                raise ApiError(404, "unknown", "Datei nicht gefunden.")
            path = root / course.folder / event.rel_path
            event_id: Optional[int] = event.id
        elif "course_id" in data:
            course = self.cfg.course(str(data["course_id"]))
            if not course:
                raise ApiError(404, "unknown", "Kurs nicht gefunden.")
            path, event_id = root / course.folder, None
        elif data.get("target") == "root":
            path, event_id = root, None
        elif data.get("target") == "logs":
            return self.s.paths.log_dir, None
        else:
            raise ApiError(400, "target", "Was soll geöffnet werden?")
        if not _within(root, path):
            raise ApiError(403, "outside", "Dieser Pfad liegt außerhalb deines Uni-Ordners.")
        if not path.exists():
            raise ApiError(404, "missing", "Die Datei gibt es nicht mehr – vielleicht verschoben oder gelöscht.")
        return path, event_id

    async def open(self, request: web.Request) -> web.Response:
        data = await self._json(request)
        path, event_id = self._resolve_target(data)
        revealed = False
        if path.is_file() and is_risky(path):
            self.s.platform.reveal_path(path)
            revealed = True
        else:
            self.s.platform.open_path(path)
        if event_id is not None:
            self.s.store.mark_opened(event_id)
        return web.json_response({"ok": True, "revealed": revealed})

    async def reveal(self, request: web.Request) -> web.Response:
        data = await self._json(request)
        path, _ = self._resolve_target(data)
        self.s.platform.reveal_path(path)
        return web.json_response({"ok": True})

    async def seen(self, request: web.Request) -> web.Response:
        data = await self._json(request)
        module = data.get("module")
        self.s.store.mark_all_opened([c.id for c in self.cfg.courses if c.module == module] if module else None)
        self._changed("feed")
        return web.json_response({"ok": True})

    async def repair_schedule(self, request: web.Request) -> web.Response:
        self.reconcile_schedule()
        return await self.state(request)

    async def focus(self, request: web.Request) -> web.Response:
        if self.hooks.focus:
            self.hooks.focus()
        return web.json_response({"ok": True})

    async def ping(self, request: web.Request) -> web.Response:
        return web.json_response({"app": "fach", "version": __version__})


def wrap(handler: Callable[[web.Request], Awaitable[web.StreamResponse]]):
    async def inner(request: web.Request) -> web.StreamResponse:
        try:
            return await handler(request)
        except ApiError as e:
            return web.json_response({"error": e.code, "message": e.message}, status=e.status)
        except IliasError as e:
            status = {"auth": 401, "offline": 503}.get(e.code, 502)
            return web.json_response({"error": e.code, "message": e.message}, status=status)
        except (ValueError, TypeError) as e:
            return web.json_response({"error": "bad_request", "message": str(e)[:200]}, status=400)
        except PermissionError:
            return web.json_response({"error": "permission", "message": "Keine Berechtigung für diesen Ordner."},
                                     status=403)
    return inner
