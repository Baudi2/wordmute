"""Snippet player: ffmpeg extraction command and error handling
(subprocess and winsound stubbed)."""

import subprocess

import pytest

from wordmute_app.ui import player as player_mod


def test_play_extracts_with_context_and_plays(tmp_path, monkeypatch):
    calls = {}

    def fake_run(cmd, **kwargs):
        calls["cmd"] = cmd
        # ffmpeg writes the wav (last arg)
        with open(cmd[-1], "wb") as f:
            f.write(b"RIFF")
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(player_mod.subprocess, "run", fake_run)
    import winsound
    played = []
    monkeypatch.setattr(winsound, "PlaySound",
                        lambda *a, **k: played.append(a))

    p = player_mod.SnippetPlayer()
    try:
        p.play(tmp_path / "v.mp4", 10.0, 10.5)
        cmd = calls["cmd"]
        assert cmd[0] == "ffmpeg"
        assert cmd[cmd.index("-ss") + 1] == "9.300"   # 0.7 s context before
        assert cmd[cmd.index("-t") + 1] == "1.900"    # word + context both sides
        assert played and played[-1][0].endswith(".wav")
    finally:
        p.dispose()


def test_play_at_clip_start_clamps_context(tmp_path, monkeypatch):
    calls = {}

    def fake_run(cmd, **kwargs):
        calls["cmd"] = cmd
        with open(cmd[-1], "wb") as f:
            f.write(b"RIFF")
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(player_mod.subprocess, "run", fake_run)
    import winsound
    monkeypatch.setattr(winsound, "PlaySound", lambda *a, **k: None)

    p = player_mod.SnippetPlayer()
    try:
        p.play(tmp_path / "v.mp4", 0.2, 0.6)
        assert calls["cmd"][calls["cmd"].index("-ss") + 1] == "0.000"
    finally:
        p.dispose()


def test_play_raises_on_ffmpeg_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(
        player_mod.subprocess, "run",
        lambda cmd, **k: subprocess.CompletedProcess(cmd, 1, stdout=b"",
                                                     stderr=b"bad input"))
    p = player_mod.SnippetPlayer()
    try:
        with pytest.raises(RuntimeError, match="bad input"):
            p.play(tmp_path / "v.mp4", 1.0, 2.0)
    finally:
        p.dispose()
