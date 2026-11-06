"""Einstieg.

    fach                 App-Fenster (Standard)
    fach --sync          Abgleich ohne Fenster (Aufgabenplanung / launchd)
    fach --serve         Oberfläche im Browser (Entwicklung), läuft bis Strg+C
    fach --demo          mit Demo-ILIAS statt echtem Uni-Zugang
    fach --home PFAD     alle Daten von Fach in PFAD (Tests)
    fach --remove-schedule   Zeitplan entfernen (ruft der Deinstaller auf)
"""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__


def _fix_std_streams() -> None:
    # Fenster-Apps unter Windows haben kein stdout/stderr (None) – jedes print würde abstürzen.
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    _fix_std_streams()
    parser = argparse.ArgumentParser(prog="fach", description="ILIAS-Unterlagen automatisch auf deinen Rechner.")
    parser.add_argument("--sync", action="store_true", help="einmal abgleichen, ohne Fenster")
    parser.add_argument("--serve", action="store_true", help="Oberfläche im Browser statt im Fenster")
    parser.add_argument("--port", type=int, default=0, help="Port für --serve (Standard: zufällig)")
    parser.add_argument("--dev", action="store_true", help="Entwicklung: fester Token 'dev', Debug-Fenster")
    parser.add_argument("--no-browser", action="store_true", help="mit --serve: keinen Browser öffnen")
    parser.add_argument("--demo", action="store_true", help="Demo-ILIAS statt echtem Uni-Zugang")
    parser.add_argument("--home", help="eigener Datenordner (z. B. für Tests)")
    parser.add_argument("--remove-schedule", action="store_true", help="Zeitplan aus dem System entfernen (Deinstallation)")
    parser.add_argument("--version", action="version", version=f"Fach {__version__}")
    args = parser.parse_args(argv)

    from .app import build_services, demo_home, use_home

    demo = args.demo or bool(os.environ.get("FACH_DEMO"))
    use_home(args.home or (demo_home() if demo and not os.environ.get("FACH_HOME") else None))
    if demo:
        os.environ["FACH_DEMO"] = "1"

    services = build_services(demo=demo)
    from . import desktop

    if args.remove_schedule:
        services.platform.remove_schedule()
        return 0
    if args.sync:
        return desktop.run_sync(services)
    if args.serve:
        return desktop.run_browser(services, port=args.port, token="dev" if args.dev else None,
                                   open_browser=not args.no_browser, keep_alive=True)
    return desktop.run_window(services, dev=args.dev)


if __name__ == "__main__":
    sys.exit(main())
