"""FFmpeg shared-build discovery replaces the old hardcoded path."""

import os
from pathlib import Path

import pytest

from wordmute_app.engine import wordmute as wm


def test_no_hardcoded_user_path_in_source():
    src = Path(wm.__file__).read_text(encoding="utf-8")
    assert r"Users\badic" not in src


def test_configure_overrides_discovery(tmp_path):
    old = wm.FFMPEG_SHARED_BIN
    try:
        wm.configure_ffmpeg_shared_dir(tmp_path)
        assert wm.FFMPEG_SHARED_BIN == str(tmp_path)
        assert wm._ffmpeg_dll_dir_registered is False
    finally:
        wm.configure_ffmpeg_shared_dir(old)


@pytest.mark.skipif(os.name != "nt", reason="Windows-only discovery")
def test_discover_finds_dir_with_shared_dlls_if_any():
    found = wm.discover_ffmpeg_shared_dir()
    if found is None:
        pytest.skip("no ffmpeg shared build on this machine")
    p = Path(found)
    assert p.is_dir()
    assert any(p.glob("avcodec-*.dll"))
