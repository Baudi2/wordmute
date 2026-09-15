"""Vendored engine must behave identically to the original CLI at
C:\\wordmute\\wordmute.py (matching + list parsing). Skipped on machines
without the original."""

import importlib.util
from pathlib import Path

import pytest

from wordmute_app.engine import wordmute as vendored

ORIGINAL = Path(r"C:\wordmute\wordmute.py")

pytestmark = pytest.mark.skipif(not ORIGINAL.exists(),
                                reason="original CLI not present")


@pytest.fixture(scope="module")
def original():
    spec = importlib.util.spec_from_file_location("wordmute_original", ORIGINAL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SAMPLES = ["Ёжик", "боже,", "кто-то", "ПРИВЕТ!", "«слово»", "...", "don't"]


def test_norm_parity(original):
    for s in SAMPLES:
        assert vendored.norm(s) == original.norm(s)


def test_load_wordlist_parity(original, tmp_path):
    p = tmp_path / "list.txt"
    p.write_text("слово\nкорень*\n*внутри*\nдва слова\n# c\nЁлка\n",
                 encoding="utf-8")
    assert vendored.load_wordlist(p) == original.load_wordlist(p)


def test_find_hits_parity_on_real_lists(original, tmp_path):
    res = Path(__file__).resolve().parents[1] / "wordmute_app" / "resources"
    words = [{"w": w, "s": i * 0.7, "e": i * 0.7 + 0.5}
             for i, w in enumerate(
                 "привет боже мой это демонстрация чуда колдовать "
                 "unicorn magic normal words here".split())]
    for name in ("words_russian.txt", "words_english.txt"):
        wl_v = vendored.load_wordlist(res / name)
        wl_o = original.load_wordlist(res / name)
        assert wl_v == wl_o
        assert (vendored.find_hits(words, *wl_v, pad_ms=100)
                == original.find_hits(words, *wl_o, pad_ms=100))


def test_clock_plumbing_parity(original, tmp_path, monkeypatch):
    """The file-clock ASR extraction, the cache names and the silence
    mute command stay identical in both copies — the CLI had the same
    early mutes and the same FFmpeg 9 break."""
    for name in ("FILE_CLOCK_FILTER", "INPUT_FLAGS", "CLOCK_SIDE_OUTPUT",
                 "ASR_RATE", "CACHE_SUFFIX", "LEGACY_CACHE_SUFFIXES"):
        assert getattr(vendored, name) == getattr(original, name), name
    media, wav = Path("v.mp4"), "a.wav"
    assert (vendored._asr_extract_cmd(media, wav)
            == original._asr_extract_cmd(media, wav))

    seen = {}

    class FakePopen:
        def __init__(self, cmd, **kwargs):
            seen["vendored"] = list(cmd)
            self.stdout = iter([])
            self.returncode = 0

        def wait(self):
            return 0

    monkeypatch.setattr(vendored.subprocess, "Popen", FakePopen)
    vendored.set_reporter(lambda e, d: None)
    try:
        vendored.mute(tmp_path / "v.mp4", [(1.0, 1.5, "x")],
                      tmp_path / "o.mp4")
    finally:
        vendored.set_reporter(None)
    monkeypatch.setattr(original.subprocess, "run",
                        lambda cmd, **k: seen.__setitem__("original",
                                                          list(cmd)))
    original.mute(tmp_path / "v.mp4", [(1.0, 1.5, "x")], tmp_path / "o.mp4")

    def from_input_flags(cmd):     # the script's temp name differs
        start = cmd.index("-err_detect")
        return ["SCRIPT" if a.endswith(".txt") else a for a in cmd[start:]]

    assert (from_input_flags(seen["vendored"])
            == from_input_flags(seen["original"]))
