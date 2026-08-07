"""Humanized time formatting."""

from wordmute_app.ui.main_window import fmt_duration, fmt_eta, fmt_hms


def test_fmt_hms_seconds_only():
    assert fmt_hms(45) == "45 s"
    assert fmt_hms(0) == "0 s"


def test_fmt_hms_minutes_and_seconds():
    assert fmt_hms(89) == "1 min 29 s"
    assert fmt_hms(120) == "2 min"


def test_fmt_hms_hours():
    assert fmt_hms(3900) == "1 h 5 min"
    assert fmt_hms(7200) == "2 h"
    assert fmt_hms(3661) == "1 h 1 min"


def test_fmt_eta_wraps_hms():
    assert fmt_eta(89) == "~1 min 29 s left"
    assert fmt_eta(45) == "~45 s left"
    assert fmt_eta(0.4) == "~1 s left"  # never shows zero


def test_fmt_duration_clock_style():
    assert fmt_duration(65) == "1:05"
    assert fmt_duration(3661) == "1:01:01"
    assert fmt_duration(None) == "—"
