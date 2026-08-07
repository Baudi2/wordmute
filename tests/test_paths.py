"""Cache naming, input collection, output naming."""

from pathlib import Path

import pytest

from wordmute_app.engine import wordmute as wm


def test_cache_path_whisper_untagged():
    assert wm._cache_path(Path("v.mp4"), "whisper").name == "v.mp4.words.json"


def test_cache_path_gigaam_tagged():
    assert wm._cache_path(Path("v.mp4"), "gigaam").name == "v.mp4.gigaam.words.json"


def test_collect_inputs_skips_clean_and_nonmedia(tmp_path):
    (tmp_path / "b.mp4").touch()
    (tmp_path / "a.mkv").touch()
    (tmp_path / "a.clean.mkv").touch()
    (tmp_path / "notes.txt").touch()
    files = wm.collect_inputs([tmp_path])
    assert [f.name for f in files] == ["a.mkv", "b.mp4"]  # sorted, filtered


def test_collect_inputs_missing_path_exits(tmp_path):
    with pytest.raises(SystemExit):
        wm.collect_inputs([tmp_path / "nope.mp4"])


def test_collect_inputs_empty_dir_exits(tmp_path):
    with pytest.raises(SystemExit):
        wm.collect_inputs([tmp_path])


def test_output_for_default_and_dir(tmp_path):
    inp = tmp_path / "v.mp4"
    assert wm.output_for(inp, None, multi=False).name == "v.clean.mp4"
    outdir = tmp_path / "out"
    got = wm.output_for(inp, outdir, multi=True)
    assert got == outdir / "v.clean.mp4"
    assert outdir.is_dir()  # created on demand


def test_output_for_explicit_file(tmp_path):
    inp = tmp_path / "v.mp4"
    out = tmp_path / "custom.mp4"
    assert wm.output_for(inp, out, multi=False) == out
