# PyInstaller-Bauplan für Fach.  Aufruf aus dem Projektordner:  pyinstaller packaging/fach.spec
#
# onedir statt onefile: startet schneller (kein Entpacken bei jedem Start) und löst seltener
# Fehlalarme von Virenscannern aus. Der Installer verpackt den Ordner.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
ICON = ROOT / "packaging" / "assets" / ("fach.ico" if sys.platform == "win32" else "fach.png")

hidden = collect_submodules("PFERD") + ["platformdirs"]
if sys.platform == "win32":
    hidden += ["keyring.backends.Windows", "win32ctypes.core"]
elif sys.platform == "darwin":
    hidden += ["keyring.backends.macOS"]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "fach" / "ui"), "fach/ui")],
    hiddenimports=hidden,
    excludes=["tkinter", "pytest", "PIL"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Fach",
    console=False,          # Fenster-App: kein Konsolenfenster (auch nicht beim geplanten Abgleich)
    icon=str(ICON),
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name="Fach", upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Fach.app",
        icon=None,
        bundle_identifier="de.fach.app",
        info_plist={"CFBundleName": "Fach", "CFBundleShortVersionString": "0.1.0", "NSHighResolutionCapable": True},
    )
