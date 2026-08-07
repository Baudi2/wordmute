"""History, model manager backend, watch-folder scanning, tester."""

from wordmute_app.core import history, models
from wordmute_app.core.jobs import scan_watch_dir
from wordmute_app.core.wordlists import explain_matches


# ---------------------------------------------------------------- history
def test_history_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert history.load_history() == []
    history.append_history({"name": "a.mp4", "status": "ok", "muted": 3})
    history.append_history({"name": "b.mp4", "status": "error",
                            "error": "boom"})
    records = history.load_history()
    assert len(records) == 2
    assert records[0]["name"] == "b.mp4"  # newest first
    assert "time" in records[0]
    history.clear_history()
    assert history.load_history() == []


def test_history_skips_corrupt_lines(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    history.append_history({"name": "ok.mp4"})
    with history.history_path().open("a", encoding="utf-8") as f:
        f.write("{broken\n")
    assert len(history.load_history()) == 1


# ---------------------------------------------------------------- models
def test_whisper_model_status_and_delete(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    d = tmp_path / "models--Systran--faster-whisper-small" / "blobs"
    d.mkdir(parents=True)
    (d / "weights.bin").write_bytes(b"x" * 1000)

    status = {s["model"]: s for s in models.whisper_model_status()}
    assert status["small"]["downloaded"] is True
    assert status["small"]["size_bytes"] == 1000
    assert status["large-v3"]["downloaded"] is False

    models.delete_whisper_model("small")
    status = {s["model"]: s for s in models.whisper_model_status()}
    assert status["small"]["downloaded"] is False


def test_fmt_size():
    assert models.fmt_size(500 * 1024 ** 2) == "500 MB"
    assert models.fmt_size(3 * 1024 ** 3) == "3.0 GB"


# ---------------------------------------------------------------- watch dir
def test_scan_watch_dir_waits_for_stable_size(tmp_path):
    seen = {}
    f = tmp_path / "v.mp4"
    f.write_bytes(b"x" * 10)
    # first scan: file just appeared -> not ready yet
    assert scan_watch_dir(tmp_path, seen) == []
    # file still growing -> still not ready
    f.write_bytes(b"x" * 20)
    assert scan_watch_dir(tmp_path, seen) == []
    # size stable -> ready exactly once
    assert scan_watch_dir(tmp_path, seen) == [f]
    assert scan_watch_dir(tmp_path, seen) == []


def test_scan_watch_dir_ignores_clean_and_nonmedia(tmp_path):
    seen = {}
    (tmp_path / "a.clean.mp4").write_bytes(b"x")
    (tmp_path / "notes.txt").write_bytes(b"x")
    scan_watch_dir(tmp_path, seen)
    assert scan_watch_dir(tmp_path, seen) == []


def test_scan_watch_dir_missing_folder(tmp_path):
    assert scan_watch_dir(tmp_path / "nope", {}) == []


# ---------------------------------------------------------------- tester
WORDLIST = ({"бог"}, ["колд"], [("боже", "мой")], ["монстр"])


def test_explain_exact_stem_substring():
    per_word, phrases = explain_matches("Бог колдовать демонстрация чай",
                                        WORDLIST)
    assert per_word[0] == ("бог", ["бог"])
    assert per_word[1] == ("колдовать", ["колд*"])
    assert per_word[2] == ("демонстрация", ["*монстр*"])
    assert per_word[3] == ("чай", [])  # no match
    assert phrases == []


def test_explain_phrase():
    _, phrases = explain_matches("ну боже мой скажи", WORDLIST)
    assert phrases == ["боже мой"]


def test_explain_normalizes_input():
    per_word, _ = explain_matches("БОГ,", WORDLIST)
    assert per_word[0][1] == ["бог"]
