"""Einstiegsskript für PyInstaller (braucht eine Datei, kein -m)."""

import sys

from fach.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
