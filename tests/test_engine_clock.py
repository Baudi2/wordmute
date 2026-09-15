"""File-clock plumbing, stubbed: the extraction command, every ASR route
hearing the extracted WAV, cache names, legacy caches never read."""

import contextlib
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

from wordmute_app.engine import wordmute as wm


def test_extraction_command_is_on_the_file_clock():
    assert wm._asr_extract_cmd(Path("v.mp4"), "a.wav") == [
        "ffmpeg", "-y", "-v", "error", *wm.INPUT_FLAGS, "-i", "v.mp4",
        "-map", "0:a:0", "-af", "aresample=async=1:first_pts=0",
        "-ac", "1", "-ar", "16000", "a.wav",
        "-map", "0", "-c", "copy", "-f", "null", "-"]


@pytest.fixture
def stub_audio(monkeypatch):
    extracted = []

    @contextlib.contextmanager
    def fake(media):
        extracted.append(Path(media).name)
        yield "x.wav"

    monkeypatch.setattr(wm, "_asr_audio", fake)
    return extracted


class FakeSeg:
    def __init__(self):
        self.words = [types.SimpleNamespace(word=" бог", start=1.0, end=1.5)]
        self.end = 2.0


def _media(tmp_path, name):
    path = tmp_path / name
    path.write_bytes(b"x")
    return path


def test_every_route_hears_the_wav(tmp_path, monkeypatch, stub_audio):
    heard = []

    class Model:
        def transcribe(self, path, **kw):
            heard.append(("whisper", path))
            return iter([FakeSeg()]), None

    class Pipe:
        def __init__(self, model):
            pass

        def transcribe(self, path, **kw):
            heard.append(("batched", path))
            return iter([FakeSeg()]), None

    class Seg:
        tokens, timestamps, start, end = list("бог"), [1.0, 1.1, 1.2], 0.0, 2.0

    class OnnxPipe:
        def recognize(self, path):
            heard.append(("onnx", path))
            return [Seg()]

    class Word:
        text, start, end = " бог ", 1.0, 1.5

    class TorchModel:
        def transcribe_longform(self, path, word_timestamps):
            heard.append(("torch", path))
            return types.SimpleNamespace(words=[Word()])

    fake_fw = types.ModuleType("faster_whisper")
    fake_fw.BatchedInferencePipeline = Pipe
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_fw)
    monkeypatch.setattr(wm, "get_whisper_model", lambda n, d: Model())
    monkeypatch.setattr(wm, "_gigaam_onnx_pipeline", lambda n: OnnxPipe())
    monkeypatch.setattr(wm, "get_gigaam_model", lambda n, d: TorchModel())
    monkeypatch.setattr(wm, "FAST_MODE", False)
    monkeypatch.setattr(wm, "GIGAAM_BACKEND", "torch")
    wm.set_reporter(lambda e, d: None)
    try:
        wm.transcribe(_media(tmp_path, "a.mp4"), "whisper", "s", "cpu", "ru")
        wm.configure_fast_mode(True)
        wm.transcribe(_media(tmp_path, "b.mp4"), "whisper", "s", "cpu", "ru")
        wm.configure_gigaam_backend("onnx")
        wm.transcribe(_media(tmp_path, "c.mp4"), "gigaam", "v3", "cpu", "ru")
        wm.configure_gigaam_backend("torch")
        wm.transcribe(_media(tmp_path, "d.mp4"), "gigaam", "v3", "cpu", "ru")
    finally:
        wm.set_reporter(None)
    assert heard == [("whisper", "x.wav"), ("batched", "x.wav"),
                     ("onnx", "x.wav"), ("torch", "x.wav")]
    assert stub_audio == ["a.mp4", "b.mp4", "c.mp4", "d.mp4"]


def test_legacy_caches_are_never_read(tmp_path, monkeypatch, stub_audio):
    media = _media(tmp_path, "v.mp4")
    stale = [{"w": "старое", "s": 0.1, "e": 0.2}]
    for suffix in wm.LEGACY_CACHE_SUFFIXES:     # written after the media
        (tmp_path / ("v.mp4" + suffix)).write_text(
            json.dumps(stale), encoding="utf-8")

    class Model:
        def transcribe(self, path, **kw):
            return iter([FakeSeg()]), None

    monkeypatch.setattr(wm, "get_whisper_model", lambda n, d: Model())
    monkeypatch.setattr(wm, "FAST_MODE", False)
    events = []
    wm.set_reporter(lambda e, d: events.append(e))
    try:
        words = wm.transcribe(media, "whisper", "s", "cpu", "ru")
    finally:
        wm.set_reporter(None)
    assert words == [{"w": "бог", "s": 1.0, "e": 1.5}]
    assert "cache_hit" not in events
    assert stub_audio == ["v.mp4"]
    assert wm._cache_path(media, "whisper").exists()


def test_drop_output_caches_removes_current_and_legacy_names(tmp_path):
    out = tmp_path / "v.clean.mp4"
    names = [out.name + s for s in (*wm.CACHE_SUFFIX.values(),
                                    *wm.LEGACY_CACHE_SUFFIXES)]
    for name in names:
        (tmp_path / name).write_text("[]", encoding="utf-8")
    wm.drop_output_caches(out)
    assert [n for n in names if (tmp_path / n).exists()] == []


def test_unknown_engine_raises_before_extracting(tmp_path, monkeypatch):
    extracted = []
    monkeypatch.setattr(wm, "_asr_audio", lambda media: extracted.append(1))
    with pytest.raises(ValueError, match="unknown engine"):
        wm.transcribe(tmp_path / "v.mp4", "bogus", "m", "cpu", "ru")
    assert extracted == []


def test_extraction_failure_raises_with_stderr(tmp_path, monkeypatch):
    monkeypatch.setattr(
        wm.subprocess, "run",
        lambda cmd, **k: subprocess.CompletedProcess(
            cmd, 1, stdout="", stderr="Invalid data found when processing"))
    with pytest.raises(RuntimeError, match="Invalid data found"):
        wm.extract_asr_wav(tmp_path / "v.mp4", tmp_path / "a.wav")


def test_asr_audio_deletes_the_wav(tmp_path, monkeypatch):
    made = []

    def fake_extract(media, wav):
        made.append(wav)
        Path(wav).write_bytes(b"RIFF")

    monkeypatch.setattr(wm, "extract_asr_wav", fake_extract)
    with wm._asr_audio(tmp_path / "v.mp4") as wav:
        assert Path(wav).exists()
    assert not Path(made[0]).exists()

    def failing_extract(media, wav):
        made.append(wav)
        raise RuntimeError("ffmpeg audio extraction failed")

    monkeypatch.setattr(wm, "extract_asr_wav", failing_extract)
    with pytest.raises(RuntimeError):
        with wm._asr_audio(tmp_path / "v.mp4"):
            pass
    assert not Path(made[1]).exists()
