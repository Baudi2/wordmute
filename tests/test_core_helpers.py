"""expand_inputs, build_plan, media_duration."""

import subprocess

from wordmute_app.core import probe
from wordmute_app.core.jobs import build_plan, expand_inputs


def test_expand_inputs_mixed_files_and_dirs(tmp_path):
    d = tmp_path / "videos"
    d.mkdir()
    (d / "b.mp4").touch()
    (d / "a.mkv").touch()
    (d / "a.clean.mkv").touch()
    (d / "junk.txt").touch()
    single = tmp_path / "solo.mp3"
    single.touch()
    missing = tmp_path / "nope.mp4"

    got = expand_inputs([d, single, missing, tmp_path / "x.txt"])
    assert [f.name for f in got] == ["a.mkv", "b.mp4", "solo.mp3"]


def test_expand_inputs_skips_clean_direct_file(tmp_path):
    f = tmp_path / "v.clean.mp4"
    f.touch()
    assert expand_inputs([f]) == []


def test_build_plan_maps_models():
    assert build_plan(["gigaam", "whisper"], "large-v3", "v3_e2e_rnnt") == \
        [("gigaam", "v3_e2e_rnnt"), ("whisper", "large-v3")]


def test_media_duration_parses_ffprobe_output(tmp_path, monkeypatch):
    def fake_run(cmd, **kwargs):
        assert "ffprobe" in cmd[0]
        return subprocess.CompletedProcess(cmd, 0, stdout="123.456\n", stderr="")
    monkeypatch.setattr(probe.subprocess, "run", fake_run)
    assert probe.media_duration(tmp_path / "v.mp4") == 123.456


def test_media_duration_handles_failures(tmp_path, monkeypatch):
    def fake_run(cmd, **kwargs):
        raise OSError("no ffprobe")
    monkeypatch.setattr(probe.subprocess, "run", fake_run)
    assert probe.media_duration(tmp_path / "v.mp4") is None
