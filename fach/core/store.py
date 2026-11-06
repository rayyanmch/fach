"""Verlauf: Abgleiche (runs) und Datei-Ereignisse (files) in SQLite.

GUI und Hintergrund-Abgleich sind getrennte Prozesse und teilen sich diese Datei –
deshalb WAL-Modus und kurze Transaktionen.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    started   REAL NOT NULL,
    ended     REAL,
    trigger   TEXT NOT NULL,          -- auto | manual | onboarding
    status    TEXT NOT NULL,          -- running | ok | partial | error | offline | auth | cancelled
    added     INTEGER NOT NULL DEFAULT 0,
    changed   INTEGER NOT NULL DEFAULT 0,
    message   TEXT NOT NULL DEFAULT '',
    details   TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS files (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     INTEGER NOT NULL,
    course_id  TEXT NOT NULL,
    rel_path   TEXT NOT NULL,         -- relativ zum Kursordner (übersteht Umbenennen des Ordners)
    kind       TEXT NOT NULL,         -- added | changed
    initial    INTEGER NOT NULL DEFAULT 0,  -- Teil des ersten Abgleichs eines Kurses → nicht als „neu“ zeigen
    at         REAL NOT NULL,
    opened_at  REAL
);
CREATE INDEX IF NOT EXISTS files_at ON files(at DESC);
CREATE INDEX IF NOT EXISTS files_course ON files(course_id);
"""


@dataclass
class RunRecord:
    id: int
    started: float
    ended: float | None
    trigger: str
    status: str
    added: int = 0
    changed: int = 0
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class FileEvent:
    id: int
    run_id: int
    course_id: str
    rel_path: str
    kind: str
    initial: bool
    at: float
    opened_at: float | None


class Store:
    def __init__(self, path: Path):
        self.path = path
        self._db = sqlite3.connect(path, timeout=10, isolation_level=None, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    # --- Abgleiche ---------------------------------------------------------

    def start_run(self, trigger: str) -> int:
        cur = self._db.execute(
            "INSERT INTO runs(started, trigger, status) VALUES (?, ?, 'running')", (time.time(), trigger)
        )
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, status: str, added: int, changed: int, message: str,
                   details: dict[str, Any]) -> None:
        self._db.execute(
            "UPDATE runs SET ended=?, status=?, added=?, changed=?, message=?, details=? WHERE id=?",
            (time.time(), status, added, changed, message, json.dumps(details, ensure_ascii=False), run_id),
        )

    def runs(self, limit: int = 30) -> list[RunRecord]:
        rows = self._db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [self._run(r) for r in rows]

    def last_run(self, finished_only: bool = True) -> RunRecord | None:
        q = "SELECT * FROM runs WHERE status != 'running' ORDER BY id DESC LIMIT 1" if finished_only \
            else "SELECT * FROM runs ORDER BY id DESC LIMIT 1"
        row = self._db.execute(q).fetchone()
        return self._run(row) if row else None

    def last_ok_run(self) -> RunRecord | None:
        row = self._db.execute(
            "SELECT * FROM runs WHERE status IN ('ok', 'partial') ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return self._run(row) if row else None

    def close_stale_runs(self) -> None:
        """Läufe, die beim Absturz/Beenden auf 'running' stehen geblieben sind, als abgebrochen markieren."""
        self._db.execute("UPDATE runs SET status='cancelled', ended=started WHERE status='running'")

    @staticmethod
    def _run(r: sqlite3.Row) -> RunRecord:
        return RunRecord(r["id"], r["started"], r["ended"], r["trigger"], r["status"], r["added"],
                         r["changed"], r["message"], json.loads(r["details"] or "{}"))

    # --- Dateien -------------------------------------------------------------

    def add_files(self, run_id: int, course_id: str, kind: str, paths: list[str], initial: bool) -> None:
        now = time.time()
        self._db.executemany(
            "INSERT INTO files(run_id, course_id, rel_path, kind, initial, at) VALUES (?, ?, ?, ?, ?, ?)",
            [(run_id, course_id, p, kind, int(initial), now) for p in paths],
        )

    def feed(self, limit: int = 200, since: float | None = None, course_id: str | None = None) -> list[FileEvent]:
        q = "SELECT * FROM files WHERE initial = 0"
        args: list[Any] = []
        if since is not None:
            q += " AND at >= ?"
            args.append(since)
        if course_id:
            q += " AND course_id = ?"
            args.append(course_id)
        q += " ORDER BY at DESC, id DESC LIMIT ?"
        args.append(limit)
        return [self._file(r) for r in self._db.execute(q, args).fetchall()]

    def file_event(self, event_id: int) -> FileEvent | None:
        row = self._db.execute("SELECT * FROM files WHERE id = ?", (event_id,)).fetchone()
        return self._file(row) if row else None

    def mark_opened(self, event_id: int) -> None:
        self._db.execute("UPDATE files SET opened_at = ? WHERE id = ? AND opened_at IS NULL",
                         (time.time(), event_id))

    def mark_all_opened(self, course_id: str | None = None) -> None:
        if course_id:
            self._db.execute("UPDATE files SET opened_at = ? WHERE opened_at IS NULL AND course_id = ?",
                             (time.time(), course_id))
        else:
            self._db.execute("UPDATE files SET opened_at = ? WHERE opened_at IS NULL", (time.time(),))

    def count_new(self, since: float) -> int:
        row = self._db.execute("SELECT COUNT(*) n FROM files WHERE initial = 0 AND kind = 'added' AND at >= ?",
                               (since,)).fetchone()
        return int(row["n"])

    def unopened_counts(self) -> dict[str, int]:
        rows = self._db.execute(
            "SELECT course_id, COUNT(*) n FROM files WHERE initial = 0 AND opened_at IS NULL GROUP BY course_id"
        ).fetchall()
        return {r["course_id"]: r["n"] for r in rows}

    def forget_course(self, course_id: str) -> None:
        self._db.execute("DELETE FROM files WHERE course_id = ?", (course_id,))

    @staticmethod
    def _file(r: sqlite3.Row) -> FileEvent:
        return FileEvent(r["id"], r["run_id"], r["course_id"], r["rel_path"], r["kind"], bool(r["initial"]),
                         r["at"], r["opened_at"])
