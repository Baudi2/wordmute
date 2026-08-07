"""Review sidecar: save/load, and apply_review re-rendering."""

import json

import pytest

from wordmute_app.core import review
from wordmute_app.engine import wordmute as engine


def IV(s, e, text, muted=True, pass_n=1, eng="whisper"):
    return {"s": s, "e": e, "text": text, "pass": pass_n, "engine": eng,
            "muted": muted}


def test_review_path_naming(tmp_path):
    out = tmp_path / "v.clean.mp4"
    assert review.review_path_for(out).name == "v.clean.mp4.wordmute.json"


def test_save_load_roundtrip(tmp_path):
    out = tmp_path / "v.clean.mp4"
    intervals = [IV(1.0, 1.5, "бог"), IV(3.0, 3.2, "черт", muted=False)]
    p = review.save_review(tmp_path / "v.mp4", out, 100, intervals)
    data = review.load_review(p)
    assert data["source"] == str(tmp_path / "v.mp4")
    assert data["output"] == str(out)
    assert data["pad_ms"] == 100
    assert data["intervals"] == intervals


def test_load_rejects_non_review_json(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"foo": 1}), encoding="utf-8")
    with pytest.raises(ValueError):
        review.load_review(p)


def test_apply_review_mutes_only_checked(tmp_path, monkeypatch):
    source = tmp_path / "v.mp4"
    source.write_bytes(b"original")
    output = tmp_path / "v.clean.mp4"
    output.write_bytes(b"old-output")
    stale = tmp_path / "v.clean.mp4.words.json"
    stale.write_text("[]", encoding="utf-8")

    muted_calls = []

    def fake_mute(media, intervals, out):
        muted_calls.append((media, list(intervals)))
        out.write_bytes(b"re-rendered")

    monkeypatch.setattr(engine, "mute", fake_mute)
    data = {"source": str(source), "output": str(output), "pad_ms": 100,
            "intervals": [IV(1.0, 1.5, "бог"),
                          IV(3.0, 3.2, "обожаю", muted=False)]}
    review.apply_review(data)

    assert muted_calls == [(source, [(1.0, 1.5, "бог")])]
    assert output.read_bytes() == b"re-rendered"
    assert not stale.exists()  # cached transcript invalidated
    saved = review.load_review(review.review_path_for(output))
    assert saved["intervals"][1]["muted"] is False


def test_apply_review_all_unmuted_copies_source(tmp_path, monkeypatch):
    source = tmp_path / "v.mp4"
    source.write_bytes(b"original")
    output = tmp_path / "v.clean.mp4"
    output.write_bytes(b"old-output")

    monkeypatch.setattr(engine, "mute",
                        lambda *a: pytest.fail("mute must not be called"))
    data = {"source": str(source), "output": str(output), "pad_ms": 100,
            "intervals": [IV(1.0, 1.5, "бог", muted=False)]}
    review.apply_review(data)
    assert output.read_bytes() == b"original"


def test_apply_review_requires_source(tmp_path):
    data = {"source": str(tmp_path / "gone.mp4"),
            "output": str(tmp_path / "v.clean.mp4"),
            "pad_ms": 100, "intervals": [IV(1.0, 1.5, "x")]}
    with pytest.raises(FileNotFoundError):
        review.apply_review(data)
