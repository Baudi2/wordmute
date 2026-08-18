"""Theme loading: the Nocturne QSS files from the design handoff.

apply_theme() sets the Fusion base style (predictable QSS rendering),
loads the requested stylesheet with icon urls rewritten to absolute
paths, and fixes the placeholder-text palette color the QSS cannot
reach. Safe to call again at runtime to switch themes live."""

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import (QColor, QFontDatabase, QIcon, QImage, QPainter,
                           QPalette, QPixmap)

from ..core.config import resources_dir

THEMES = {
    "dark": "wordmute.qss",
    "light": "wordmute-light.qss",
}
# the setup wizard's sheet is appended to the base theme (it only adds
# rules keyed by objectName, per the design handoff)
SETUP_THEMES = {
    "dark": "wordmute-setup.qss",
    "light": "wordmute-setup-light.qss",
}
# the 0.6.1 rework sheet must come LAST — it overrides rules from both
# earlier sheets (menu frame, install rows, empty states)
FIX_THEMES = {
    "dark": "wordmute-0.6.1.qss",
    "light": "wordmute-0.6.1-light.qss",
}
DEFAULT_THEME = "dark"

_PLACEHOLDER = {"dark": "#75798c", "light": "#8b8fa3"}
_HOVER = {"dark": "#1f2130", "light": "#e4e7f5"}
_current_theme = DEFAULT_THEME


def theme_dir():
    return resources_dir() / "theme"


def load_stylesheet(name: str) -> str:
    name = name if name in THEMES else DEFAULT_THEME
    parts = []
    for table in (THEMES, SETUP_THEMES, FIX_THEMES):
        path = theme_dir() / table[name]
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
    qss = "\n".join(parts)
    # icon urls in the QSS are relative to the file; Qt resolves url()
    # against the process cwd, so rewrite to absolute (forward slashes)
    base = theme_dir().as_posix()
    return re.sub(r"url\((icons/[^)]+)\)", rf"url({base}/\1)", qss)


_fonts_loaded = False


def _register_fonts() -> None:
    """Bundle Inter (full Cyrillic coverage) so RU and EN text share the
    design's typeface; falls back to Segoe UI when absent."""
    global _fonts_loaded
    if _fonts_loaded:
        return
    fonts = theme_dir() / "fonts"
    if fonts.is_dir():
        for ttf in fonts.glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(ttf))
    _fonts_loaded = True


def hover_color() -> QColor:
    """Row-hover tint for the active theme (used by HoverRowTable —
    whole-row hover can't be expressed in QSS)."""
    return QColor(_HOVER[_current_theme])


def apply_theme(app, name: str) -> None:
    global _current_theme
    name = name if name in THEMES else DEFAULT_THEME
    _current_theme = name
    _register_fonts()
    app.setStyle("Fusion")
    app.setStyleSheet(load_stylesheet(name))
    palette = app.palette()
    palette.setColor(QPalette.PlaceholderText, QColor(_PLACEHOLDER[name]))
    app.setPalette(palette)


def app_icon() -> QIcon:
    return QIcon(str(theme_dir() / "wordmute-icon.svg"))


def _svg_pixmap(svg_text: str, size: int = 36) -> QPixmap:
    from PySide6.QtSvg import QSvgRenderer
    renderer = QSvgRenderer(svg_text.encode("utf-8"))
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    return QPixmap.fromImage(image)


def ui_icon(name: str, size: int = 14, color: str = None) -> QIcon:
    """A flat icon from resources/theme/icons, stroke retinted to the
    given color (defaults to the theme's muted tone)."""
    path = theme_dir() / "icons" / f"{name}.svg"
    if not path.exists():
        return QIcon()
    svg = path.read_text(encoding="utf-8")
    tint = color or ("#9397ab" if _current_theme == "dark" else "#595d6c")
    svg = svg.replace("#9397ab", tint).replace("currentColor", tint)
    return QIcon(_svg_pixmap(svg, size))


def nav_icon(name: str) -> QIcon:
    """Sidebar icon: muted stroke normally, accent when selected (the
    design recolors the same SVG rather than shipping two)."""
    path = theme_dir() / "icons" / "tabs" / f"{name}.svg"
    icon = QIcon()
    if not path.exists():
        return icon
    svg = path.read_text(encoding="utf-8")
    icon.addPixmap(_svg_pixmap(svg), QIcon.Normal)
    icon.addPixmap(_svg_pixmap(svg.replace("#9397ab", "#9184d9")),
                   QIcon.Selected)
    return icon
