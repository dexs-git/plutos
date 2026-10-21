"""Erzeugt aus qt/icon.svg die Programm-Icons (PNG, ICO, ICNS).

Aufruf (aus dem Repo-Wurzelverzeichnis):  python packaging/make_icons.py
Benötigt PySide6 (QtSvg) und Pillow. Die erzeugten Dateien liegen in
packaging/icons/ und sind eingecheckt – nur bei geändertem Icon neu erzeugen."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PIL import Image
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "packaging" / "icons"
OUT.mkdir(parents=True, exist_ok=True)

app = QGuiApplication(sys.argv)
renderer = QSvgRenderer(str(ROOT / "qt" / "icon.svg"))


def render(size):
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    path = OUT / f"_tmp_{size}.png"
    image.save(str(path))
    img = Image.open(path).convert("RGBA")
    path.unlink()
    return img


big = render(1024)
big.resize((256, 256), Image.LANCZOS).save(OUT / "plutos.png")
big.save(OUT / "plutos.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
big.save(OUT / "plutos.icns")
print("Icons erzeugt in", OUT)
