"""Kleiner Ereignisbus: Der Abgleich meldet Fortschritt, die Oberfläche hört zu.

Kennt weder HTTP noch PFERD – nur Wörterbücher. Alle Abonnenten laufen im selben Event-Loop.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

Listener = Callable[[dict[str, Any]], None]


class EventBus:
    def __init__(self) -> None:
        self._listeners: list[Listener] = []

    def subscribe(self, fn: Listener) -> Callable[[], None]:
        self._listeners.append(fn)
        return lambda: self._listeners.remove(fn) if fn in self._listeners else None

    def emit(self, type_: str, **data: Any) -> None:
        event = {"type": type_, **data}
        for fn in list(self._listeners):
            try:
                fn(event)
            except Exception:  # ein kaputter Zuhörer darf den Abgleich nicht stoppen
                pass

    def queue(self, maxsize: int = 256) -> tuple[asyncio.Queue, Callable[[], None]]:
        """Abo als Queue – für Server-Sent Events. Volle Queue verwirft alte Ereignisse."""
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)

        def put(event: dict[str, Any]) -> None:
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(event)

        return q, self.subscribe(put)
