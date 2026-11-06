"""Version 0.2: Restzeit, Module, Klausuren, Datei-Browser, Updater."""

import asyncio
import hashlib
import json
import socket
from datetime import date
from pathlib import Path, PurePath

import pytest
from aiohttp import web

from fach.core.naming import is_valid_relpath, module_parts, plan_layout
from fach.ilias.demo import text_pdf
from fach.ilias.pferd_runtime import DEFAULT_TRANSFORM, rules_transform
from fach.insights.exams import find_exams, scan_file
from fach.server.exams_api import build_ics
from fach.sync.progress import Estimator


# --- Restzeit -----------------------------------------------------------------------

def test_estimator_waits_for_basis_then_is_monotonic():
    est = Estimator.for_run([(None, True), (None, True), (None, True)], now=0)
    est.start(0, now=0)
    frac, eta = est.snapshot(now=5)
    assert eta is None and 0 < frac < 0.1          # erster Abgleich ohne Grundlage: „wird geschätzt“
    est.finish(0, now=30)
    est.start(1, now=30)
    f1, eta1 = est.snapshot(now=31)
    assert eta1 is not None and 55 <= eta1 <= 65    # zwei Kurse à ~30 s übrig
    f2, _ = est.snapshot(now=200)                   # Kurs dauert viel länger → Anteil wächst trotzdem nie zurück
    assert f2 >= f1 and f2 < 1


def test_estimator_uses_history():
    est = Estimator.for_run([(10.0, False), (20.0, False)], now=0)
    est.start(0, now=0)
    frac, eta = est.snapshot(now=5)
    assert eta == pytest.approx(25, abs=1) and frac == pytest.approx(5 / 30, abs=0.02)


# --- Module ---------------------------------------------------------------------------

@pytest.mark.parametrize("title,expected", [
    ("Visualisierung – Übungen", ("Visualisierung", "Übung")),
    ("Übung zu Mathematik für Studierende der Informatik I (WiSe 2026/27)", ("Mathematik für Studierende der Informatik I", "Übung")),
    ("Softwaretechnik", ("Softwaretechnik", "")),
    ("Statistik Tutorium", ("Statistik", "Tutorium")),
])
def test_module_parts(title, expected):
    assert module_parts(title) == expected


def test_plan_layout_groups_lecture_and_exercise():
    layout = plan_layout([("a", "Visualisierung"), ("b", "Visualisierung – Übungen"), ("c", "Softwaretechnik"),
                          ("d", "Übung zu Statistik")])
    assert layout["a"] == ("Visualisierung/Vorlesung", "VIS")
    assert layout["b"] == ("Visualisierung/Übung", "VIS")
    assert layout["c"][0] == "Softwaretechnik"
    assert layout["d"][0] == "Übung zu Statistik"   # allein bleibt allein


def test_is_valid_relpath():
    assert is_valid_relpath("Visualisierung/Übung")
    assert not is_valid_relpath("../x") and not is_valid_relpath("a//b") and not is_valid_relpath("a/b/c/d")


def test_rules_transform_quotes_and_order():
    from PFERD.transformer import Transformer

    rules = [{"src": 'Vorlesung/06 "Arch".pdf', "dst": "Vorlesung/06.pdf"}, {"src": "Blatt 1.pdf", "dst": None}]
    t = Transformer(rules_transform(rules) + "\n" + DEFAULT_TRANSFORM)
    assert str(t.transform(PurePath('Vorlesung/06 "Arch".pdf'))) == "Vorlesung/06.pdf"
    assert t.transform(PurePath("Blatt 1.pdf")) is None
    assert str(t.transform(PurePath("Blatt 2.pdf"))) == "Blatt 2.pdf"


# --- Klausuren --------------------------------------------------------------------------

REF = date(2026, 10, 14)


def _finds(text):
    return sorted((str(f.date), f.start, f.end, f.room, f.kind) for f in find_exams(text, 1, REF))


def test_exams_from_orga_text():
    text = ("Klausur\n1. Termin: Do 11.02.2027, 12:00–14:00 Uhr, Kurt-Alder-Hörsaal\n"
            "2. Termin: Mo 08.03.2027, 09:30 - 11:30, Kurt-Alder-Hörsaal\nAnmeldung zur Klausur bis 15.01.2027 in KLIPS")
    assert _finds(text) == [("2027-02-11", "12:00", "14:00", "Kurt-Alder-Hörsaal", "1. Termin"),
                            ("2027-03-08", "09:30", "11:30", "Kurt-Alder-Hörsaal", "2. Termin")]


def test_exams_exclusions_and_formats():
    assert _finds("Bonustest 1 am 02.12.2026, 12:00-12:30 (zählt für die Klausur)") == []
    assert _finds("Klausureinsicht am 01.03.2027 um 14 Uhr") == []
    assert _finds("Nachklausur: 18. März 2027") == [("2027-03-18", "", "", "", "Nachklausur")]
    assert _finds("Klausurtermin: Mi, 24.03. – Termin B") == [("2027-03-24", "", "", "", "Klausur")]   # Jahr ergänzt
    assert _finds("Exam: February 15, 2027 at 8:00 am – 11:00 am") == [("2027-02-15", "08:00", "11:00", "", "Klausur")]


