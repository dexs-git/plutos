# PyInstaller-Konfiguration für die Qt-Version von Plutos.
# Aufruf aus dem Repo-Wurzelverzeichnis:  pyinstaller packaging/plutos.spec --noconfirm
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
ICONS = ROOT / "packaging" / "icons"

if sys.platform == "win32":
    exe_icon = str(ICONS / "plutos.ico")
elif sys.platform == "darwin":
    exe_icon = str(ICONS / "plutos.icns")
else:
    exe_icon = None

a = Analysis(
    [str(ROOT / "qt" / "main.py")],
    pathex=[str(ROOT / "qt")],
    datas=[(str(ROOT / "qt" / "icon.png"), "."), (str(ROOT / "qt" / "icon.svg"), ".")],
    hiddenimports=[],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.QtQml", "PySide6.QtQuick", "PySide6.Qt3DCore", "PySide6.QtMultimedia",
              "PySide6.QtPdf", "PySide6.QtCharts", "PySide6.QtDataVisualization"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Plutos",
    console=False,
    icon=exe_icon,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Plutos")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Plutos.app",
        icon=str(ICONS / "plutos.icns"),
        bundle_identifier="de.plutos.haushaltsbuch",
        info_plist={
            "CFBundleDisplayName": "Plutos",
            "NSHighResolutionCapable": True,
        },
    )
