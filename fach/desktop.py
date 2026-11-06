"""Start-Modi: Fenster (pywebview), Browser (Entwicklung / Rückfall) und Hintergrund-Abgleich.

Ein Fenster pro Rechner: Ein zweiter Start holt das vorhandene Fenster nach vorne.
Der Hintergrund-Abgleich übergibt an ein offenes Fenster, statt parallel zu laufen.
"""

from __future__ import annotations

import asyncio
import json
import random
import sys
import threading
import time
import urllib.request
import webbrowser
from typing import Optional

from .app import Services
from .server.api import UiHooks
from .server.http import Server, write_instance


def _instance_call(services: Services, path: str, body: Optional[dict] = None, timeout: float = 1.5) -> Optional[dict]:
    """Mit einer bereits laufenden Fach-Instanz sprechen. None, wenn keine antwortet."""
    try:
        info = json.loads(services.paths.instance_file.read_text(encoding="utf-8"))
        req = urllib.request.Request(
            f"http://127.0.0.1:{int(info['port'])}{path}",
            data=json.dumps(body or {}).encode() if body is not None else None,
            headers={"X-Fach-Token": info["token"], "Content-Type": "application/json"},
            method="POST" if body is not None else "GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read() or b"{}")
    except Exception:
        return None


class _LoopThread:
    """Eigener asyncio-Loop im Hintergrund – das Fenster braucht den Haupt-Thread."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self.loop.run_forever, name="fach-loop", daemon=True)
        self._thread.start()

    def run(self, coro, timeout: Optional[float] = None):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)


def run_window(services: Services, dev: bool = False) -> int:
    if _instance_call(services, "/api/ping") is not None:
        _instance_call(services, "/api/focus", {})
        return 0
    try:
        import webview  # pywebview
    except ImportError:
        return run_browser(services)

    if sys.platform == "win32":
        from .platform.windows import set_process_app_id

        set_process_app_id()

    hooks = UiHooks()
    server = Server(services, hooks)
    loop = _LoopThread()
    loop.run(server.start(), timeout=20)
    write_instance(services.paths.instance_file, server.port, server.token)

    # Eigene Titelleiste nur unter Windows; abschaltbar in den Einstellungen (falls etwas klemmt).
    custom_chrome = sys.platform == "win32" and not services.config.config.options.native_frame
    window = webview.create_window(
        "Fach", f"{server.url}#t={server.token}", width=1160, height=780, min_size=(920, 640),
        background_color="#F6F5F2", text_select=True, frameless=custom_chrome, easy_drag=False,
        shadow=custom_chrome,
    )
    if custom_chrome:
        from .platform.windows_window import try_chrome

        chrome = try_chrome(window)
        if chrome is not None:
            hooks.chrome = chrome
            hooks.start_file_drag = chrome.start_file_drag
            window.events.shown += chrome.prepare
    elif sys.platform == "win32":
        from .platform.windows_window import WindowsChrome

        hooks.start_file_drag = WindowsChrome(window).start_file_drag

    folder_kind = webview.FileDialog.FOLDER if hasattr(webview, "FileDialog") else webview.FOLDER_DIALOG

    def choose_folder(start: str) -> Optional[str]:
        result = window.create_file_dialog(folder_kind, directory=start)
        return result[0] if result else None

    def focus() -> None:
        try:
            window.restore()
            window.show()
            window.on_top = True
            window.on_top = False
        except Exception:
            pass

    hooks.choose_folder = choose_folder
    hooks.focus = focus
    hooks.quit = window.destroy
    try:
        webview.start(debug=dev, private_mode=True)
    except Exception:
        # Kein WebView2/WKWebView? Dann eben im Standardbrowser – der Server läuft ja schon.
        webbrowser.open(f"{server.url}#t={server.token}")
        _wait_for_browser_clients(server)
    finally:
        loop.run(server.stop(), timeout=30)
        loop.stop()
        services.paths.instance_file.unlink(missing_ok=True)
    return 0


def _wait_for_browser_clients(server: Server, grace_s: int = 45) -> None:
    """Im Browser-Modus weiterlaufen, solange ein Tab offen ist (SSE-Verbindung)."""
    idle_since: Optional[float] = None
    while True:
        time.sleep(2)
        if server.clients > 0 or server.services.engine.running:
            idle_since = None
        elif idle_since is None:
            idle_since = time.monotonic()
        elif time.monotonic() - idle_since > grace_s:
            return


def run_browser(services: Services, port: int = 0, token: Optional[str] = None, open_browser: bool = True,
                keep_alive: bool = False) -> int:
    """Oberfläche im normalen Browser. Mit keep_alive (Entwicklung) läuft der Server bis Strg+C."""
    loop = _LoopThread()
    server = Server(services, token=token, port=port)
    loop.run(server.start(), timeout=20)
    write_instance(services.paths.instance_file, server.port, server.token)
    url = f"{server.url}#t={server.token}"
    print(f"Fach läuft auf {url}", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        if keep_alive:
            while True:
                time.sleep(3600)
        else:
            time.sleep(10)  # dem Browser Zeit geben, sich zu verbinden
            _wait_for_browser_clients(server)
    except KeyboardInterrupt:
        pass
    finally:
        loop.run(server.stop(), timeout=30)
        loop.stop()
        services.paths.instance_file.unlink(missing_ok=True)
    return 0


def run_sync(services: Services) -> int:
    """Aufruf aus der Aufgabenplanung bzw. launchd."""
    cfg = services.config.load()
    if not cfg.onboarded:
        return 0
    if cfg.schedule.spread_min > 0:
        # Zufälliger Versatz, damit nicht alle Installationen gleichzeitig bei ILIAS anklopfen.
        time.sleep(random.uniform(0, cfg.schedule.spread_min * 60))
    if _instance_call(services, "/api/ping") is not None:
        # Das offene Fenster soll den Abgleich machen – dann sieht man den Fortschritt dort.
        _instance_call(services, "/api/sync", {"trigger": "auto"})
        return 0

    async def main():
        return await services.engine.run("auto")

    async def update_quietly() -> None:
        """Auch ohne geöffnetes Fenster aktuell bleiben – viele öffnen Fach nach der Einrichtung nie wieder."""
        from .update import Updater, installed_with_installer

        if not cfg.options.auto_update or not installed_with_installer():
            return
        updater = Updater(services.paths.data_dir / "updates")
        if await updater.check() and await updater.download():
            updater.install(relaunch=False)

    async def everything():
        record = await main()
        try:
            await update_quietly()
        except Exception:
            pass
        return record

    if sys.platform == "win32":
        # PFERD-Hinweis: Windows-Loop stürzt nach asyncio.run gelegentlich beim Aufräumen ab.
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        record = loop.run_until_complete(everything())
        loop.run_until_complete(asyncio.sleep(0.5))
        loop.close()
    else:
        record = asyncio.run(everything())
    return 0 if record is None or record.status in ("ok", "partial") else 1
