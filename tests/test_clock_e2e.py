"""End to end on real FFmpeg: mutes and beeps land ON the word in files
whose audio starts after the video (rutube downloads: 0.556 s), that
have a timestamp gap, or that are MPEG-TS — for every FFmpeg build the
app can end up running (PATH's and the managed runtime's).

Before the file-clock fix every mute here landed 0.556 s early (and
0.8 s more after the gap); on FFmpeg 9 the old command did not run."""

import os
import shutil
import subprocess
from array import array
from pathlib import Path
from types import SimpleNamespace

import pytest

from wordmute_app.engine import wordmute as wm

OFFSET = 0.556                 # audio start after the video
GAP_AT, GAP = 4.5, 0.8         # gap.mkv: +0.8 s pts jump at ~4.5 s
BURST = 0.4
WORDS = {"бог": (3.0, 500), "черт": (6.0, 700), "привет": (9.0, 900)}
RATE = 16000

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None,
                                reason="ffmpeg is not on PATH")


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode:
        raise RuntimeError(f"{' '.join(cmd[:4])} …: {r.stderr[-400:]}")
    return r


def decode(path, start=None, dur=None) -> list:
    cmd = ["ffmpeg", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}", "-t", f"{dur:.3f}"]
    cmd += ["-i", str(path), "-vn", "-ac", "1", "-ar", str(RATE),
            "-f", "s16le", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    samples = array("h")
    samples.frombytes(raw[: len(raw) // 2 * 2])
    return [x / 32768 for x in samples]


def peak(samples) -> float:
    return max((abs(x) for x in samples), default=0.0)


def bursts(samples) -> list:
    """[(start_s, end_s, word)] for stretches louder than 0.3."""
    hop = RATE // 100
    loud = [peak(samples[i:i + hop]) > 0.3
            for i in range(0, len(samples) - hop + 1, hop)]
    found, start = [], None
    for k, on in enumerate(loud + [False]):
        if on and start is None:
            start = k
        elif not on and start is not None:
            seg = samples[start * hop:k * hop]
            crossings = sum(1 for a, b in zip(seg, seg[1:])
                            if (a < 0) != (b < 0))
            hz = crossings / 2 / (len(seg) / RATE)
            word = min(WORDS, key=lambda w: abs(WORDS[w][1] - hz))
            found.append((start / 100, k / 100, word))
            start = None
    return found


@pytest.fixture(scope="module")
def sources(tmp_path_factory):
    """{name: (path, content time -> file clock)}"""
    d = tmp_path_factory.mktemp("clock")
    expr = "0.003*sin(2*PI*217*t)" + "".join(
        f"+if(between(t,{s},{s + BURST}),0.5*sin(2*PI*{hz}*t),0)"
        for s, hz in WORDS.values())
    tone = d / "tone.wav"
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         f"aevalsrc='{expr}|{expr}':s=44100:d=13",
         "-c:a", "pcm_s16le", str(tone)])
    video = d / "video.mp4"
    try:
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
             "color=c=black:s=160x120:r=25:d=14", "-c:v", "libx264",
             "-pix_fmt", "yuv420p", str(video)])
    except RuntimeError as exc:
        pytest.skip(f"this FFmpeg cannot encode test video: {exc}")
    offset = d / "offset.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(video),
         "-itsoffset", str(OFFSET), "-i", str(tone),
         "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "128k", str(offset)])
    ts = d / "remux.ts"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(offset), "-c", "copy",
         "-f", "mpegts", str(ts)])
    gap_audio = d / "gap_audio.mka"
    first = int(GAP_AT * 44100)
    run(["ffmpeg", "-y", "-v", "error", "-i", str(tone), "-af",
         f"asetnsamples=n=1024,"
         f"asetpts='if(gte(N,{first}),PTS+{GAP}/TB,PTS)'",
         "-c:a", "aac", "-b:a", "128k", str(gap_audio)])
    gap = d / "gap.mkv"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(video),
         "-itsoffset", str(OFFSET), "-i", str(gap_audio),
         "-map", "0:v", "-map", "1:a", "-c", "copy", str(gap)])
    # csv lines can carry a trailing comma ("0.533000,")
    fields = (line.split(",")[0].strip() for line in run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "packet=pts_time", "-of", "csv=p=0",
         str(gap)]).stdout.splitlines())
    pts = [float(x) for x in fields if x not in ("", "N/A")]
    assert max(b - a for a, b in zip(pts, pts[1:])) > GAP, \
        "the synthetic timestamp gap did not survive muxing"
    return {
        "offset.mp4": (offset, lambda t: t + OFFSET),
        "remux.ts": (ts, lambda t: t + OFFSET),
        "gap.mkv": (gap, lambda t: t + OFFSET + (GAP if t > GAP_AT else 0)),
    }


def _args(beep_hz=None):
    return SimpleNamespace(device="cpu", language="ru", pad=100,
                           list_only=False, retranscribe=False,
                           force_passes=False, no_vad=False,
                           beep_hz=beep_hz)


