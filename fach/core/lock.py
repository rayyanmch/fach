"""Prozessübergreifende Sperre: Es läuft immer höchstens ein Abgleich – egal ob aus der App
oder aus der Aufgabenplanung. Das Betriebssystem gibt die Sperre frei, wenn der Prozess stirbt.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


class ProcessLock:
    def __init__(self, path: Path):
        self.path = path
        self._fh = None

    def acquire(self) -> bool:
        if self._fh is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+b")
        try:
            if sys.platform == "win32":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        fh.seek(0)
        fh.truncate()
        fh.write(str(os.getpid()).encode())
        fh.flush()
        self._fh = fh
        return True

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            self._fh.close()
            self._fh = None

    def is_held_elsewhere(self) -> bool:
        """Hält ein anderer Prozess die Sperre? (Kurz probieren, sofort wieder freigeben.)"""
        if self._fh is not None:
            return False
        if self.acquire():
            self.release()
            return False
        return True

    def __enter__(self) -> "ProcessLock":
        if not self.acquire():
            raise RuntimeError("Sperre belegt")
        return self

    def __exit__(self, *exc) -> None:
        self.release()
