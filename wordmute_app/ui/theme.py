"""Theme loading: the Nocturne QSS files from the design handoff.

apply_theme() sets the Fusion base style (predictable QSS rendering),
loads the requested stylesheet with icon urls rewritten to absolute
paths, and fixes the placeholder-text palette color the QSS cannot
reach. Safe to call again at runtime to switch themes live."""

import re

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import (QColor, QFontDatabase, QIcon, QImage, QPainter,
                           QPalette, QPixmap)
from PySide6.QtWidgets import QWidget

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
# the 0.6.1 rework sheet overrides rules from both earlier sheets (menu
# frame, install rows, empty states); the Models-tab sheet comes after
# it — the chain order is part of the design contract
FIX_THEMES = {
    "dark": "wordmute-0.6.1.qss",
    "light": "wordmute-0.6.1-light.qss",
}
MODELS_THEMES = {
    "dark": "wordmute-models.qss",
    "light": "wordmute-models-light.qss",
}
# Word Lists search bar (design round 4) — loads last
SEARCH_THEMES = {
    "dark": "wordmute-wordlist-search.qss",
    "light": "wordmute-wordlist-search-light.qss",
}
# match highlights are QTextCharFormat (not QSS): (match bg, current
# bg, current fg) per theme, from the handoff
FIND_HIGHLIGHT = {
    "dark": ("#2b2741", "#423a6a", "#d2cefd"),
    "light": ("#e7e5fe", "#d2cefd", "#5d5294"),
}
# the OS title bar painted as the app's chrome (Windows 11 DWM): caption
# background, caption text, window border — per theme
_TITLEBAR = {
    "dark": ("#131522", "#e9e9ed", "#292b31"),
    "light": ("#edf0fa", "#292b31", "#cfd3e5"),
}
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_BORDER_COLOR = 34
_DWMWA_CAPTION_COLOR = 35
_DWMWA_TEXT_COLOR = 36
DEFAULT_THEME = "dark"

_PLACEHOLDER = {"dark": "#75798c", "light": "#8b8fa3"}
_HOVER = {"dark": "#1f2130", "light": "#e4e7f5"}
_current_theme = DEFAULT_THEME


def theme_dir():
    return resources_dir() / "theme"


def load_stylesheet(name: str) -> str:
    name = name if name in THEMES else DEFAULT_THEME
    parts = []
    for table in (THEMES, SETUP_THEMES, FIX_THEMES, MODELS_THEMES,
                  SEARCH_THEMES):
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


def is_dark() -> bool:
    return _current_theme == "dark"


def _colorref(hex_color: str) -> int:
    """DWM wants COLORREF: 0x00BBGGRR."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return (b << 16) | (g << 8) | r


def apply_titlebar(widget) -> None:
    """Paint the OS caption of a top-level window in the theme's chrome
    colors, so the native title bar IS the app header (no in-app strip
    repeating the name one row below). Windows 11 DWM; on Windows 10 the
    color attributes are rejected and only dark mode applies — both
    cases are silently fine."""
    import sys
    if sys.platform != "win32" or not widget.isWindow():
        return
    try:
        import ctypes
        hwnd = int(widget.winId())
        dwm = ctypes.windll.dwmapi
        dark = ctypes.c_int(1 if is_dark() else 0)
        dwm.DwmSetWindowAttribute(hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE,
                                  ctypes.byref(dark), ctypes.sizeof(dark))
        caption, text, border = _TITLEBAR[_current_theme]
        for attribute, value in ((_DWMWA_CAPTION_COLOR, caption),
                                 (_DWMWA_TEXT_COLOR, text),
                                 (_DWMWA_BORDER_COLOR, border)):
            color = ctypes.c_uint(_colorref(value))
            dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(color),
                                      ctypes.sizeof(color))
    except (OSError, AttributeError, ValueError):
        pass


class _TitleBarFilter(QObject):
    """Every window and dialog gets the themed caption the moment it is
    shown — one place, instead of a call in each dialog class."""

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Show and isinstance(obj, QWidget)
                and obj.isWindow()
                and obj.windowType() in (Qt.Window, Qt.Dialog)):
            apply_titlebar(obj)
        return False


_titlebar_filter = None


def retint_titlebars(app) -> None:
    """After a live theme switch: recolor the captions already open."""
    for widget in app.topLevelWidgets():
        if widget.isVisible() and widget.windowType() in (Qt.Window,
                                                          Qt.Dialog):
            apply_titlebar(widget)


def apply_theme(app, name: str) -> None:
    global _current_theme, _titlebar_filter
    name = name if name in THEMES else DEFAULT_THEME
    _current_theme = name
    _register_fonts()
    app.setStyle("Fusion")
    app.setStyleSheet(load_stylesheet(name))
    palette = app.palette()
    palette.setColor(QPalette.PlaceholderText, QColor(_PLACEHOLDER[name]))
    app.setPalette(palette)
    if _titlebar_filter is None:
        _titlebar_filter = _TitleBarFilter(app)
        app.installEventFilter(_titlebar_filter)
    retint_titlebars(app)


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
    # retint whatever stroke the file hard-codes: check.svg ships in
    # the checkbox's dark ink and was invisible on a dark row
    svg = re.sub(r'stroke="#[0-9a-fA-F]{3,6}"', f'stroke="{tint}"', svg)
    svg = svg.replace("currentColor", tint)
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