def test_scan_file_reads_real_pdf(tmp_path):
    pdf = tmp_path / "00_Orga.pdf"
    pdf.write_bytes(text_pdf(["Klausur: Di 16.02.2027, 09:00–11:00 Uhr, Hörsaal 1 Physik"]))
    finds = scan_file(pdf, REF, date(2026, 11, 7))
    assert [(str(f.date), f.start, f.room) for f in finds] == [("2027-02-16", "09:00", "Hörsaal 1 Physik")]


def test_ics_escapes_and_times():
    ics = build_ics([({"title": "Mathe; I, Teil"}, {"ids": [1], "date": "2027-02-16", "start": "09:00", "end": "",
                                                  "room": "HS 1", "kind": "Klausur", "sources": []})])
    assert "SUMMARY:Klausur Mathe\\; I\\, Teil" in ics
    assert "DTSTART:20270216T090000" in ics and "DTEND:20270216T110000" in ics
    assert ics.endswith("END:VCALENDAR\r\n")


# --- API: Zusammenlegen, Datei-Browser, Klausuren ----------------------------------------------

def _call(port, method, path, body=None):
    import urllib.error
    import urllib.request

    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method,
                                 headers={"X-Fach-Token": "t", "Content-Type": "application/json"},
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("FACH_HOME", str(tmp_path))
    from fach.app import build_services
    from fach.core.config import Course
    from fach.desktop import _LoopThread
    from fach.server.http import Server

    services = build_services(demo=True)
    cfg = services.config.load()
    cfg.username, cfg.onboarded, cfg.target_dir = "jmuster1", True, str(tmp_path / "Uni")
    cfg.courses = [Course("crs_1", "Visualisierung", "Visualisierung", "VIS"),
                   Course("crs_2", "Visualisierung – Übungen", "Visualisierung – Übungen", "VISÜ"),
                   Course("crs_3", "Softwaretechnik", "Softwaretechnik", "SWT")]
    services.config.save(cfg)
    services.secrets.set(services.uni.keyring_service(), "jmuster1", "x")
    root = tmp_path / "Uni"
    (root / "Visualisierung" / "Vorlesungsfolien").mkdir(parents=True)
    (root / "Visualisierung" / "Vorlesungsfolien" / "VIS_01.pdf").write_bytes(b"%PDF")
    (root / "Visualisierung" / "notizen.txt").write_text("meins")
    (root / "Visualisierung – Übungen").mkdir()
    (root / "Visualisierung – Übungen" / "Blatt_01.pdf").write_bytes(b"%PDF")
    (root / "Softwaretechnik").mkdir()
    (root / "Softwaretechnik" / "01_Intro.pdf").write_bytes(b"%PDF")
    trashed: list[Path] = []
    services.platform.trash = lambda p: (trashed.append(p), p.unlink())  # nie den echten Papierkorb anfassen
    loop = _LoopThread()
    srv = Server(services, token="t")
    loop.run(srv.start(), timeout=10)
    yield srv, root, trashed
    loop.run(srv.stop(), timeout=10)
    loop.stop()


def test_group_suggestion_moves_folders_two_phase(app):
    srv, root, _ = app
    status, groups = _call(srv.port, "GET", "/api/courses/groups")
    assert status == 200 and len(groups) == 1 and groups[0]["module"] == "Visualisierung"
    status, _ = _call(srv.port, "POST", "/api/courses/groups", {"key": groups[0]["key"], "apply": True})
    assert status == 200
    # Ziel lag im alten Ordner – trotzdem korrekt verschoben, eigene Notiz zieht mit
    assert (root / "Visualisierung" / "Vorlesung" / "Vorlesungsfolien" / "VIS_01.pdf").exists()
    assert (root / "Visualisierung" / "Vorlesung" / "notizen.txt").read_text() == "meins"
    assert (root / "Visualisierung" / "Übung" / "Blatt_01.pdf").exists()
    assert not (root / "Visualisierung – Übungen").exists()
    cfg = srv.services.config.load()
    assert {c.id: c.folder for c in cfg.courses}["crs_2"] == "Visualisierung/Übung"
    assert all(c.label == "VIS" for c in cfg.courses if c.module == "Visualisierung")
    assert _call(srv.port, "GET", "/api/courses/groups")[1] == []


def test_course_folders_may_not_nest(app):
    srv, _, _ = app
    status, body = _call(srv.port, "PUT", "/api/courses", {"courses": [{"id": "crs_3", "folder": "Visualisierung/SWT"}]})
    assert status == 400 and "Ordner eines anderen Kurses" in body["message"]


