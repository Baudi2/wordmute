"""Beep-mode filter graphs and command construction."""

import subprocess
from pathlib import Path

from wordmute_app.engine import wordmute as wm

INTERVALS = [(1.0, 1.5, "бог"), (9.0, 9.4, "черт")]


def test_silence_filters_unchanged_format():
    f = wm._silence_filters(INTERVALS)
    assert f == ("volume=enable='between(t,1.000,1.500)':volume=0,"
                 "volume=enable='between(t,9.000,9.400)':volume=0")


def test_beep_filtergraph_structure():
    g = wm._beep_filtergraph(INTERVALS, 1000)
    assert g.startswith("[0:a]volume=enable=")
    assert "sine=frequency=1000[tone]" in g
    assert "not(between(t,1.000,1.500)+between(t,9.000,9.400))" in g
    assert g.endswith("[aout]")


class FakePopen:
    captured = None

    def __init__(self, cmd, **kwargs):
        FakePopen.captured["cmd"] = cmd
        script_arg = [a for a in cmd
                      if a.endswith(".txt") and Path(a).exists()]
        FakePopen.captured["script"] = (
            Path(script_arg[0]).read_text(encoding="utf-8")
            if script_arg else "")
        self.stdout = iter(["progress=end\n"])
        self.returncode = 0

    def wait(self):
        return self.returncode


def run_mute_capture(tmp_path, monkeypatch, beep_hz):
    FakePopen.captured = {}
    monkeypatch.setattr(wm.subprocess, "Popen", FakePopen)
    wm.mute(tmp_path / "v.mp4", INTERVALS, tmp_path / "out.mp4",
            beep_hz=beep_hz)
    return FakePopen.captured


def test_mute_silence_command(tmp_path, monkeypatch):
    captured = run_mute_capture(tmp_path, monkeypatch, beep_hz=None)
    cmd = captured["cmd"]
    assert "-filter_script:a" in cmd
    assert "-filter_complex_script" not in cmd
    assert captured["script"].startswith("volume=enable=")


def test_mute_beep_command(tmp_path, monkeypatch):
    captured = run_mute_capture(tmp_path, monkeypatch, beep_hz=800)
    cmd = captured["cmd"]
    assert "-filter_complex_script" in cmd
    assert "-filter_script:a" not in cmd
    assert "[aout]" in cmd  # mapped
    assert "sine=frequency=800" in captured["script"]


def test_ffmpeg_progress_events_emitted(monkeypatch):
    events = []

    class ProgressPopen:
        def __init__(self, cmd, **kwargs):
            self.stdout = iter(["out_time=00:01:29.500000\n",
                                "out_time=N/A\n",
                                "out_time=01:00:00.000000\n",
                                "progress=end\n"])
            self.returncode = 0

        def wait(self):
            return 0

    monkeypatch.setattr(wm.subprocess, "Popen", ProgressPopen)
    wm.set_reporter(lambda e, d: events.append((e, d)))
    try:
        wm._run_ffmpeg_with_progress(["ffmpeg"])
    finally:
        wm.set_reporter(None)
    seconds = [d["seconds"] for e, d in events if e == "mute_progress"]
    assert seconds == [89.5, 3600.0]  # N/A line skipped


def test_ffmpeg_failure_raises_with_code(monkeypatch):
    import pytest

    class FailPopen:
        def __init__(self, cmd, **kwargs):
            self.stdout = iter([])
            self.returncode = 1

        def wait(self):
            return 1

    monkeypatch.setattr(wm.subprocess, "Popen", FailPopen)
    with pytest.raises(RuntimeError, match="code 1"):
        wm._run_ffmpeg_with_progress(["ffmpeg"])


def test_audio_codec_follows_container():
    assert wm._audio_codec_args(Path("v.webm"))[:2] == ["-c:a", "libopus"]
    assert wm._audio_codec_args(Path("v.opus"))[:2] == ["-c:a", "libopus"]
    assert wm._audio_codec_args(Path("v.ogg"))[:2] == ["-c:a", "libvorbis"]
    assert wm._audio_codec_args(Path("v.flac")) == ["-c:a", "flac"]
    assert wm._audio_codec_args(Path("v.wav")) == ["-c:a", "pcm_s16le"]
    assert wm._audio_codec_args(Path("v.mp4"))[:2] == ["-c:a", "aac"]
    assert wm._audio_codec_args(Path("v.MKV"))[:2] == ["-c:a", "aac"]


def test_mute_webm_uses_opus(tmp_path, monkeypatch):
    FakePopen.captured = {}
    monkeypatch.setattr(wm.subprocess, "Popen", FakePopen)
    wm.mute(tmp_path / "v.webm", INTERVALS, tmp_path / "out.webm")
    cmd = FakePopen.captured["cmd"]
    assert "libopus" in cmd
    assert "aac" not in cmd


def test_process_file_passes_beep_option(tmp_path, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(wm, "transcribe",
                        lambda *a, **k: [{"w": "бог", "s": 1.0, "e": 1.5}])
    seen = {}

    def fake_mute(media, intervals, out, beep_hz=None):
        seen["beep_hz"] = beep_hz
        Path(out).write_bytes(b"x")

    monkeypatch.setattr(wm, "mute", fake_mute)
    args = SimpleNamespace(device="cpu", language="ru", pad=100,
                           list_only=False, retranscribe=False,
                           force_passes=False, no_vad=False, beep_hz=700)
    inp = tmp_path / "v.mp4"
    inp.write_bytes(b"x")
    wm.process_file(inp, tmp_path / "v.clean.mp4", ({"бог"}, [], [], []),
                    args, [("whisper", "small")])
    assert seen["beep_hz"] == 700
