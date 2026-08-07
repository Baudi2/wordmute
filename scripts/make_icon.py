"""Generate packaging/wordmute.ico — a simple flat 'muted speaker' mark.
Run: python scripts/make_icon.py (offscreen-safe)."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QPainter, QPen, \
    QPixmap, QPolygonF


def draw(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 256.0

    p.setBrush(QBrush(QColor("#2b3a55")))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(8 * s, 8 * s, 240 * s, 240 * s), 48 * s, 48 * s)

    # speaker body
    p.setBrush(QBrush(QColor("#e8ecf4")))
    p.drawRect(QRectF(56 * s, 104 * s, 40 * s, 48 * s))
    p.drawPolygon(QPolygonF([
        QPointF(96 * s, 104 * s), QPointF(148 * s, 60 * s),
        QPointF(148 * s, 196 * s), QPointF(96 * s, 152 * s),
    ]))

    # mute slash
    pen = QPen(QColor("#e05d5d"), 22 * s, Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(178 * s, 88 * s), QPointF(74 * s, 192 * s))
    p.end()
    return pm


def main():
    QGuiApplication(sys.argv)
    out = Path(__file__).resolve().parents[1] / "packaging" / "wordmute.ico"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not draw(256).save(str(out), "ICO"):
        sys.exit("failed to write ICO")
    print(f"icon written: {out}")


if __name__ == "__main__":
    main()
