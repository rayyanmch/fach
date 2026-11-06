"""Die einzige Stelle, die PFERD-Interna kennt. Getestet gegen PFERD 3.10.1 (in requirements gepinnt).

Warum zur Laufzeit statt die installierte Datei zu ändern (wie ~/ilias-sync/patch-pferd.py)?
In der gebauten App liegt PFERD als kompilierter Code im Paket – dort lässt sich nichts patchen.

Köln-Probleme von PFERD und wie sie hier gelöst werden:
1. ILIAS liegt unter einem Unterpfad (…/ilias). PFERD baut Login- und Download-Adressen mit
   urljoin(base_url, "/login.php") – der führende Schrägstrich wirft "/ilias" weg → 404.
   → `fixed_urljoin` behandelt die Basisadresse als Ordner. Bereits korrekte Aufrufe bleiben unverändert;
     falls PFERD das irgendwann selbst behebt, ist der Fix wirkungslos statt schädlich.
2. Mit links=ignore löst PFERD Link-Ziele trotzdem auf; das schlägt in Köln fehl und bricht den Kurs ab.
   → FachCrawler._handle_link prüft vorher.
3. PFERD legt .report und .cookies in jeden Kursordner – auf Windows sichtbar und verwirrend.
   → Beides liegt im App-Datenordner.
4. PFERD schreibt mit rich auf die Konsole; eine Fenster-App unter Windows hat keine (stdout = None).
   → Ausgabe geht in unsere Logdatei, Fortschrittsbalken sind abgeschaltet.
"""

from __future__ import annotations

import configparser
from contextlib import contextmanager
from pathlib import Path, PurePath
from typing import IO, Any, Callable, Optional
from urllib.parse import urljoin as _std_urljoin
from urllib.parse import urlsplit

from PFERD.auth import Authenticator, AuthError
from PFERD.config import Config
from PFERD.crawl.ilias import ilias_web_crawler as _crawler_mod
from PFERD.crawl.ilias import kit_ilias_html as _html_mod
from PFERD.crawl.ilias.ilias_web_crawler import IliasWebCrawler, IliasWebCrawlerSection
from PFERD.logging import log
from rich.console import Console
from rich.live import Live

PFERD_TESTED_VERSION = "3.10.1"

_ROOTS: set[str] = set()


def fixed_urljoin(base: Any, url: Any, allow_fragments: bool = True) -> Any:
    if isinstance(base, str) and isinstance(url, str) and base in _ROOTS:
        prefix = urlsplit(base).path.rstrip("/")
        if url.startswith("/") and not url.startswith("//") and prefix and not (
            url == prefix or url.startswith(prefix + "/")
        ):
            url = url[1:]  # PFERD meinte „relativ zur ILIAS-Wurzel“, nicht „relativ zur Domain“
        base = base + "/"
    return _std_urljoin(base, url, allow_fragments)


_installed = False


def install(base_url: str) -> None:
    """Einmal pro Prozess aufrufen, bevor ein Crawler läuft."""
    global _installed
    _ROOTS.add(base_url.rstrip("/"))
    if _installed:
        return
    _crawler_mod.urljoin = fixed_urljoin  # type: ignore[attr-defined]
    _html_mod.urljoin = fixed_urljoin  # type: ignore[attr-defined]

    log.output_explain = False
    log.output_status = True
    log.output_report = False
    log.output_not_deleted = False
    set_log_stream(None)

    @contextmanager
    def _no_progress():
        yield

    # Fortschrittsbalken abschalten; exclusive_output() verlangt aber „Fortschritt läuft“.
    log.show_progress = _no_progress  # type: ignore[method-assign]
    log._showing_progress = True  # noqa: SLF001
    _installed = True


class _NullIO:
    def write(self, s: str) -> int:
        return len(s)

    def flush(self) -> None:
        pass


def set_log_stream(stream: Optional[IO[str]]) -> None:
    """Wohin PFERD schreibt (Logdatei des aktuellen Abgleichs). None = nirgendwohin."""
    log.console = Console(file=stream or _NullIO(), width=200, no_color=True, highlight=False,
                          force_terminal=False, force_jupyter=False, soft_wrap=True)
    log._live = Live(console=log.console, transient=True)  # noqa: SLF001


class AppAuthenticator(Authenticator):
    """Gibt die Zugangsdaten aus der App weiter. Falsche Daten → AuthError (PFERD fragt nie nach)."""

    def __init__(self, username: str, password: str):
        super().__init__("auth:fach")
        self._username = username
        self._password = password

    async def credentials(self) -> tuple[str, str]:
        return self._username, self._password

    def invalidate_credentials(self) -> None:
        raise AuthError("Kennung oder Passwort falsch")

    def invalidate_username(self) -> None:
        raise AuthError("Kennung falsch")

    def invalidate_password(self) -> None:
        raise AuthError("Passwort falsch")


class FachCrawler(IliasWebCrawler):
    def __init__(self, name: str, section: configparser.SectionProxy, config: Config,
                 authenticators: dict[str, Authenticator], *, report_path: Path, cookie_file: Path,
                 on_progress: Optional[Callable[[str, str], None]] = None):
        super().__init__(name, IliasWebCrawlerSection(section), config, authenticators)
        # Fix 3: Zustand in den App-Datenordner
        self._cookie_jar_path = cookie_file
        self._shared_cookie_jar_paths = None
        self._output_dir._report_path = report_path  # noqa: SLF001
        self._on_progress = on_progress

    async def _handle_link(self, element, element_path):  # type: ignore[override]
        # Fix 2
        if not self._links.extension():
            return None
        return await super()._handle_link(element, element_path)

    async def crawl(self, path: PurePath):  # type: ignore[override]
        token = await super().crawl(path)
        if token is not None and self._on_progress:
            self._on_progress("scan", path.as_posix())
        return token

    async def download(self, path: PurePath, **kwargs: Any):  # type: ignore[override]
        token = await super().download(path, **kwargs)
        if token is not None and self._on_progress:
            self._on_progress("download", path.as_posix())
        return token


def build_config(working_dir: Path, sections: dict[str, dict[str, str]]) -> Config:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_dict({
        "DEFAULT": {"working_dir": str(working_dir), "check_for_updates": "no", "share_cookies": "no"},
        **sections,
    })
    return Config(parser)


# Ignoriert: versteckte Dateien und die Kursbeschreibung als HTML-Seite.
DEFAULT_TRANSFORM = "\\..+ -name-re-> !\nDescription\\.html -name-re-> !"


def course_section(base_url: str, client_id: str, target: str, output_dir: str, videos: bool) -> dict[str, str]:
    return {
        "type": "ilias-web",
        "base_url": base_url,
        "login_type": "local",
        "client_id": client_id,
        "auth": "auth:fach",
        "target": target,
        "output_dir": output_dir,
        "on_conflict": "local-first",   # eigene Änderungen/Notizen werden nie überschrieben oder gelöscht
        "redownload": "never-smart",
        "tasks": "1",                   # schonend für den ILIAS-Server
        "downloads": "1",
        "links": "ignore",
        "videos": "yes" if videos else "no",
        "forums": "no",
        "transform": DEFAULT_TRANSFORM,
    }
