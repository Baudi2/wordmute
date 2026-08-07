"""Transcript loading, grouping, SRT export."""

import json

import pytest

from wordmute_app.core import transcript

WORDS = [
    {"w": "привет", "s": 0.0, "e": 0.4},
    {"w": "мир", "s": 0.5, "e": 0.9},
    {"w": "после", "s": 3.0, "e": 3.4},   # 2.1 s gap -> new block
    {"w": "паузы", "s": 3.5, "e": 3.9},
]


def test_load_prefers_whisper_cache(tmp_path):
    media = tmp_path / "v.mp4"
    (tmp_path / "v.mp4.words.json").write_text(
        json.dumps(WORDS), encoding="utf-8")
    (tmp_path / "v.mp4.gigaam.words.json").write_text(
        json.dumps([]), encoding="utf-8")
    words, engine_name = transcript.load_transcript(media)
    assert engine_name == "whisper"
    assert len(words) == 4


def test_load_falls_back_to_gigaam(tmp_path):
    media = tmp_path / "v.mp4"
    (tmp_path / "v.mp4.gigaam.words.json").write_text(
        json.dumps(WORDS), encoding="utf-8")
    _, engine_name = transcript.load_transcript(media)
    assert engine_name == "gigaam"


def test_load_missing_cache_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="cached transcript"):
        transcript.load_transcript(tmp_path / "v.mp4")


def test_group_words_breaks_on_gap():
    blocks = transcript.group_words(WORDS)
    assert len(blocks) == 2
    assert [w["w"] for w in blocks[0]] == ["привет", "мир"]


def test_group_words_caps_word_count():
    words = [{"w": f"w{i}", "s": i * 0.2, "e": i * 0.2 + 0.1}
             for i in range(25)]
    blocks = transcript.group_words(words, max_words=10)
    assert all(len(b) <= 10 for b in blocks)


def test_srt_output_format():
    srt = transcript.words_to_srt(WORDS)
    assert srt.startswith("1\n00:00:00,000 --> 00:00:00,900\nпривет мир\n")
    assert "2\n00:00:03,000 --> 00:00:03,900\nпосле паузы" in srt


def test_srt_ts():
    assert transcript.srt_ts(3661.5) == "01:01:01,500"


def test_export_srt(tmp_path):
    media = tmp_path / "v.mp4"
    (tmp_path / "v.mp4.words.json").write_text(
        json.dumps(WORDS), encoding="utf-8")
    dest = transcript.export_srt(media)
    assert dest == tmp_path / "v.srt"
    assert "привет мир" in dest.read_text(encoding="utf-8")
