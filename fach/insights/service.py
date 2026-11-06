"""Hintergrund-Dienst: neue und geänderte PDFs nach Klausurterminen durchsuchen.

Läuft nach jedem Abgleich und einmal beim Start. Die PDF-Arbeit passiert in einem Thread
(pypdf ist reine Rechenarbeit), Datenbank-Schreibzugriffe zurück im Event-Loop.
"""

from __future__ import annotations

import asyncio
import time
from datetime import date
from pathlib import Path
from typing import Any

from ..core.config import ConfigStore
from ..core.events import EventBus
from ..core.store import Store
from ..sync.timeline import walk_files
from .exams import scan_file


class ExamService:
    def __init__(self, config: ConfigStore, store: Store, bus: EventBus):
        self.config = config
        self.store = store
        self.bus = bus
        self._lock = asyncio.Lock()
        self.state: dict[str, Any] = {"running": False, "done": 0, "total": 0, "last": None}

    def start(self, full: bool = False) -> None:
        if not self._lock.locked():
            asyncio.get_running_loop().create_task(self.scan(full))

    def _todo(self, cfg, known: dict) -> list[tuple[str, Path, str, float, int]]:
        """Läuft im Thread – deshalb keine Datenbankzugriffe hier (eine SQLite-Verbindung, ein Thread)."""
        todo = []
        for course in cfg.courses:
            root = cfg.target_path / course.folder
            for entry in walk_files(root):
                if not entry.name.lower().endswith(".pdf"):
                    continue
                try:
                    st = entry.stat()
                except OSError:
                    continue
                path = Path(entry.path)
                if known.get(str(path)) == (st.st_mtime, st.st_size):
                    continue
                todo.append((course.id, path, path.relative_to(root).as_posix(), st.st_mtime, st.st_size))
        return todo

    async def scan(self, full: bool = False) -> int:
        async with self._lock:
            loop = asyncio.get_running_loop()
            known = {} if full else self.store.scanned_state()
            todo = await loop.run_in_executor(None, self._todo, self.config.load(), known)
            self.state.update(running=bool(todo), done=0, total=len(todo))
            self._emit()
            if not todo:
                self.state["last"] = time.time()
                return 0
            today = date.today()

            def progress(n: int) -> None:
                self.state["done"] = n
                self._emit()

            def work() -> list[tuple[str, str, Path, float, int, list]]:
                results = []
                last_report = 0.0
                for i, (cid, path, rel, mtime, size) in enumerate(todo, 1):
                    finds = scan_file(path, date.fromtimestamp(mtime), today)
                    results.append((cid, rel, path, mtime, size, finds))
                    if time.monotonic() - last_report > 0.4 or i == len(todo):
                        last_report = time.monotonic()
                        loop.call_soon_threadsafe(progress, i)
                return results

            results = await loop.run_in_executor(None, work)
            found = 0
            for cid, rel, path, mtime, size, finds in results:
                for f in finds:
                    self.store.upsert_found_exam({
                        "course_id": cid, "date": f.date.isoformat(), "start": f.start, "end": f.end,
                        "room": f.room, "kind": f.kind, "source": rel, "page": f.page, "snippet": f.snippet,
                    })
                    found += 1
            self.store.mark_scanned([(str(path), mtime, size) for _, _, path, mtime, size, _ in results])
            self.state.update(running=False, last=time.time())
            self._emit()
            self.bus.emit("changed", what="exams")
            return found

    def _emit(self) -> None:
        self.bus.emit("exams_scan", scan=dict(self.state))
