"""Klausuren: gefundene und eigene Termine, pro Modul einer gewählt, als Kalenderdatei exportierbar."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

from aiohttp import web

from ..app import Services
from ..core.naming import clean_title
from ..insights.service import ExamService
from .api import ApiError, _within

_KIND_RANK = {"Klausur": 0, "1. Termin": 1, "2. Termin": 2, "Nachklausur": 3}
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ExamsApi:
    def __init__(self, services: Services, service: ExamService):
        self.s = services
        self.service = service

    # --- Modelle ------------------------------------------------------------------

    def _modules(self) -> dict[str, dict[str, Any]]:
        mods: dict[str, dict[str, Any]] = {}
        for c in self.s.config.config.courses:
            m = mods.setdefault(c.module, {"module": c.module, "label": c.label, "title": c.module,
                                           "course_ids": [], "enabled": False})
            m["course_ids"].append(c.id)
            m["enabled"] = m["enabled"] or c.enabled
        for m in mods.values():
            if len(m["course_ids"]) == 1:
                course = self.s.config.config.course(m["course_ids"][0])
                m["title"] = clean_title(course.title) if course else m["module"]
        return mods

    def _course_module(self) -> dict[str, str]:
        return {c.id: c.module for c in self.s.config.config.courses}

    def _merged(self) -> dict[str, list[dict[str, Any]]]:
        """Termine pro Modul; derselbe Termin aus Vorlesung und Übung wird zu einem Eintrag."""
        by_module: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
        cm = self._course_module()
        for r in self.s.store.exams():
            module = cm.get(r["course_id"])
            if module is None:
                continue
            key = (r["date"], r["start"])
            e = by_module.setdefault(module, {}).get(key)
            if e is None:
                e = {"ids": [], "date": r["date"], "start": r["start"], "end": r["end"], "room": r["room"],
                     "kind": r["kind"], "note": r["note"], "origin": r["origin"], "statuses": [], "sources": []}
                by_module[module][key] = e
            e["ids"].append(r["id"])
            e["statuses"].append(r["status"])
            e["end"] = e["end"] or r["end"]
            e["room"] = e["room"] or r["room"]
            e["note"] = e["note"] or r["note"]
            if _KIND_RANK.get(r["kind"], 0) > _KIND_RANK.get(e["kind"], 0):
                e["kind"] = r["kind"]
            if r["origin"] == "manual":
                e["origin"] = "manual"
            if r["source"]:
                e["sources"].append({"course_id": r["course_id"], "file": r["source"], "page": r["page"],
                                     "snippet": r["snippet"], "id": r["id"]})
        out: dict[str, list[dict[str, Any]]] = {}
        for module, entries in by_module.items():
            items = []
            for e in entries.values():
                st = e.pop("statuses")
                e["status"] = "chosen" if "chosen" in st else ("dismissed" if all(x == "dismissed" for x in st) else "candidate")
                items.append(e)
            out[module] = sorted(items, key=lambda e: (e["date"], e["start"]))
        return out

    # --- Endpunkte ---------------------------------------------------------------

    async def list(self, request: web.Request) -> web.Response:
        mods = self._modules()
        merged = self._merged()
        result = []
        for name, m in mods.items():
            if not m["enabled"]:
                continue
            exams = merged.get(name, [])
            result.append({**m, "exams": exams, "chosen": next((e for e in exams if e["status"] == "chosen"), None)})
        today = date.today().isoformat()

        def sort_key(m: dict[str, Any]) -> tuple:
            if m["chosen"]:
                return (0, m["chosen"]["date"])
            upcoming = [e["date"] for e in m["exams"] if e["status"] != "dismissed" and e["date"] >= today]
            return (1, min(upcoming)) if upcoming else (2, m["title"].lower())

        result.sort(key=sort_key)
        return web.json_response({"modules": result, "scan": self.service.state, "today": today})

    def _module_of_ids(self, ids: list[int]) -> str:
        cm = self._course_module()
        rows = {r["id"]: r for r in self.s.store.exams()}
        modules = {cm.get(rows[i]["course_id"]) for i in ids if i in rows}
        if len(modules) != 1 or None in modules:
            raise ApiError(400, "ids", "Unbekannter Termin.")
        return modules.pop()

    def _unchoose_module(self, module: str, keep: list[int]) -> None:
        cm = self._course_module()
        others = [r["id"] for r in self.s.store.exams()
                  if cm.get(r["course_id"]) == module and r["status"] == "chosen" and r["id"] not in keep]
        self.s.store.set_exam_status(others, "candidate")

    async def _ids(self, request: web.Request) -> list[int]:
        data = await request.json()
        ids = [int(i) for i in (data.get("ids") or [])]
        if not ids:
            raise ApiError(400, "ids", "Kein Termin angegeben.")
        return ids

    async def choose(self, request: web.Request) -> web.Response:
        data = await request.json()
        ids = [int(i) for i in (data.get("ids") or [])]
        if not ids:
            module = str(data.get("module", ""))
            self._unchoose_module(module, [])
        else:
            module = self._module_of_ids(ids)
            self._unchoose_module(module, ids)
            self.s.store.set_exam_status(ids, "chosen")
        self.s.bus.emit("changed", what="exams")
        return web.json_response({"ok": True})

    async def dismiss(self, request: web.Request) -> web.Response:
        self.s.store.set_exam_status(await self._ids(request), "dismissed")
        return web.json_response({"ok": True})

    async def restore(self, request: web.Request) -> web.Response:
        self.s.store.set_exam_status(await self._ids(request), "candidate")
        return web.json_response({"ok": True})

    async def add(self, request: web.Request) -> web.Response:
        data = await request.json()
        module = str(data.get("module", ""))
        mods = self._modules()
        if module not in mods:
            raise ApiError(400, "module", "Bitte ein Modul wählen.")
        day, start, end = str(data.get("date", "")), str(data.get("start", "")), str(data.get("end", ""))
        if not _DATE.match(day):
            raise ApiError(400, "date", "Bitte ein Datum angeben.")
        date.fromisoformat(day)
        for t in (start, end):
            if t and not _TIME.match(t):
                raise ApiError(400, "time", "Uhrzeit bitte als HH:MM.")
        if start and end and end <= start:
            raise ApiError(400, "time", "Das Ende liegt vor dem Beginn.")
        exam_id = self.s.store.add_manual_exam({
            "course_id": mods[module]["course_ids"][0], "date": day, "start": start, "end": end,
            "room": str(data.get("room", ""))[:80], "kind": str(data.get("kind") or "Klausur")[:30],
            "note": str(data.get("note", ""))[:200],
        })
        chosen = [r["id"] for r in self.s.store.exams() if r["origin"] == "manual" and r["date"] == day
                  and r["start"] == start and r["course_id"] == mods[module]["course_ids"][0]]
        self._unchoose_module(module, chosen)
        self.s.bus.emit("changed", what="exams")
        return web.json_response({"ok": True, "id": exam_id})

    async def delete(self, request: web.Request) -> web.Response:
        self.s.store.delete_manual_exam(int(request.match_info["exam_id"]))
        self.s.bus.emit("changed", what="exams")
        return web.json_response({"ok": True})

    async def rescan(self, request: web.Request) -> web.Response:
        data = await request.json() if request.can_read_body else {}
        self.service.start(full=bool(data.get("full")))
        return web.json_response({"ok": True})

    async def open_source(self, request: web.Request) -> web.Response:
        data = await request.json()
        row = next((r for r in self.s.store.exams() if r["id"] == int(data.get("id", 0))), None)
        course = self.s.config.config.course(row["course_id"]) if row else None
        if not row or not course or not row["source"]:
            raise ApiError(404, "unknown", "Quelle nicht gefunden.")
        root = self.s.config.config.target_path
        path = root / course.folder / row["source"]
        if not _within(root, path) or not path.exists():
            raise ApiError(404, "missing", "Die Datei gibt es nicht mehr.")
        self.s.platform.open_path(path)
        return web.json_response({"ok": True})

    async def ics(self, request: web.Request) -> web.Response:
        mods = self._modules()
        merged = self._merged()
        events = [(mods[m], e) for m, items in merged.items() if m in mods for e in items if e["status"] == "chosen"]
        if not events:
            raise ApiError(400, "empty", "Wähle zuerst mindestens einen Klausurtermin.")
        root = self.s.config.config.target_path
        root.mkdir(parents=True, exist_ok=True)
        path = root / "Klausuren.ics"
        path.write_text(build_ics(events), encoding="utf-8", newline="")
        self.s.platform.open_path(path)
        return web.json_response({"ok": True, "path": str(path)})


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def build_ics(events: list[tuple[dict[str, Any], dict[str, Any]]]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Fach//Klausuren//DE", "CALSCALE:GREGORIAN"]
    for module, e in events:
        day = e["date"].replace("-", "")
        lines += ["BEGIN:VEVENT", f"UID:fach-{day}-{e['ids'][0]}@fach.local", f"DTSTAMP:{stamp}",
                  "SUMMARY:" + _esc("Klausur " + module["title"])]
        if e["start"]:
            start = e["start"].replace(":", "")
            end = (e["end"] or f"{(int(e['start'][:2]) + 2) % 24:02d}{e['start'][3:]}").replace(":", "")
            lines += [f"DTSTART:{day}T{start}00", f"DTEND:{day}T{end}00"]
        else:
            lines += [f"DTSTART;VALUE=DATE:{day}"]
        if e["room"]:
            lines.append(f"LOCATION:{_esc(e['room'])}")
        src = e["sources"][0]["file"] if e["sources"] else "eigener Eintrag"
        lines.append("DESCRIPTION:" + _esc(f"{e['kind']} · Quelle: {src}. Verbindlich sind KLIPS und die Lehrenden."))
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"

