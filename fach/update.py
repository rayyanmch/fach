"""Updates: neue Version aus GitHub-Releases holen und installieren.

Quelle: https://github.com/<repo>/releases/latest/download/latest.json – eine kleine Datei, die CI bei jedem
Release mitliefert (Version, Installer-Name, SHA-256, Notizen). Kein API-Aufruf, also kein Rate-Limit.

Sicherheit
- Nur HTTPS, nur von github.com/<repo>/releases/… (Weiterleitung auf GitHubs Speicher ist erlaubt).
- Der Installer wird gegen den SHA-256 aus latest.json geprüft. Das schützt vor kaputten Downloads, nicht vor
  einem kompromittierten GitHub-Konto – dafür bräuchte es Code-Signatur (siehe docs/IDEEN.md).
- Installiert wird nur, wenn Fach selbst per Installer installiert ist (sonst Hinweis mit Link).

Ablauf beim Installieren: Installer still starten (/VERYSILENT), Fach beendet sich, der Installer ersetzt die
Dateien und startet Fach neu – außer bei Updates aus dem Hintergrund-Abgleich (/nolaunch=1).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from . import __version__
from .core.paths import is_frozen

REPO = "rayyanmch/fach"
MANIFEST_URL = f"https://github.com/{REPO}/releases/latest/download/latest.json"
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"


def parse_version(v: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", v.split("-", 1)[0])
    return tuple(int(n) for n in nums[:3]) + (0,) * (3 - len(nums[:3]))


@dataclass
class UpdateState:
    status: str = "idle"          # idle | checking | uptodate | available | downloading | ready | installing | error
    current: str = __version__
    latest: str = ""
    notes: str = ""
    published: str = ""
    progress: float = 0.0
    error: str = ""
    checked: Optional[float] = None
    can_install: bool = False
    page: str = RELEASES_PAGE
    _manifest: dict[str, Any] = field(default_factory=dict, repr=False)

    def public(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("_manifest", None)
        return d


def installed_with_installer() -> bool:
    """Nur echte Installationen ersetzen – nicht die portable ZIP und nicht den Quellcode."""
    if not is_frozen() or sys.platform != "win32":
        return False
    return any(Path(sys.executable).parent.glob("unins*.exe"))


class Updater:
    def __init__(self, download_dir: Path, on_change: Optional[Callable[[dict], None]] = None):
        self.dir = download_dir
        self.on_change = on_change
        self.state = UpdateState(can_install=installed_with_installer())
        self._lock = asyncio.Lock()
        self._installer: Optional[Path] = None

    def _set(self, **kw: Any) -> None:
        for k, v in kw.items():
            setattr(self.state, k, v)
        if self.on_change:
            self.on_change(self.state.public())

    async def check(self) -> bool:
        """True, wenn eine neuere Version bereitsteht."""
        import aiohttp

        if self.state.status in ("downloading", "installing"):
            return self.state.status != "uptodate"
        self._set(status="checking", error="")
        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": f"Fach/{__version__}"}) as s:
                async with s.get(MANIFEST_URL) as resp:
                    if resp.status == 404:
                        raise RuntimeError("Noch kein Release veröffentlicht oder nicht öffentlich erreichbar.")
                    resp.raise_for_status()
                    manifest = json.loads(await resp.text())
            latest = str(manifest["version"])
            newer = parse_version(latest) > parse_version(__version__)
            self.state._manifest = manifest
            self._set(status="available" if newer else "uptodate", latest=latest, notes=str(manifest.get("notes", ""))[:2000],
                      published=str(manifest.get("published", "")), checked=time.time())
            return newer
        except Exception as e:
            self._set(status="error", error=_short(e), checked=time.time())
            return False

    async def download(self) -> Optional[Path]:
        import aiohttp

        async with self._lock:
            m = self.state._manifest
            if self.state.status not in ("available", "error") or not m:
                return self._installer
            name = str(m.get("setup", ""))
            url = f"{DOWNLOAD_PREFIX}v{m['version']}/{name}"
            if not re.fullmatch(r"Fach-Setup-[\w.\-]+\.exe", name):
                self._set(status="error", error="Ungültiger Dateiname im Update.")
                return None
            self.dir.mkdir(parents=True, exist_ok=True)
            target = self.dir / name
            part = target.with_suffix(".part")
            self._set(status="downloading", progress=0.0, error="")
            try:
                digest = hashlib.sha256()
                timeout = aiohttp.ClientTimeout(total=None, sock_read=60)
                async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": f"Fach/{__version__}"}) as s:
                    async with s.get(url) as resp:
                        resp.raise_for_status()
                        # Eine HTTPS-Quelle darf nie auf unverschlüsseltes HTTP umleiten.
                        if DOWNLOAD_PREFIX.startswith("https://") and not str(resp.url).startswith("https://"):
                            raise RuntimeError("Unsichere Weiterleitung.")
                        total = resp.content_length or int(m.get("size", 0)) or 0
                        done = 0
                        last = 0.0
                        with open(part, "wb") as fh:
                            async for chunk in resp.content.iter_chunked(256 * 1024):
                                fh.write(chunk)
                                digest.update(chunk)
                                done += len(chunk)
                                if total and time.monotonic() - last > 0.25:
                                    last = time.monotonic()
                                    self._set(progress=min(done / total, 0.99))
                if digest.hexdigest().lower() != str(m.get("sha256", "")).lower():
                    part.unlink(missing_ok=True)
                    raise RuntimeError("Prüfsumme stimmt nicht – Download verworfen.")
                part.replace(target)
                self._installer = target
                self._set(status="ready", progress=1.0)
                return target
            except Exception as e:
                part.unlink(missing_ok=True)
                self._set(status="error", error=_short(e))
                return None

    def install(self, relaunch: bool = True) -> bool:
        """Installer starten. Der Aufrufer beendet danach die App."""
        if not self._installer or not self.state.can_install:
            return False
        args = [str(self._installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
                f"/LOG={self.dir / 'update.log'}"]
        if not relaunch:
            args.append("/nolaunch=1")
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(args, creationflags=flags, close_fds=True)
        self._set(status="installing")
        return True

    def cleanup(self) -> None:
        """Alte Installer nach erfolgreichem Update entfernen."""
        for f in self.dir.glob("Fach-Setup-*"):
            if __version__ not in f.name:
                f.unlink(missing_ok=True)


def _short(e: Exception) -> str:
    text = str(e) or type(e).__name__
    return text if len(text) < 160 else text[:157] + "…"