def _check_output(out, to_file_clock, beep_hz, label, muted=("бог", "черт")):
    for word, (start, _hz) in WORDS.items():
        t0 = to_file_clock(start)
        inside = peak(decode(out, t0 + 0.03, BURST - 0.06))
        if word not in muted:
            assert inside >= 0.3, f"{label}: «{word}» was muted"
        elif beep_hz:
            assert 0.015 <= inside <= 0.08, \
                f"{label}: «{word}» peak {inside:.3f}, want only the beep"
            late = peak(decode(out, t0 + BURST + 0.25, 0.2))
            assert late < 0.012, f"{label}: beep after «{word}» ({late:.3f})"
        else:
            assert inside < 0.01, f"{label}: «{word}» audible ({inside:.3f})"


@pytest.mark.parametrize("beep_hz", [None, 3000])
@pytest.mark.parametrize("name", ["offset.mp4", "gap.mkv", "remux.ts"])
def test_two_passes_mute_on_the_file_clock(sources, ffmpeg_builds, tmp_path,
                                           monkeypatch, name, beep_hz):
    """Pass 1 hears only «бог»; pass 2 must catch «черт» on pass 1's
    AAC re-encode. Both land on the word; «привет» stays."""
    assert ffmpeg_builds
    src, to_file_clock = sources[name]
    path_before = os.environ["PATH"]
    for folder, version in ffmpeg_builds:
        monkeypatch.setenv("PATH", folder + os.pathsep + path_before)
        work = tmp_path / version.split()[2]
        work.mkdir()
        media = work / src.name
        shutil.copy2(src, media)
        out = work / f"{src.stem}.clean{src.suffix}"
        calls = []

        class Whisper:
            def transcribe(self, path, **kw):
                calls.append(path)
                heard = bursts(decode(path))
                if len(calls) == 1:
                    heard = [h for h in heard if h[2] == "бог"]
                seg = SimpleNamespace(
                    words=[SimpleNamespace(word=w, start=s, end=e)
                           for s, e, w in heard], end=13.0)
                return iter([seg]), None

        monkeypatch.setattr(wm, "get_whisper_model",
                            lambda n, d: Whisper())
        monkeypatch.setattr(wm, "FAST_MODE", False)
        wm.set_reporter(lambda e, d: None)
        try:
            wm.process_file(media, out, ({"бог", "черт"}, [], [], []),
                            _args(beep_hz),
                            [("whisper", "small"), ("whisper", "small")])
        finally:
            wm.set_reporter(None)
        label = f"{name} beep={beep_hz} on {version.split()[2]}"
        assert len(calls) == 2, label
        assert all(str(c).endswith(".wav") for c in calls), label
        assert wm._cache_path(media, "whisper").exists(), label
        _check_output(out, to_file_clock, beep_hz, label)


@pytest.mark.parametrize("backend", ["onnx", "torch"])
def test_gigaam_routes_hear_the_file_clock(sources, tmp_path, monkeypatch,
                                           backend):
    src, to_file_clock = sources["offset.mp4"]
    media = tmp_path / src.name
    shutil.copy2(src, media)
    out = tmp_path / "offset.clean.mp4"

    class OnnxPipe:
        def recognize(self, wav):
            for s, e, word in bursts(decode(wav)):
                n = len(word)
                step = (e - 0.08 - s) / max(n - 1, 1)
                yield SimpleNamespace(tokens=list(word),
                                      timestamps=[s + i * step
                                                  for i in range(n)],
                                      start=0.0, end=e)

    class TorchModel:
        def transcribe_longform(self, path, word_timestamps):
            return SimpleNamespace(words=[
                SimpleNamespace(text=w, start=s, end=e)
                for s, e, w in bursts(decode(path))])

    monkeypatch.setattr(wm, "_gigaam_onnx_pipeline", lambda n: OnnxPipe())
    monkeypatch.setattr(wm, "get_gigaam_model", lambda n, d: TorchModel())
    monkeypatch.setattr(wm, "GIGAAM_BACKEND", backend)
    wm.set_reporter(lambda e, d: None)
    try:
        wm.process_file(media, out, ({"бог", "черт"}, [], [], []), _args(),
                        [("gigaam", "v3_rnnt")])
    finally:
        wm.set_reporter(None)
    _check_output(out, to_file_clock, None, f"gigaam-{backend}")


def test_beep_gate_accepts_300_intervals(sources, tmp_path):
    """A flat between() sum fails past 99 terms: beep mode could never
    render a real episode with 281 muted spots."""
    src, _ = sources["offset.mp4"]
    intervals = [(round(0.6 + i * 0.04, 3), round(0.62 + i * 0.04, 3), "x")
                 for i in range(300)]
    out = tmp_path / "many.clean.mp4"
    wm.set_reporter(lambda e, d: None)
    try:
        wm.mute(src, intervals, out, beep_hz=1000)
    finally:
        wm.set_reporter(None)
    assert out.exists() and out.stat().st_size > 0


def test_audio_start_offset_probe(sources, tmp_path):
    """What migrate_clock shifts version-1 sidecars by: where mute() sees
    the first audio sample."""
    from wordmute_app.core import probe

    for name in ("offset.mp4", "remux.ts"):
        value = probe.audio_start_offset(sources[name][0])
        assert value is not None and 0.50 <= value <= 0.58, (name, value)
    plain = tmp_path / "plain.wav"
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         "sine=frequency=440:duration=2", str(plain)])
    assert probe.audio_start_offset(plain) == pytest.approx(0.0, abs=0.001)
    assert probe.audio_start_offset(tmp_path / "missing.mp4") is None
