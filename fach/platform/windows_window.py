"""Eigene Titelleiste unter Windows: rahmenloses pywebview-Fenster, das sich trotzdem wie ein Fenster verhält.

pywebview kann rahmenlos, aber nicht ziehen/skalieren. Die Oberfläche meldet einen Mausklick auf die Leiste
bzw. eine Kante; hier schicken wir dem Fenster dieselbe Nachricht, die Windows bei einem Klick auf eine echte
Titelleiste erzeugt (WM_NCLBUTTONDOWN + HTCAPTION/HTLEFT …). Windows übernimmt dann das Ziehen selbst –
inklusive Mehrbildschirm. So macht es auch Tauri/wry für WebView2.

Alles hier läuft auf dem UI-Thread von WinForms (BeginInvoke) und ist in try/except gekapselt: Ein Fehler darf
nie das Fenster unbedienbar machen. Rückfall: Einstellungen → „Windows-Titelleiste verwenden“.
"""

from __future__ import annotations

import ctypes
import logging
from typing import Any, Callable, Optional

log = logging.getLogger("fach.window")

WM_NCLBUTTONDOWN = 0xA1
HIT = {"caption": 2, "left": 10, "right": 11, "top": 12, "topleft": 13, "topright": 14,
       "bottom": 15, "bottomleft": 16, "bottomright": 17}
GWL_STYLE = -16
WS_SYSMENU, WS_MINIMIZEBOX = 0x00080000, 0x00020000


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class WindowsChrome:
    def __init__(self, window: Any):
        self.window = window
        self._normal: Any = None      # gespeicherte Größe vor dem Maximieren
        self.maximized = False

    # --- Hilfen ---------------------------------------------------------------

    def _form(self) -> Any:
        return getattr(self.window, "native", None)

    def _hwnd(self) -> int:
        return int(self._form().Handle.ToInt64())

    def _ui(self, fn: Callable[[], None]) -> bool:
        form = self._form()
        if form is None:
            return False
        from System import Action  # type: ignore[import-not-found]

        def safe() -> None:
            try:
                fn()
            except Exception:
                log.exception("Fensteraktion fehlgeschlagen")

        form.BeginInvoke(Action(safe))
        return True

    # --- nach dem Öffnen ----------------------------------------------------------

    def prepare(self) -> None:
        """Runde Ecken (Windows 11) und Minimieren per Taskleisten-Klick für das rahmenlose Fenster."""
        def do() -> None:
            hwnd = self._hwnd()
            u32 = ctypes.windll.user32  # type: ignore[attr-defined]
            get = getattr(u32, "GetWindowLongPtrW", u32.GetWindowLongW)
            put = getattr(u32, "SetWindowLongPtrW", u32.SetWindowLongW)
            get.restype = ctypes.c_ssize_t
            put(hwnd, GWL_STYLE, get(hwnd, GWL_STYLE) | WS_SYSMENU | WS_MINIMIZEBOX)
            corner = ctypes.c_int(2)  # DWMWCP_ROUND
            try:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner), 4)  # type: ignore[attr-defined]
            except Exception:
                pass  # Windows 10: keine runden Ecken, egal

        self._ui(do)

    # --- Aktionen aus der Oberfläche ----------------------------------------------

    def begin_drag(self, edge: str = "caption") -> bool:
        hit = HIT.get(edge)
        if hit is None:
            return False

        def do() -> None:
            u32 = ctypes.windll.user32  # type: ignore[attr-defined]
            pt = _POINT()
            u32.GetCursorPos(ctypes.byref(pt))
            if self.maximized and edge == "caption":
                self._restore_under_cursor(pt)
            elif self.maximized:
                return  # maximiert: keine Größenänderung an den Kanten
            u32.ReleaseCapture()
            lparam = (pt.y & 0xFFFF) << 16 | (pt.x & 0xFFFF)
            u32.PostMessageW(self._hwnd(), WM_NCLBUTTONDOWN, hit, lparam)

        return self._ui(do)

    def _restore_under_cursor(self, pt: _POINT) -> None:
        """Wie bei normalen Fenstern: maximiert anfassen und ziehen = verkleinern, Maus bleibt an der gleichen Stelle."""
        from System.Drawing import Rectangle  # type: ignore[import-not-found]

        form = self._form()
        full = form.Bounds
        normal = self._normal or Rectangle(full.X, full.Y, 1160, 780)
        ratio = (pt.x - full.X) / max(1, full.Width)
        x = int(pt.x - normal.Width * ratio)
        form.Bounds = Rectangle(x, pt.y - 16, normal.Width, normal.Height)
        self._normal, self.maximized = None, False

    def toggle_maximize(self) -> bool:
        def do() -> None:
            from System.Windows.Forms import Screen  # type: ignore[import-not-found]

            form = self._form()
            if not self.maximized:
                self._normal = form.Bounds
                form.Bounds = Screen.FromHandle(form.Handle).WorkingArea  # nicht über die Taskleiste
                self.maximized = True
            else:
                if self._normal is not None:
                    form.Bounds = self._normal
                self._normal, self.maximized = None, False

        self._ui(do)
        return not self.maximized  # Zustand nach der Aktion (BeginInvoke läuft gleich danach)

    def minimize(self) -> None:
        self.window.minimize()

    def close(self) -> None:
        self.window.destroy()

    # --- Dateien nach außen ziehen ------------------------------------------------

    def start_file_drag(self, paths: list[str]) -> bool:
        """Echtes Windows-Drag&Drop mit „Kopieren“ – wie aus dem Explorer, z. B. in einen KI-Chat im Browser."""
        def do() -> None:
            from System import Array, String  # type: ignore[import-not-found]
            from System.Windows.Forms import DataFormats, DataObject, DragDropEffects  # type: ignore[import-not-found]

            ctypes.windll.user32.ReleaseCapture()  # type: ignore[attr-defined]
            data = DataObject(DataFormats.FileDrop, Array[String](paths))
            self._form().DoDragDrop(data, DragDropEffects.Copy)

        return self._ui(do)


def try_chrome(window: Any) -> Optional[WindowsChrome]:
    try:
        return WindowsChrome(window)
    except Exception:
        log.exception("Eigene Titelleiste nicht verfügbar")
        return None
