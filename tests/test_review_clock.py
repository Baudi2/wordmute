"""Version-1 review sidecars counted time from the first audio sample;
the Review window moves them onto the file clock once."""

import json
from pathlib import Path

import pytest

from wordmute_app.core import probe, review


def _no_probe(path):
    raise AssertionError("the probe must not run here")


def v1(source, output="o.mp4"):
    return {"version": 1, "source": str(source), "output": str(output),
            "pad_ms": 100, "beep_hz": None,
            "intervals": [{"s": 1.0, "e": 1.5, "text": "бог", "pass": 1,
                           "engine": "gigaam", "muted": True}]}


def test_version_1_is_shifted_once(tmp_path, monkeypatch):
    src = tmp_path / "v.mp4"
    src.write_bytes(b"x")
    monkeypatch.setattr(probe, "audio_start_offset", lambda p: 0.556009)
    data = v1(src)
    assert review.migrate_clock(data) == 0.556009
    row = data["intervals"][0]
    assert (row["s"], row["e"]) == (1.556, 2.056)
    assert data["version"] == 2
    assert review.migrate_clock(data) is None          # never twice
    assert data["intervals"][0]["s"] == 1.556


def test_version_2_and_missing_sources_are_left_alone(tmp_path,
                                                      monkeypatch):
    monkeypatch.setattr(probe, "audio_start_offset", _no_probe)
    src = tmp_path / "v.mp4"
    src.write_bytes(b"x")
    current = v1(src)
    current["version"] = 2
    assert review.migrate_clock(current) is None
    assert current["intervals"][0]["s"] == 1.0
    gone = v1(tmp_path / "gone.mp4")
    assert review.migrate_clock(gone) is None
    assert gone["version"] == 1 and gone["intervals"][0]["s"] == 1.0


def test_failed_probe_keeps_version_1(tmp_path, monkeypatch):
    src = tmp_path / "v.mp4"
    src.write_bytes(b"x")
    monkeypatch.setattr(probe, "audio_start_offset", lambda p: None)
    data = v1(src)
    assert review.migrate_clock(data) is None
    assert data["version"] == 1 and data["intervals"][0]["s"] == 1.0


def test_new_sidecars_are_version_2_and_loading_never_probes(tmp_path,
                                                             monkeypatch):
    """cleanup.resolve_source reads sidecars from the delete flows: no
    ffmpeg may run there."""
    monkeypatch.setattr(probe, "audio_start_offset", _no_probe)
    path = review.save_review(tmp_path / "v.mp4", tmp_path / "v.clean.mp4",
                              100, v1(tmp_path)["intervals"])
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 2
    review.load_review(path)


def test_apply_review_keeps_the_version(tmp_path, monkeypatch):
    from wordmute_app.engine import wordmute as engine

    src = tmp_path / "v.mp4"
    src.write_bytes(b"x")
    out = tmp_path / "v.clean.mp4"
    out.write_bytes(b"y")
    monkeypatch.setattr(engine, "mute",
                        lambda media, iv, tmp, beep_hz=None:
                        Path(tmp).write_bytes(b"m"))
    data = v1(src, out)
    review.apply_review(data)          # not migrated: must stay version 1
    sidecar = review.review_path_for(out)
    assert json.loads(sidecar.read_text(encoding="utf-8"))["version"] == 1
    data["version"] = 2
    review.apply_review(data)
    assert json.loads(sidecar.read_text(encoding="utf-8"))["version"] == 2


class DummyPlayer:
    def play(self, *a):
        pass

    def stop(self):
        pass

    def dispose(self):
        pass


def _sidecar(tmp_path, version):
    src = tmp_path / "v.mp4"
    src.write_bytes(b"x")
    out = tmp_path / "v.clean.mp4"
    out.write_bytes(b"y")
    data = {"version": version, "source": str(src), "output": str(out),
            "pad_ms": 100, "beep_hz": None,
            "intervals": [{"s": 9.0, "e": 9.4, "text": "черт", "pass": 1,
                           "engine": "gigaam", "muted": True}]}
    path = review.review_path_for(out)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_review_window_corrects_a_version_1_sidecar(qapp, tmp_path,
                                                    monkeypatch):
    from wordmute_app.ui import review_dialog

    monkeypatch.setattr(review_dialog, "SnippetPlayer", DummyPlayer)
    monkeypatch.setattr(probe, "audio_start_offset", lambda p: 0.556)
    dialog = review_dialog.ReviewDialog(_sidecar(tmp_path, 1))
    assert (dialog.table.item(0, review_dialog.COL_START).text()
            == "00:00:09.556")
    assert dialog.clock_note is not None
    assert "556" in dialog.clock_note.text()
    assert dialog._dirty is False
    dialog.close()


def test_review_window_leaves_version_2_alone(qapp, tmp_path, monkeypatch):
    from wordmute_app.ui import review_dialog

    monkeypatch.setattr(review_dialog, "SnippetPlayer", DummyPlayer)
    monkeypatch.setattr(probe, "audio_start_offset", _no_probe)
    dialog = review_dialog.ReviewDialog(_sidecar(tmp_path, 2))
    assert (dialog.table.item(0, review_dialog.COL_START).text()
            == "00:00:09.000")
    assert dialog.clock_note is None
    dialog.close()
