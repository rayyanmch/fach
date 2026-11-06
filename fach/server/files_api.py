"""Datei-Browser über den Uni-Ordner.

Regeln (siehe BRAIN.md):
- Pfade kommen relativ zum Uni-Ordner, mit „/“. Absolute Pfade, „..“ und alles außerhalb (auch über Symlinks)
  werden abgelehnt.
- Programme werden nie gestartet, nur im Ordner gezeigt.
- Umbenennen/Löschen einer Datei, die aus ILIAS kommt, erzeugt eine PFERD-Regel – sonst lädt der nächste
  Abgleich das Original einfach wieder herunter.
- Kursordner selbst werden hier nicht umbenannt oder gelöscht (dafür gibt es den Tab „Kurse“).
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any, Optional

from aiohttp import web

from ..app import Services
from ..core.config import AppConfig, Course
from ..core.naming import is_valid_folder
from ..platform import is_risky
from .api import ApiError, UiHooks, _within

MAX_LIST = 2000
MAX_SEARCH = 200
_HIDDEN = re.compile(r"^(\.|~\$|desktop\.ini$|thumbs\.db$)", re.IGNORECASE)


class FilesApi:
    def __init__(self, services: Services, hooks: UiHooks):
        self.s = services
        self.hooks = hooks

    # --- Hilfen ---------------------------------------------------------------

    @property
    def cfg(self) -> AppConfig:
        return self.s.config.config

    def _root(self) -> Path:
        return self.cfg.target_path

    def _path(self, rel: str, must_exist: bool = True) -> Path:
        rel = (rel or "").replace("\\", "/").strip("/")
        pure = PurePosixPath(rel)
        if pure.is_absolute() or ".." in pure.parts or re.match(r"^[A-Za-z]:", rel):
            raise ApiError(400, "path", "Ungültiger Pfad.")
        root = self._root()
        path = root.joinpath(*pure.parts) if rel else root
        if not _within(root, path):
            raise ApiError(403, "outside", "Dieser Pfad liegt außerhalb deines Uni-Ordners.")
        if must_exist and not path.exists():
            raise ApiError(404, "missing", "Die Datei gibt es nicht mehr.")
        return path

    def _rel(self, path: Path) -> str:
        return path.relative_to(self._root()).as_posix()

    def _course_for(self, rel: str) -> Optional[tuple[Course, str]]:
        """(Kurs, Pfad relativ zum Kursordner) – längster passender Kursordner gewinnt."""
        best: Optional[tuple[Course, str]] = None
        for c in self.cfg.courses:
            if rel == c.folder or rel.startswith(c.folder + "/"):
                inner = rel[len(c.folder):].lstrip("/")
                if best is None or len(c.folder) > len(best[0].folder):
                    best = (c, inner)
        return best

    def _is_protected(self, rel: str) -> bool:
        """Uni-Ordner, Kursordner und Modulordner, die Kursordner enthalten."""
        if not rel:
            return True
        return any(c.folder == rel or c.folder.startswith(rel + "/") for c in self.cfg.courses)

    def _unopened(self) -> set[str]:
        out = set()
        for e in self.s.store.feed(limit=2000):
            if e.opened_at is None:
                c = self.cfg.course(e.course_id)
                if c:
                    out.add(f"{c.folder}/{e.rel_path}")
        return out

    def _entry(self, entry: os.DirEntry, unopened: set[str]) -> Optional[dict[str, Any]]:
        if _HIDDEN.match(entry.name):
            return None
        try:
            is_dir = entry.is_dir(follow_symlinks=False)
            st = entry.stat(follow_symlinks=False)
        except OSError:
            return None
        rel = self._rel(Path(entry.path))
        item: dict[str, Any] = {"name": entry.name, "rel": rel, "dir": is_dir, "mtime": st.st_mtime,
                                "ext": "" if is_dir else os.path.splitext(entry.name)[1].lower().lstrip(".")}
        if is_dir:
            size = count = 0
            for dirpath, dirnames, filenames in os.walk(entry.path):
                dirnames[:] = [d for d in dirnames if not _HIDDEN.match(d)]
                for f in filenames:
                    if _HIDDEN.match(f):
                        continue
                    count += 1
                    try:
                        size += os.stat(os.path.join(dirpath, f)).st_size
                    except OSError:
                        pass
                if count > 20000:
                    break
            item.update(size=size, items=count)
            item["course"] = any(c.folder == rel for c in self.cfg.courses)
            item["protected"] = self._is_protected(rel)
        else:
            item.update(size=st.st_size, new=rel in unopened, risky=is_risky(Path(entry.name)))
        return item

    # --- Lesen ---------------------------------------------------------------

    async def list(self, request: web.Request) -> web.Response:
        rel = request.query.get("path", "")
        path = self._path(rel)
        if not path.is_dir():
            raise ApiError(400, "notdir", "Das ist kein Ordner.")
        unopened = self._unopened()

        def scan() -> list[dict[str, Any]]:
            items = []
            with os.scandir(path) as it:
                for entry in it:
                    if (e := self._entry(entry, unopened)) is not None:
                        items.append(e)
                    if len(items) >= MAX_LIST:
                        break
            return items

        items = await asyncio.get_running_loop().run_in_executor(None, scan)
        rel = self._rel(path) if path != self._root() else ""
        course = self._course_for(rel)
        return web.json_response({
            "path": rel, "root": str(self._root()), "items": items,
            "course_id": course[0].id if course else None, "protected": self._is_protected(rel),
            "drag": bool(self.hooks.start_file_drag),
        })

    async def search(self, request: web.Request) -> web.Response:
        q = request.query.get("q", "").strip().lower()
        if len(q) < 2:
            return web.json_response({"items": []})
        root = self._root()
        unopened = self._unopened()

        def run() -> list[dict[str, Any]]:
            hits = []
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if not _HIDDEN.match(d)]
                for name in filenames:
                    if q in name.lower() and not _HIDDEN.match(name):
                        full = Path(dirpath) / name
                        try:
                            st = full.stat()
                        except OSError:
                            continue
                        rel = self._rel(full)
                        hits.append({"name": name, "rel": rel, "dir": False, "size": st.st_size, "mtime": st.st_mtime,
                                     "ext": full.suffix.lower().lstrip("."), "new": rel in unopened,
                                     "risky": is_risky(full), "parent": self._rel(full.parent) if full.parent != root else ""})
                        if len(hits) >= MAX_SEARCH:
                            return hits
            return hits

        hits = await asyncio.get_running_loop().run_in_executor(None, run)
        hits.sort(key=lambda h: -h["mtime"])
        return web.json_response({"items": hits})

    # --- Aktionen --------------------------------------------------------------

    async def _rels(self, request: web.Request) -> list[Path]:
        data = await request.json()
        rels = data.get("rels") or ([data["rel"]] if data.get("rel") is not None else [])
        if not rels or len(rels) > 200:
            raise ApiError(400, "rels", "Keine Datei ausgewählt.")
        return [self._path(str(r)) for r in rels]

    def _mark_opened(self, path: Path) -> None:
        rel = self._rel(path)
        hit = self._course_for(rel)
        if hit:
            course, inner = hit
            self.s.store.mark_opened_path(course.id, inner)

    async def open(self, request: web.Request) -> web.Response:
        paths = await self._rels(request)
        revealed = False
        for p in paths[:10]:
            if p.is_file() and is_risky(p):
                self.s.platform.reveal_path(p)
                revealed = True
            else:
                self.s.platform.open_path(p)
            if p.is_file():
                self._mark_opened(p)
        return web.json_response({"ok": True, "revealed": revealed})

    async def open_with(self, request: web.Request) -> web.Response:
        path = (await self._rels(request))[0]
        if path.is_dir():
            raise ApiError(400, "dir", "„Öffnen mit“ gibt es nur für Dateien.")
        await asyncio.get_running_loop().run_in_executor(None, self.s.platform.open_with, path)
        self._mark_opened(path)
        return web.json_response({"ok": True})

    async def reveal(self, request: web.Request) -> web.Response:
        path = (await self._rels(request))[0]
        self.s.platform.reveal_path(path)
        return web.json_response({"ok": True})

    async def copy(self, request: web.Request) -> web.Response:
        paths = await self._rels(request)
        try:
            await asyncio.get_running_loop().run_in_executor(None, self.s.platform.copy_files, paths)
        except OSError as e:
            raise ApiError(501, "unsupported", str(e))
        return web.json_response({"ok": True, "count": len(paths)})

    async def drag(self, request: web.Request) -> web.Response:
        paths = await self._rels(request)
        if not self.hooks.start_file_drag or not self.hooks.start_file_drag([str(p) for p in paths]):
            raise ApiError(501, "unsupported", "Ziehen geht nur im App-Fenster unter Windows. Nutze „Kopieren“.")
        return web.json_response({"ok": True})

    async def rename(self, request: web.Request) -> web.Response:
        data = await request.json()
        path = self._path(str(data.get("rel", "")))
        name = str(data.get("name", "")).strip()
        rel = self._rel(path)
        if self._is_protected(rel):
            raise ApiError(400, "protected", "Kurs- und Modulordner benennst du im Tab „Kurse“ um.")
        if not is_valid_folder(name) or "/" in name:
            raise ApiError(400, "name", "Dieser Name ist unter Windows nicht erlaubt.")
        if name == path.name:
            return web.json_response({"ok": True, "rel": rel})
        target = path.with_name(name)
        if target.exists() and target.name.lower() != path.name.lower():
            raise ApiError(409, "exists", f"„{name}“ gibt es hier schon.")
        if self.s.engine.running:
            raise ApiError(409, "busy", "Bitte warte, bis der Abgleich fertig ist.")
        path.rename(target)
        hit = self._course_for(rel)
        if hit:
            course, inner = hit
            new_inner = str(PurePosixPath(inner).with_name(name))
            self._set_rule(course, inner, new_inner)
            self.s.store.rename_paths(course.id, inner, new_inner)
        return web.json_response({"ok": True, "rel": self._rel(target)})

    async def trash(self, request: web.Request) -> web.Response:
        data = await request.json()
        paths = await self._rels_from(data)
        keep_away = bool(data.get("keep_away", True))
        if self.s.engine.running:
            raise ApiError(409, "busy", "Bitte warte, bis der Abgleich fertig ist.")
        for p in paths:
            rel = self._rel(p)
            if self._is_protected(rel):
                raise ApiError(400, "protected", "Kurse entfernst du im Tab „Kurse“ – dann bleiben auch die Einstellungen sauber.")
        for p in paths:
            rel = self._rel(p)
            await asyncio.get_running_loop().run_in_executor(None, self.s.platform.trash, p)
            hit = self._course_for(rel)
            if hit and keep_away:
                self._set_rule(hit[0], hit[1], None)
        return web.json_response({"ok": True})

    async def _rels_from(self, data: dict[str, Any]) -> list[Path]:
        rels = data.get("rels") or []
        if not rels or len(rels) > 200:
            raise ApiError(400, "rels", "Keine Datei ausgewählt.")
        return [self._path(str(r)) for r in rels]

    def _set_rule(self, course: Course, current: str, new: Optional[str]) -> None:
        """Regel anlegen oder fortschreiben. `current` ist der lokale Pfad im Kursordner."""
        work = AppConfig.from_json(self.cfg.to_json())
        c = work.course(course.id)
        if c is None:
            return
        rule = next((r for r in c.rules if r.get("dst") == current), None)
        if rule is None:
            # auch alles darunter, falls ein Ordner umbenannt wurde, der schon Regeln hat
            c.rules.append({"src": current, "dst": new})
        elif new == rule["src"]:
            c.rules.remove(rule)  # zurück zum Originalnamen
        else:
            rule["dst"] = new
        for r in c.rules:
            dst = r.get("dst")
            if new is not None and dst and dst.startswith(current + "/"):
                r["dst"] = new + dst[len(current):]
        self.s.config.save(work)
