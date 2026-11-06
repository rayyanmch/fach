"""Selbsttest der gebauten App: Sind alle Bausteine im Paket und ladbar?

PyInstaller übersieht gern dynamisch geladene Module (Keyring-Backends, PFERD-Crawler, pywebview).
`Fach.exe --selftest ergebnis.json` prüft das ohne Fenster und ohne Netz. CI ruft es nach jedem Build auf.
"""

from __future__ import annotations

import json
import sys
import tempfile
import traceback
from pathlib import Path


def run(out: str) -> int:
    checks: dict[str, str] = {}

    def check(name: str, fn) -> None:
        try:
            checks[name] = str(fn() or "ok")
        except Exception:
            checks[name] = "FEHLER: " + traceback.format_exc(limit=3).strip().splitlines()[-1]

    from .core.paths import resource_dir
    from .core.university import KOELN

    check("ui", lambda: "ok" if (resource_dir() / "ui" / "index.html").exists() else 1 / 0)
    check("fonts", lambda: str(len(list((resource_dir() / "ui" / "fonts").glob("*.woff2")))))

    def pferd() -> str:
        from .ilias import pferd_runtime as rt
        from .ilias.real import RealIlias

        RealIlias(KOELN, Path(tempfile.mkdtemp()) / "pferd")
        import PFERD.crawl.ilias.ilias_web_crawler as mod

        assert mod.urljoin is rt.fixed_urljoin
        return "ok"

    check("pferd", pferd)

    def keyring() -> str:
        from .core.secrets import KeyringStore

        store = KeyringStore()
        store.get("Fach Selbsttest", "niemand")  # nur lesen, legt nichts an
        return type(store._kr.get_keyring()).__name__

    check("keyring", keyring)

    def window() -> str:
        import webview

        return "FileDialog" if hasattr(webview, "FileDialog") else "alt"

    check("pywebview", window)

    def platform() -> str:
        from .platform import get_platform

        return get_platform().name

    check("platform", platform)

    ok = all(not v.startswith("FEHLER") for v in checks.values())
    Path(out).write_text(json.dumps({"ok": ok, "frozen": bool(getattr(sys, "frozen", False)), **checks},
                                    ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if ok else 1
