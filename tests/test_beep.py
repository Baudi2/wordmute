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


def run_mute_capture(tmp_path, monkeypatch, beep_hz):
    captured = {}

    def fake_run(cmd, check=False, **kwargs):
        captured["cmd"] = cmd
        script_arg = [a for a in cmd
                      if a.endswith(".txt") and Path(a).exists()]
        captured["script"] = Path(script_arg[0]).read_text(encoding="utf-8") \
            if script_arg else ""
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(wm.subprocess, "run", fake_run)
    wm.mute(tmp_path / "v.mp4", INTERVALS, tmp_path / "out.mp4",
            beep_hz=beep_hz)
    return captured


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
