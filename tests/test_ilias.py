"""ILIAS-Schicht: Köln-Fix (urljoin), Kurserkennung aus HTML, Login gegen ein Schein-ILIAS."""

import asyncio
import socket
from pathlib import Path

import pytest
from aiohttp import web

from fach.core.university import University
from fach.ilias import AuthFailed
from fach.ilias.discover import course_id_from_url, parse_courses, parse_page_title
from fach.ilias.pferd_runtime import _ROOTS, fixed_urljoin

from .fake_ilias import PASSWORD, USER, make_app

BASE = "https://www.ilias.uni-koeln.de/ilias"


@pytest.fixture(autouse=True)
def _root():
    _ROOTS.add(BASE)
    yield


@pytest.mark.parametrize("base,url,expected", [
    (BASE, "/login.php", f"{BASE}/login.php"),                                   # PFERD-Annahme „ILIAS liegt auf /“
    (BASE, "/ilias.php?baseClass=x", f"{BASE}/ilias.php?baseClass=x"),
    (BASE, "ilias.php?cmd=post", f"{BASE}/ilias.php?cmd=post"),                 # relative Formular-Aktion
    (BASE, "/ilias/ilias.php?cmd=post", f"{BASE}/ilias.php?cmd=post"),          # Server liefert schon den Unterpfad
    (BASE, "https://other.example/x", "https://other.example/x"),               # absolute Adresse bleibt
    (BASE, "goto.php/file/123/download", f"{BASE}/goto.php/file/123/download"),
    (BASE + "/", "goto.php", f"{BASE}/goto.php"),                               # schon korrekter Aufruf: unverändert
    (f"{BASE}/goto.php/crs/1", "/ilias/x.php", "https://www.ilias.uni-koeln.de/ilias/x.php"),  # andere Basis: Standardverhalten
])
def test_fixed_urljoin(base, url, expected):
    assert fixed_urljoin(base, url) == expected


def test_course_id_from_url():
    assert course_id_from_url("https://www.ilias.uni-koeln.de/ilias/goto.php/crs/6997658") == "crs_6997658"
    assert course_id_from_url("https://x/ilias/goto.php?target=grp_12&client_id=uk") == "grp_12"
    assert course_id_from_url("https://x/goto_uk_crs_99.html") == "crs_99"
    assert course_id_from_url("https://x/ilias.php?ref_id=5") is None


def test_parse_courses_variants_and_dedupe():
    from .fake_ilias import MEMBERSHIPS

    found = {c.id: c for c in parse_courses(MEMBERSHIPS, BASE)}
    assert set(found) == {"crs_6997658", "crs_6997182", "grp_555"}
    swt = found["crs_6997658"]
    assert swt.title == "Softwaretechnik (WiSe 2026/27)"
    assert swt.semester == "WiSe 2026/27"
    assert swt.period == "12.10.2026 – 05.02.2027"
    # Bild-Link ohne Text + Titel-Link → ein Eintrag mit Titel
    assert found["crs_6997182"].title == "Information Systems Management"
    assert found["grp_555"].url == f"{BASE}/goto_uk_grp_555.html"


def test_parse_courses_ignores_header_links():
    html = ('<html><body><header><a href="goto.php/crs/1">Kopf</a></header>'
            '<div id="ilContentContainer"><a href="goto.php/crs/2">Echt</a></div></body></html>')
    assert [c.id for c in parse_courses(html, BASE)] == ["crs_2"]


def test_parse_page_title():
    assert parse_page_title("<html><head><title>Kurs: Visualisierung - ILIAS Uni Köln</title></head></html>") == "Visualisierung"
    assert parse_page_title('<h1 id="il_mhead_t_focus">Softwaretechnik</h1>') == "Softwaretechnik"


# --- Login + Kurssuche gegen das Schein-ILIAS (unverändertes PFERD 3.10.1) ---------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _with_fake(tmp_path: Path, fn):
    seen: list[str] = []
    runner = web.AppRunner(make_app(seen))
    await runner.setup()
    port = _free_port()
    await web.TCPSite(runner, "127.0.0.1", port).start()
    try:
        from fach.ilias.real import RealIlias

        uni = University("test", "Test", f"http://localhost:{port}/ilias", "uk", "local", "", "")  # Hostname: aiohttp nimmt keine Cookies von IP-Adressen
        backend = RealIlias(uni, tmp_path / "pferd")
        return await fn(backend), seen
    finally:
        await runner.cleanup()


def test_login_and_discover_against_subpath_ilias(tmp_path):
    async def run(backend):
        return await backend.discover(USER, PASSWORD, fresh_login=True)

    courses, seen = asyncio.run(_with_fake(tmp_path, run))
    assert "/ilias/login.php" in seen and "/login.php" not in seen
    assert {c.id for c in courses} == {"crs_6997658", "crs_6997182", "grp_555"}
    # Cookies liegen im App-Datenordner, nicht im Uni-Ordner
    assert (tmp_path / "pferd" / "cookies.txt").exists()


def test_wrong_password_raises_auth_failed(tmp_path):
    async def run(backend):
        with pytest.raises(AuthFailed):
            await backend.discover(USER, "falsch", fresh_login=True)
        return True

    ok, _ = asyncio.run(_with_fake(tmp_path, run))
    assert ok
