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
CREATE TABLE IF NOT EXISTS course_stats (
    course_id  TEXT PRIMARY KEY,
    regular_s  REAL,                  -- übliche Dauer eines normalen Abgleichs (gleitender Mittelwert)
    initial_s  REAL,                  -- Dauer des ersten Abgleichs
    updated    REAL
);
CREATE TABLE IF NOT EXISTS exams (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id  TEXT NOT NULL,         -- Kurs, in dessen Unterlagen der Termin steht (bzw. gewählt wurde)
    date       TEXT NOT NULL,         -- JJJJ-MM-TT
    start      TEXT NOT NULL DEFAULT '',  -- HH:MM, leer = unbekannt
    end        TEXT NOT NULL DEFAULT '',
    room       TEXT NOT NULL DEFAULT '',
    kind       TEXT NOT NULL DEFAULT 'Klausur',
    note       TEXT NOT NULL DEFAULT '',
    source     TEXT NOT NULL DEFAULT '',  -- Datei relativ zum Kursordner
    page       INTEGER,
    snippet    TEXT NOT NULL DEFAULT '',
    origin     TEXT NOT NULL,         -- found | manual
    status     TEXT NOT NULL DEFAULT 'candidate',  -- candidate | chosen | dismissed
    created    REAL NOT NULL,
    UNIQUE(course_id, date, start, origin)
);
CREATE TABLE IF NOT EXISTS scanned (
    path    TEXT PRIMARY KEY,         -- absoluter Pfad einer schon nach Klausurterminen durchsuchten Datei
    mtime   REAL NOT NULL,
    size    INTEGER NOT NULL
);
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

    def feed(self, limit: int = 200, since: float | None = None, course_ids: list[str] | None = None) -> list[FileEvent]:
        q = "SELECT * FROM files WHERE initial = 0"
        args: list[Any] = []
        if since is not None:
            q += " AND at >= ?"
            args.append(since)
        if course_ids is not None:
            q += f" AND course_id IN ({','.join('?' * len(course_ids)) or 'NULL'})"
            args.extend(course_ids)
        q += " ORDER BY at DESC, id DESC LIMIT ?"
        args.append(limit)
        return [self._file(r) for r in self._db.execute(q, args).fetchall()]

    def file_event(self, event_id: int) -> FileEvent | None:
        row = self._db.execute("SELECT * FROM files WHERE id = ?", (event_id,)).fetchone()
        return self._file(row) if row else None

    def mark_opened(self, event_id: int) -> None:
        self._db.execute("UPDATE files SET opened_at = ? WHERE id = ? AND opened_at IS NULL",
                         (time.time(), event_id))

    def mark_opened_path(self, course_id: str, rel_path: str) -> None:
        self._db.execute("UPDATE files SET opened_at = ? WHERE course_id = ? AND rel_path = ? AND opened_at IS NULL",
                         (time.time(), course_id, rel_path))

    def rename_paths(self, course_id: str, old: str, new: str) -> None:
        """Verlauf nachziehen, wenn eine Datei oder ein Ordner im Datei-Browser umbenannt wurde."""
        self._db.execute("UPDATE files SET rel_path = ? WHERE course_id = ? AND rel_path = ?", (new, course_id, old))
        self._db.execute(
            "UPDATE files SET rel_path = ? || substr(rel_path, ?) WHERE course_id = ? AND rel_path LIKE ? ESCAPE '\\'",
            (new, len(old) + 1, course_id, old.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%"))

    def mark_all_opened(self, course_ids: list[str] | None = None) -> None:
        if course_ids:
            self._db.execute(
                f"UPDATE files SET opened_at = ? WHERE opened_at IS NULL AND course_id IN ({','.join('?' * len(course_ids))})",
                (time.time(), *course_ids))
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
        self._db.execute("DELETE FROM course_stats WHERE course_id = ?", (course_id,))
        self._db.execute("DELETE FROM exams WHERE course_id = ? AND origin = 'found'", (course_id,))

    # --- Dauer je Kurs (für die Restzeit) -------------------------------------

    def course_durations(self) -> dict[str, dict[str, float]]:
        rows = self._db.execute("SELECT * FROM course_stats").fetchall()
        return {r["course_id"]: {"regular_s": r["regular_s"], "initial_s": r["initial_s"]} for r in rows}

    def record_duration(self, course_id: str, seconds: float, initial: bool) -> None:
        col = "initial_s" if initial else "regular_s"
        row = self._db.execute(f"SELECT {col} v FROM course_stats WHERE course_id = ?", (course_id,)).fetchone()
        old = row["v"] if row else None
        value = seconds if old is None or initial else 0.6 * seconds + 0.4 * old
        self._db.execute(
            f"INSERT INTO course_stats(course_id, {col}, updated) VALUES (?, ?, ?) "
            f"ON CONFLICT(course_id) DO UPDATE SET {col} = excluded.{col}, updated = excluded.updated",
            (course_id, value, time.time()))

    # --- Klausuren -----------------------------------------------------------

    def exams(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._db.execute("SELECT * FROM exams ORDER BY date, start").fetchall()]

    def upsert_found_exam(self, e: dict[str, Any]) -> None:
        """Gefundenen Termin speichern. Bereits gewählte/verworfene behalten ihren Status."""
        self._db.execute(
            "INSERT INTO exams(course_id, date, start, end, room, kind, source, page, snippet, origin, created) "
            "VALUES (:course_id, :date, :start, :end, :room, :kind, :source, :page, :snippet, 'found', :created) "
            "ON CONFLICT(course_id, date, start, origin) DO UPDATE SET "
            "end = CASE WHEN excluded.end != '' THEN excluded.end ELSE exams.end END, "
            "room = CASE WHEN excluded.room != '' THEN excluded.room ELSE exams.room END",
            {"end": "", "room": "", "kind": "Klausur", "page": None, "snippet": "", "created": time.time(), **e})

    def add_manual_exam(self, e: dict[str, Any]) -> int:
        cur = self._db.execute(
            "INSERT INTO exams(course_id, date, start, end, room, kind, note, origin, status, created) "
            "VALUES (:course_id, :date, :start, :end, :room, :kind, :note, 'manual', 'chosen', :created) "
            "ON CONFLICT(course_id, date, start, origin) DO UPDATE SET status = 'chosen', room = excluded.room, "
            "end = excluded.end, note = excluded.note, kind = excluded.kind",
            {"end": "", "room": "", "kind": "Klausur", "note": "", "created": time.time(), **e})
        return int(cur.lastrowid or 0)

    def set_exam_status(self, ids: list[int], status: str) -> None:
        self._db.executemany("UPDATE exams SET status = ? WHERE id = ?", [(status, i) for i in ids])

    def delete_manual_exam(self, exam_id: int) -> None:
        self._db.execute("DELETE FROM exams WHERE id = ? AND origin = 'manual'", (exam_id,))

    def scanned_state(self) -> dict[str, tuple[float, int]]:
        return {r["path"]: (r["mtime"], r["size"]) for r in self._db.execute("SELECT * FROM scanned").fetchall()}

    def mark_scanned(self, items: list[tuple[str, float, int]]) -> None:
        self._db.executemany("INSERT OR REPLACE INTO scanned(path, mtime, size) VALUES (?, ?, ?)", items)

    @staticmethod
    def _file(r: sqlite3.Row) -> FileEvent:
        return FileEvent(r["id"], r["run_id"], r["course_id"], r["rel_path"], r["kind"], bool(r["initial"]),
                         r["at"], r["opened_at"])
