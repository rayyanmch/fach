"""Abgleich mit dem Demo-Backend: erster Lauf still, zweiter Lauf meldet Neues, Sperre, fehlendes Passwort."""

import asyncio
from pathlib import Path

import pytest

from fach.core.config import ConfigStore, Course
from fach.core.events import EventBus
from fach.core.lock import ProcessLock
from fach.core.paths import AppPaths
from fach.core.secrets import MemoryStore
from fach.core.store import Store
from fach.core.university import KOELN
from fach.ilias.demo import DemoIlias
from fach.sync.engine import SyncEngine
from fach.sync.timeline import semester_timeline


@pytest.fixture
def engine(tmp_path: Path):
    paths = AppPaths(tmp_path / "config", tmp_path / "data").ensure()
    config = ConfigStore(paths.config_file)
    cfg = config.load()
    cfg.username = "jmuster1"
    cfg.target_dir = str(tmp_path / "Uni")
    cfg.onboarded = True
    cfg.courses = [Course("crs_6997658", "Softwaretechnik", "Softwaretechnik", "SWT"),
                   Course("crs_6996734", "Visualisierung", "Visualisierung", "VIS")]
    config.save(cfg)
    secrets = MemoryStore()
    secrets.set(KOELN.keyring_service(), "jmuster1", "geheim")
    notes: list[tuple[str, str]] = []
    eng = SyncEngine(config, Store(paths.db_file), DemoIlias(), secrets, KOELN, paths, EventBus(),
                     notify=lambda t, b: notes.append((t, b)))
    eng.notes = notes
    return eng


def test_first_run_is_initial_second_finds_new(engine):
    first = asyncio.run(engine.run("onboarding"))
    assert first.status == "ok" and first.added == 0
    assert "erstmals abgelegt" in first.message
    assert engine.store.feed() == []                       # erster Abgleich flutet den Eingang nicht
    assert all(c.synced_once for c in engine.config.load().courses)

    second = asyncio.run(engine.run("auto"))
    assert second.status == "ok" and second.added == 2       # Demo hält in SWT zwei Dateien zurück
    feed = engine.store.feed()
    assert {f.course_id for f in feed} == {"crs_6997658"}
    assert engine.notes and "2 neue Dateien" in engine.notes[0][0]

    third = asyncio.run(engine.run("manual"))
    assert third.added == 0 and third.message == "Nichts Neues"


def test_missing_password_is_auth(engine):
    engine.secrets.delete(KOELN.keyring_service(), "jmuster1")
    rec = asyncio.run(engine.run("manual"))
    assert rec.status == "auth"


def test_lock_blocks_parallel_run(engine):
    other = ProcessLock(engine.paths.sync_lock)
    assert other.acquire()
    try:
        assert asyncio.run(engine.run("manual")) is None
    finally:
        other.release()


def test_timeline_counts_files_by_upload_week(engine):
    asyncio.run(engine.run("onboarding"))
    t = semester_timeline(engine.config.load(), KOELN)
    swt = next(c for c in t["courses"] if c["id"] == "crs_6997658")
    assert swt["total"] > 0 and sum(swt["counts"]) + swt["before"] == swt["total"]
    assert len(t["week_starts"]) == len(swt["counts"])