def test_files_api_paths_rename_rules_and_protection(app):
    srv, root, trashed = app
    assert _call(srv.port, "GET", "/api/files?path=../")[0] == 400
    assert _call(srv.port, "GET", "/api/files?path=Softwaretechnik")[0] == 200
    # Kursordner selbst sind geschützt
    assert _call(srv.port, "POST", "/api/files/rename", {"rel": "Softwaretechnik", "name": "SE"})[0] == 400
    assert _call(srv.port, "POST", "/api/files/trash", {"rels": ["Softwaretechnik"]})[0] == 400
    # Umbenennen → Regel, zweites Umbenennen schreibt dieselbe Regel fort
    assert _call(srv.port, "POST", "/api/files/rename", {"rel": "Softwaretechnik/01_Intro.pdf", "name": "Intro.pdf"})[0] == 200
    assert _call(srv.port, "POST", "/api/files/rename", {"rel": "Softwaretechnik/Intro.pdf", "name": "Einführung.pdf"})[0] == 200
    swt = srv.services.config.load().course("crs_3")
    assert swt.rules == [{"src": "01_Intro.pdf", "dst": "Einführung.pdf"}]
    assert (root / "Softwaretechnik" / "Einführung.pdf").exists()
    # Unzulässige Namen
    assert _call(srv.port, "POST", "/api/files/rename", {"rel": "Softwaretechnik/Einführung.pdf", "name": "a:b.pdf"})[0] == 400
    # Papierkorb → Datei kommt nicht wieder (Regel ohne Ziel)
    assert _call(srv.port, "POST", "/api/files/trash", {"rels": ["Softwaretechnik/Einführung.pdf"]})[0] == 200
    assert trashed and srv.services.config.load().course("crs_3").rules == [{"src": "01_Intro.pdf", "dst": None}]


def test_exams_api_choose_one_per_module_and_manual(app):
    srv, root, _ = app
    store = srv.services.store
    for d in ("2027-02-15", "2027-03-15"):
        store.upsert_found_exam({"course_id": "crs_1", "date": d, "start": "08:00", "source": "Orga.pdf", "page": 1})
    store.upsert_found_exam({"course_id": "crs_2", "date": "2027-02-15", "start": "08:00", "source": "Info.pdf", "page": 2})
    status, data = _call(srv.port, "GET", "/api/exams")
    vis = next(m for m in data["modules"] if m["title"] in ("Visualisierung", "Visualisierung – Übungen") and m["exams"])
    first = vis["exams"][0]
    assert len(first["ids"]) == (2 if len(vis["course_ids"]) == 2 else 1)
    _call(srv.port, "POST", "/api/exams/choose", {"ids": vis["exams"][1]["ids"]})
    _call(srv.port, "POST", "/api/exams/choose", {"ids": first["ids"]})
    data = _call(srv.port, "GET", "/api/exams")[1]
    vis = next(m for m in data["modules"] if m["module"] == vis["module"])
    assert [e["status"] for e in vis["exams"]] == ["chosen", "candidate"]      # nur einer gewählt
    status, _ = _call(srv.port, "POST", "/api/exams", {"module": "Softwaretechnik", "date": "2027-02-11", "start": "12:00", "end": "14:00"})
    assert status == 200
    assert _call(srv.port, "POST", "/api/exams", {"module": "Softwaretechnik", "date": "11.02.2027"})[0] == 400


# --- Updater ---------------------------------------------------------------------------------

def test_parse_version():
    from fach.update import parse_version

    assert parse_version("0.2.0") < parse_version("0.10.0") and parse_version("v1.2") == (1, 2, 0)


def _serve(app: web.Application):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    runner = web.AppRunner(app)
    return runner, port


def test_updater_check_download_and_bad_checksum(tmp_path, monkeypatch):
    import fach.update as upd

    payload = b"MZ fake installer"
    good = {"version": "9.9.9", "setup": "Fach-Setup-9.9.9.exe", "sha256": hashlib.sha256(payload).hexdigest(),
            "size": len(payload), "notes": "Neu"}
    manifest = dict(good)

    async def run():
        async def latest(request):
            return web.json_response(manifest)

        async def setup(request):
            return web.Response(body=payload)

        app = web.Application()
        app.router.add_get("/latest.json", latest)
        app.router.add_get("/v9.9.9/Fach-Setup-9.9.9.exe", setup)
        runner, port = _serve(app)
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", port).start()
        monkeypatch.setattr(upd, "MANIFEST_URL", f"http://127.0.0.1:{port}/latest.json")
        monkeypatch.setattr(upd, "DOWNLOAD_PREFIX", f"http://127.0.0.1:{port}/")
        try:
            u = upd.Updater(tmp_path / "updates")
            assert await u.check() is True and u.state.latest == "9.9.9"
            path = await u.download()
            assert path is not None and path.read_bytes() == payload and u.state.status == "ready"
            # falsche Prüfsumme → verworfen
            manifest["sha256"] = "0" * 64
            u2 = upd.Updater(tmp_path / "updates2")
            await u2.check()
            assert await u2.download() is None and u2.state.status == "error"
            assert not list((tmp_path / "updates2").glob("*.exe"))
        finally:
            await runner.cleanup()

    asyncio.run(run())
