"""Lokaler Server: Token-, Host- und Origin-Prüfung, Pfadgrenzen beim Öffnen."""

import asyncio
import json
import os
import urllib.error
import urllib.request

import pytest

from fach.server.api import _within


def _call(port, path, token="", headers=None, method="GET", body=None):
    h = {"X-Fach-Token": token, "Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=h, method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.headers


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("FACH_HOME", str(tmp_path))
    from fach.app import build_services
    from fach.desktop import _LoopThread
    from fach.server.http import Server

    services = build_services(demo=True)
    loop = _LoopThread()
    srv = Server(services, token="t0ken")
    loop.run(srv.start(), timeout=10)
    yield srv
    loop.run(srv.stop(), timeout=10)
    loop.stop()


def test_token_required(server):
    assert _call(server.port, "/api/state")[0] == 401
    assert _call(server.port, "/api/state", token="falsch")[0] == 401
    status, headers = _call(server.port, "/api/state", token="t0ken")
    assert status == 200
    assert "script-src 'self'" in headers["Content-Security-Policy"]


def test_host_and_origin_checked(server):
    assert _call(server.port, "/api/state", token="t0ken", headers={"Host": "evil.example"})[0] == 403
    assert _call(server.port, "/api/state", token="t0ken", headers={"Origin": "http://evil.example"})[0] == 403
    assert _call(server.port, "/api/state", token="t0ken", headers={"Origin": f"http://127.0.0.1:{server.port}"})[0] == 200


def test_open_rejects_unknown_targets(server):
    assert _call(server.port, "/api/open", "t0ken", method="POST", body={"path": "/etc/passwd"})[0] == 400
    assert _call(server.port, "/api/open", "t0ken", method="POST", body={"event_id": 999})[0] == 404


def test_within(tmp_path):
    root = tmp_path / "Uni"
    root.mkdir()
    assert _within(root, root / "SWT" / "a.pdf")
    assert not _within(root, root / ".." / "secret.txt")
    if os.name != "nt":
        (root / "link").symlink_to(tmp_path)
        assert not _within(root, root / "link" / "x")
