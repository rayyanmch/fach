"""Kompositionswurzel: Hier – und nur hier – werden die Bausteine zusammengesteckt.

    core (Konfig, Verlauf, Sperre)  ←  sync.engine  ←  server.api  ←  desktop / Browser
                     ↑                    ↓
              platform (OS)         ilias (PFERD oder Demo)

Kein Baustein importiert einen, der weiter rechts steht. So bleibt z. B. der Abgleich ohne
Oberfläche testbar, und Windows/macOS-Unterschiede stecken nur in platform/.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .core.config import ConfigStore
from .core.events import EventBus
from .core.paths import AppPaths, app_paths
from .core.secrets import KeyringStore, MemoryStore, SecretStore
from .core.store import Store
from .core.university import University, get_university
from .ilias import IliasBackend
from .platform import Platform, get_platform
from .sync.engine import SyncEngine


@dataclass
class Services:
    paths: AppPaths
    config: ConfigStore
    store: Store
    secrets: SecretStore
    uni: University
    backend: IliasBackend
    platform: Platform
    bus: EventBus
    engine: SyncEngine
    demo: bool


class _DemoPlatform:
    """Im Demo-Modus nie den echten Zeitplan des Systems anfassen."""

    def __init__(self, real: Platform):
        self._real = real
        self.name = f"{real.name}-demo"
        self._installed = False

    def apply_schedule(self, schedule) -> None:
        self._installed = bool(schedule.enabled)

    def remove_schedule(self) -> None:
        self._installed = False

    def schedule_installed(self) -> bool:
        return self._installed

    def notify(self, title: str, body: str) -> None:
        self._real.notify(title, body)

    def open_path(self, path: Path) -> None:
        self._real.open_path(path)

    def reveal_path(self, path: Path) -> None:
        self._real.reveal_path(path)

    def open_with(self, path: Path) -> None:
        self._real.open_with(path)

    def copy_files(self, paths: list[Path]) -> None:
        self._real.copy_files(paths)

    def trash(self, path: Path) -> None:
        self._real.trash(path)


def build_services(demo: bool = False) -> Services:
    paths = app_paths()
    config = ConfigStore(paths.config_file)
    cfg = config.load()
    uni = get_university(cfg.university)
    store = Store(paths.db_file)
    bus = EventBus()
    platform: Platform = get_platform()

    backend: IliasBackend
    secrets: SecretStore
    if demo:
        from .ilias.demo import DemoIlias

        backend, secrets, platform = DemoIlias(), MemoryStore(), _DemoPlatform(platform)
    else:
        from .ilias.real import RealIlias

        backend, secrets = RealIlias(uni, paths.pferd_dir), KeyringStore()

    engine = SyncEngine(config, store, backend, secrets, uni, paths, bus, notify=platform.notify)
    return Services(paths, config, store, secrets, uni, backend, platform, bus, engine, demo)


def demo_home() -> str:
    from platformdirs import user_data_path

    return str(user_data_path("Fach", appauthor=False) / "demo-home")


def use_home(path: str | None) -> None:
    if path:
        os.environ["FACH_HOME"] = str(Path(path).expanduser())
