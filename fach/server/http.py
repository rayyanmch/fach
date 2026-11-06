"""Lokaler Webserver für die Oberfläche – nur auf 127.0.0.1, nur mit Token.

Bedrohungsmodell: Eine beliebige Webseite im Browser könnte Anfragen an 127.0.0.1 schicken.
- Token im eigenen Header (X-Fach-Token) → fremde Seiten können ihn nicht setzen, ohne CORS-Vorabanfrage,
  und CORS erlaubt der Server nie.
- Host-Prüfung gegen DNS-Rebinding, Origin-Prüfung als zweite Linie.
- CSP: Skripte nur aus der App selbst, keine fremden Verbindungen.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import secrets
import socket
from pathlib import Path
from typing import Optional

from aiohttp import web

from ..app import Services
from ..core.paths import resource_dir
from .api import Api, UiHooks, wrap

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")


class Server:
    def __init__(self, services: Services, hooks: Optional[UiHooks] = None, token: Optional[str] = None,
                 port: int = 0):
        self.services = services
        self.hooks = hooks or UiHooks()
        self.token = token or secrets.token_urlsafe(32)
        self.port = port
        self.api = Api(services, self.hooks)
        self.clients = 0          # offene SSE-Verbindungen (Browser-Modus: beenden, wenn keiner mehr da ist)
        self._runner: Optional[web.AppRunner] = None
        self._allowed_hosts: set[str] = set()
        self._allowed_origins: set[str] = set()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    @web.middleware
    async def _guard(self, request: web.Request, handler):
        if request.host not in self._allowed_hosts:
            return web.Response(status=403, text="forbidden")
        if request.path.startswith("/api/"):
            token = request.headers.get("X-Fach-Token", "")
            if request.path == "/api/events" and not token:
                token = request.query.get("token", "")  # EventSource kann keine Header setzen
            if not token or not hmac.compare_digest(token, self.token):
                return web.json_response({"error": "token"}, status=401)
            origin = request.headers.get("Origin")
            if origin and origin not in self._allowed_origins:
                return web.json_response({"error": "origin"}, status=403)
        resp = await handler(request)
        resp.headers["Content-Security-Policy"] = CSP
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        if request.path.startswith("/api/") or request.path == "/":
            resp.headers["Cache-Control"] = "no-store"
        return resp

    def _build(self) -> web.Application:
        app = web.Application(middlewares=[self._guard], client_max_size=256 * 1024)
        a = self.api
        ui = resource_dir() / "ui"
        r = app.router
        r.add_get("/", self._index)
        for sub in ("css", "js", "fonts", "img"):
            if (ui / sub).exists():
                r.add_static(f"/{sub}", ui / sub, follow_symlinks=False)
        routes = [
            ("GET", "/api/ping", a.ping), ("GET", "/api/state", a.state), ("GET", "/api/feed", a.feed),
            ("GET", "/api/timeline", a.timeline), ("GET", "/api/runs", a.runs),
            ("POST", "/api/login", a.login), ("POST", "/api/discover", a.discover),
            ("POST", "/api/courses/resolve", a.resolve), ("POST", "/api/setup", a.setup),
            ("PUT", "/api/courses", a.update_courses), ("DELETE", "/api/courses/{course_id}", a.remove_course),
            ("PUT", "/api/settings", a.update_settings), ("POST", "/api/folder/choose", a.choose_folder),
            ("POST", "/api/logout", a.logout), ("POST", "/api/sync", a.sync), ("POST", "/api/sync/cancel", a.cancel),
            ("POST", "/api/open", a.open), ("POST", "/api/reveal", a.reveal), ("POST", "/api/feed/seen", a.seen),
            ("POST", "/api/schedule/repair", a.repair_schedule), ("POST", "/api/focus", a.focus),
        ]
        for method, path, handler in routes:
            r.add_route(method, path, wrap(handler))
        r.add_get("/api/events", self._events)
        return app

    async def _index(self, request: web.Request) -> web.StreamResponse:
        return web.FileResponse(resource_dir() / "ui" / "index.html")

    async def _events(self, request: web.Request) -> web.StreamResponse:
        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-store"})
        await resp.prepare(request)
        queue, unsubscribe = self.services.bus.queue()
        self.clients += 1
        try:
            await resp.write(b"retry: 2000\n\n")
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    await resp.write(b": ping\n\n")
                    continue
                await resp.write(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
        except (ConnectionResetError, asyncio.CancelledError, RuntimeError):
            pass
        finally:
            self.clients -= 1
            unsubscribe()
        return resp

    async def start(self) -> None:
        self.api.reconcile_schedule()
        if not self.services.engine.running and not self.services.engine.snapshot()["external"]:
            self.services.store.close_stale_runs()
        self._runner = web.AppRunner(self._build(), access_log=None)
        await self._runner.setup()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", self.port))
        self.port = sock.getsockname()[1]
        self._allowed_hosts = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        self._allowed_origins = {f"http://{h}" for h in self._allowed_hosts}
        site = web.SockSite(self._runner, sock)
        await site.start()

    async def stop(self) -> None:
        if self.services.engine.running:
            self.services.engine.cancel()
            await self.services.engine.wait()
        if self._runner:
            await self._runner.cleanup()


def write_instance(path: Path, port: int, token: str) -> None:
    import os
    import sys

    path.write_text(json.dumps({"port": port, "token": token, "pid": os.getpid()}), encoding="utf-8")
    if sys.platform != "win32":
        os.chmod(path, 0o600)
