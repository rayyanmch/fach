"""Fortschritt und Restzeit eines Abgleichs schätzen.

PFERD weiß vorher nicht, wie viele Dateien ein Kurs hat – es entdeckt sie beim Durchsuchen. Deshalb
rechnen wir in Zeit: Jeder Kurs bekommt eine erwartete Dauer (aus früheren Läufen, sonst aus den in
diesem Lauf schon fertigen Kursen, sonst ein Startwert). Daraus folgen Prozent und Restzeit.

Eigenschaften, auf die die Oberfläche sich verlässt:
- Der Anteil wächst nie rückwärts (sonst springt der Balken).
- Solange es noch keine Grundlage gibt, ist die Restzeit None („wird geschätzt“).
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import Optional

DEFAULT_INITIAL_S = 75.0   # erster Abgleich eines Kurses: lädt alles herunter
DEFAULT_REGULAR_S = 35.0   # normaler Abgleich: hauptsächlich Durchsuchen


@dataclass
class _Course:
    expected: Optional[float]      # aus früheren Läufen
    initial: bool
    started: Optional[float] = None
    ended: Optional[float] = None


@dataclass
class Estimator:
    courses: list[_Course] = field(default_factory=list)
    started: float = field(default_factory=time.monotonic)
    _last_fraction: float = 0.0

    @classmethod
    def for_run(cls, expectations: list[tuple[Optional[float], bool]], now: Optional[float] = None) -> "Estimator":
        est = cls([_Course(e, i) for e, i in expectations])
        est.started = now if now is not None else time.monotonic()
        return est

    def start(self, index: int, now: Optional[float] = None) -> None:
        self.courses[index].started = now if now is not None else time.monotonic()

    def finish(self, index: int, now: Optional[float] = None) -> float:
        c = self.courses[index]
        c.ended = now if now is not None else time.monotonic()
        return c.ended - (c.started or c.ended)

    def _expected(self, c: _Course) -> tuple[float, bool]:
        """(erwartete Dauer, verlässlich?)"""
        if c.expected:
            return c.expected, True
        done = [x.ended - x.started for x in self.courses
                if x.ended is not None and x.started is not None and x.initial == c.initial]
        if done:
            return statistics.median(done), True
        known = [x.expected for x in self.courses if x.expected]
        if known:
            return statistics.median(known) * (2.0 if c.initial else 1.0), True
        return (DEFAULT_INITIAL_S if c.initial else DEFAULT_REGULAR_S), False

    def snapshot(self, now: Optional[float] = None) -> tuple[float, Optional[float]]:
        """(Anteil 0..1, Restzeit in Sekunden oder None)."""
        now = now if now is not None else time.monotonic()
        done_time = total = 0.0
        reliable = True
        for c in self.courses:
            if c.ended is not None and c.started is not None:
                spent = c.ended - c.started
                done_time += spent
                total += spent
                continue
            exp, ok = self._expected(c)
            reliable = reliable and ok
            if c.started is not None:
                elapsed = now - c.started
                done_time += elapsed
                # Dauert es länger als erwartet, wächst die Erwartung mit – der Kurs ist nie „fast fertig“, solange er läuft.
                total += max(exp, elapsed * 1.15 + 2)
            else:
                total += exp
        if total <= 0:
            return 1.0, 0.0
        fraction = max(self._last_fraction, min(done_time / total, 0.99))
        self._last_fraction = fraction
        remaining = max(0.0, total - done_time)
        if not reliable and now - self.started < 20:
            return fraction, None
        return fraction, remaining
