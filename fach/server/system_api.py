"""Fenster (eigene Titelleiste) und Updates."""

from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from ..app import Services
from ..update import Updater
from .api import ApiError, UiHooks

log = logging.getLogger("fach.system")


class SystemApi:
    def __init__(self, services: Services, hooks: UiHooks, updater: Updater):
        self.s = services
        self.hooks = hooks
        self.updater = updater

    # --- Fenster ---------------------------------------------------------------

    async def window(self, request: web.Request) -> web.Response:
        chrome = self.hooks.chrome
        if chrome is None:
            raise ApiError(501, "unsupported", "Keine eigene Titelleiste aktiv.")
        data = await request.json()
        action = str(data.get("action", ""))
        if action == "drag":
            ok = chrome.begin_drag(str(data.get("edge", "caption")))
        elif action == "maximize":
            ok = True
            return web.json_response({"ok": ok, "maximized": chrome.toggle_maximize()})
        elif action == "minimize":
            chrome.minimize()
            ok = True
        elif action == "close":
            chrome.close()
            ok = True
        else:
            raise ApiError(400, "action", "Unbekannte Fensteraktion.")
        return web.json_response({"ok": bool(ok), "maximized": chrome.maximized})

    # --- Updates -----------------------------------------------------------------

    async def update_state(self, request: web.Request) -> web.Response:
        return web.json_response(self.updater.state.public())

    async def update_check(self, request: web.Request) -> web.Response:
        await self.updater.check()
        return web.json_response(self.updater.state.public())

    async def update_install(self, request: web.Request) -> web.Response:
        if not self.updater.state.can_install:
            raise ApiError(400, "unsupported", "Diese Installation kann sich nicht selbst aktualisieren. Lade den Installer von GitHub.")
        if self.s.engine.running:
            raise ApiError(409, "busy", "Bitte warte, bis der Abgleich fertig ist.")
        if self.updater.state.status in ("idle", "uptodate", "error") and not await self.updater.check():
            raise ApiError(409, "uptodate", "Fach ist schon aktuell.")
        asyncio.get_running_loop().create_task(self.install_now())
        return web.json_response({"ok": True})

    async def install_now(self) -> None:
        installer = await self.updater.download()
        if installer and self.updater.install(relaunch=True):
            await asyncio.sleep(1.2)  # der Oberfläche Zeit für „startet neu“ geben
            if self.hooks.quit:
                self.hooks.quit()

    async def auto_update(self) -> None:
        """Beim Start (und dann alle 6 Stunden): prüfen, bei aktivierter Automatik laden und installieren."""
        await asyncio.sleep(4)
        while True:
            try:
                if await self.updater.check():
                    cfg = self.s.config.load()
                    # Nie mitten in der Einrichtung oder während eines Abgleichs neu starten
                    if cfg.options.auto_update and cfg.onboarded and self.updater.state.can_install:
                        while self.s.engine.running:
                            await asyncio.sleep(5)
                        await self.install_now()
            except Exception:
                log.exception("Update-Prüfung fehlgeschlagen")
            await asyncio.sleep(6 * 3600)
