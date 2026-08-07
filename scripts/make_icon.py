"""Render packaging/wordmute.ico from the designer's SVG mark
(resources/theme/wordmute-icon.svg). Used by the desktop shortcut,
the PyInstaller build, and the installer.
Run: python scripts/make_icon.py (offscreen-safe)."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
SVG = ROOT / "wordmute_app" / "resources" / "theme" / "wordmute-icon.svg"
OUT = ROOT / "packaging" / "wordmute.ico"


def render(size: int) -> QPixmap:
    renderer = QSvgRenderer(str(SVG))
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    return QPixmap.fromImage(image)


def main():
    QGuiApplication(sys.argv)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not render(256).save(str(OUT), "ICO"):
        sys.exit("failed to write ICO")
    print(f"icon written: {OUT}")


if __name__ == "__main__":
    main()
