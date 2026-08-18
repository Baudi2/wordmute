"""Locale-aware user-facing formatting (design 0.6.1, sections 1d/1e).

Everything here follows the UI LANGUAGE, not the system locale, so a
Russian window never mixes «14 авг» with «4.4 GB»: dates come from
QLocale, sizes and rates get Russian unit names and a decimal comma.
"""

from PySide6.QtCore import QDate, QDateTime, QLocale, Qt

from .i18n import current_language, tr


def ui_locale() -> QLocale:
    return QLocale(current_language() or "en")


def _decimal(value: float, digits: int = 1) -> str:
    return ui_locale().toString(float(value), "f", digits)


def fmt_bytes(n) -> str:
    """851 МБ · 4,4 ГБ — the decimal separator comes from the locale,
    never from str.replace.

    Binary steps with decimal unit names, like Windows Explorer: users
    compare these numbers against the file properties dialog. Keeps the
    same math as the Qt-free core.models.fmt_size (which the engine and
    tests use) — the only difference is the localized unit and comma."""
    if not n:
        return "0 " + tr("MB")
    n = float(n)
    if n >= 1024 ** 3:
        return f"{_decimal(n / 1024 ** 3)} {tr('GB')}"
    if n >= 1024 ** 2:
        return f"{_decimal(n / 1024 ** 2, 0)} {tr('MB')}"
    return f"{_decimal(n / 1024, 0)} {tr('kB')}"


def fmt_rate(bytes_per_second) -> str:
    """2,3 МБ/с — empty string when there is no measurement yet."""
    if not bytes_per_second:
        return ""
    bps = float(bytes_per_second)
    if bps >= 1024 ** 2:
        return f"{_decimal(bps / 1024 ** 2)} {tr('MB/s')}"
    return f"{_decimal(bps / 1024, 0)} {tr('kB/s')}"


def human_datetime(iso: str) -> str:
    """«сегодня 22:35» / «вчера 09:12» / «14 авг 09:12» /
    «29 дек 2025, 18:03» — today and yesterday read faster than a date,
    and month names come from the UI language."""
    stamp = QDateTime.fromString(iso, Qt.ISODate)
    if not stamp.isValid():
        return iso
    locale = ui_locale()
    today = QDate.currentDate()
    date, clock = stamp.date(), locale.toString(stamp.time(), "HH:mm")
    if date == today:
        return tr("today {}").format(clock)
    if date == today.addDays(-1):
        return tr("yesterday {}").format(clock)
    if date.year() == today.year():
        return locale.toString(stamp, "d MMM HH:mm")
    return locale.toString(stamp, "d MMM yyyy, HH:mm")


def full_datetime(iso: str) -> str:
    """The unabbreviated stamp for tooltips."""
    stamp = QDateTime.fromString(iso, Qt.ISODate)
    if not stamp.isValid():
        return iso
    return ui_locale().toString(stamp, "dddd, d MMMM yyyy, HH:mm:ss")
