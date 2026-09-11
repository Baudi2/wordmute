"""One review row per muted spot. Passes 2+ transcribe the already-
muted output and re-catch the same word a few ms off; the Review window
listed every catch (49 rows for ~20 spots on a Better Call Saul
episode), and unchecking one copy un-muted nothing while the others
stayed checked. Fixture = the real timestamps from that run."""

import json

from wordmute_app.core import review


def iv(s, e, text, p, engine, muted=True):
    return {"s": s, "e": e, "text": text, "pass": p, "engine": engine,
            "muted": muted}


def ts(m, s):
    return m * 60 + s


# Лучше звоните Солу 2x03 — plan gigaam → gigaam → whisper
SAUL = [
    iv(ts(1, 30.101), ts(1, 30.741), "повезло", 1, "gigaam"),
    iv(ts(5, 32.335), ts(5, 32.755), "карты", 1, "gigaam"),
    iv(ts(8, 21.393), ts(8, 21.793), "домов", 1, "gigaam"),
    iv(ts(10, 47.741), ts(10, 48.181), "боже", 1, "gigaam"),
    iv(ts(12, 4.731), ts(12, 5.151), "верю", 1, "gigaam"),
    iv(ts(12, 8.195), ts(12, 8.595), "веру", 1, "gigaam"),
    iv(ts(1, 30.158), ts(1, 30.798), "повезло", 2, "gigaam"),
    iv(ts(8, 21.433), ts(8, 21.853), "домов", 2, "gigaam"),
    iv(ts(10, 47.749), ts(10, 48.229), "боже", 2, "gigaam"),
    iv(ts(12, 4.748), ts(12, 5.168), "верю", 2, "gigaam"),
    iv(ts(12, 8.251), ts(12, 8.652), "веру", 2, "gigaam"),
    iv(ts(1, 29.680), ts(1, 30.680), "повезло.", 3, "whisper"),
    iv(ts(5, 32.270), ts(5, 32.710), "карты", 3, "whisper"),
    iv(ts(6, 19.750), ts(6, 20.550), "Феникс,", 3, "whisper"),
    iv(ts(8, 21.240), ts(8, 21.740), "домов", 3, "whisper"),
    iv(ts(10, 47.400), ts(10, 48.120), "Боже.", 3, "whisper"),
    iv(ts(12, 4.750), ts(12, 5.150), "верю.", 3, "whisper"),
    iv(ts(12, 8.200), ts(12, 8.560), "веру", 3, "whisper"),
]


def test_real_run_collapses_to_one_row_per_spot():
    merged = review.merge_intervals(SAUL)
    assert [r["text"] for r in merged] == [
        "повезло", "карты", "Феникс,", "домов", "боже", "верю", "веру"]
    domov = merged[3]
    # the union of every catch — exactly what the output file holds
    assert domov["s"] == ts(8, 21.240) and domov["e"] == ts(8, 21.853)
    assert domov["passes"] == [1, 2, 3]
    assert domov["engines"] == ["gigaam", "whisper"]
    # a word only whisper found stays a plain single-pass row
    phoenix = merged[2]
    assert phoenix["pass"] == 3 and "passes" not in phoenix
    assert phoenix["engine"] == "whisper" and "engines" not in phoenix


def test_rows_come_in_time_order():
    merged = review.merge_intervals(SAUL)
    starts = [r["s"] for r in merged]
    assert starts == sorted(starts)


def test_unchecking_the_merged_row_unmutes_every_catch():
    """Before: rows 3 and 19 unchecked, row 37 still checked — the
    re-render muted «домов» anyway. Now there is one checkbox."""
    merged = review.merge_intervals(SAUL)
    merged[3]["muted"] = False
    still_muted = [(r["s"], r["e"]) for r in merged if r["muted"]]
    assert not any(s <= ts(8, 21.5) <= e for s, e in still_muted)


def test_any_copy_still_muting_keeps_the_row_checked():
    """An old sidecar with some copies unchecked: the output still has
    the spot muted, so the row says so (a family filter errs muted)."""
    data = [dict(r) for r in SAUL]
    for r in data:
        if r["text"] == "домов" and r["pass"] in (1, 2):
            r["muted"] = False
    domov = [r for r in review.merge_intervals(data)
             if r["text"] == "домов"][0]
    assert domov["muted"] is True
    for r in data:
        if r["text"] == "домов":
            r["muted"] = False
    domov = [r for r in review.merge_intervals(data)
             if r["text"] == "домов"][0]
    assert domov["muted"] is False


def test_same_word_in_one_pass_stays_two_rows():
    """«боже … боже» 0.2 s apart in ONE pass are two occurrences; only
    another pass's catch of the same word bridges a small gap."""
    two = [iv(10.0, 10.4, "боже", 1, "gigaam"),
           iv(10.6, 11.0, "боже", 1, "gigaam")]
    assert len(review.merge_intervals(two)) == 2
    shifted = [iv(10.0, 10.4, "боже", 1, "gigaam"),
               iv(10.6, 11.0, "Боже!", 2, "whisper")]
    merged = review.merge_intervals(shifted)
    assert len(merged) == 1
    assert (merged[0]["s"], merged[0]["e"]) == (10.0, 11.0)


def test_different_words_far_apart_stay_apart():
    rows = [iv(1.0, 1.4, "боже", 1, "gigaam"),
            iv(1.8, 2.2, "чертов", 2, "gigaam")]
    assert len(review.merge_intervals(rows)) == 2


def test_two_engines_hearing_different_words_share_a_row():
    rows = [iv(5.0, 5.5, "домов", 1, "gigaam"),
            iv(5.1, 5.6, "дома", 3, "whisper")]
    merged = review.merge_intervals(rows)
    assert len(merged) == 1
    assert merged[0]["text"] == "домов / дома"


def test_merge_is_stable_on_merged_data():
    once = review.merge_intervals(SAUL)
    assert review.merge_intervals(once) == once


def test_old_sidecar_is_merged_on_load(tmp_path):
    out = tmp_path / "v.clean.mp4"
    path = review.review_path_for(out)
    path.write_text(json.dumps({
        "version": 1, "source": str(tmp_path / "v.mp4"),
        "output": str(out), "pad_ms": 100, "intervals": SAUL,
    }, ensure_ascii=False), encoding="utf-8")
    data = review.load_review(path)
    assert len(data["intervals"]) == 7
    # merged in memory only — the file is rewritten on re-render
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert len(raw["intervals"]) == len(SAUL)


def test_review_dialog_shows_every_pass_and_engine(qapp, tmp_path,
                                                   monkeypatch):
    from wordmute_app.ui import review_dialog

    class DummyPlayer:
        def play(self, *a): pass
        def stop(self): pass
        def dispose(self): pass

    monkeypatch.setattr(review_dialog, "SnippetPlayer", DummyPlayer)
    source = tmp_path / "v.mp4"
    source.write_bytes(b"x")
    out = tmp_path / "v.clean.mp4"
    out.write_bytes(b"y")
    path = review.save_review(source, out, 100, SAUL)
    dialog = review_dialog.ReviewDialog(path)
    assert dialog.table.rowCount() == 7
    row = [r for r in range(7)
           if dialog.table.item(r, review_dialog.COL_TEXT).text()
           == "домов"][0]
    assert dialog.table.item(row, review_dialog.COL_PASS).text() == "1, 2, 3"
    assert dialog.table.item(row, review_dialog.COL_ENGINE).text() == \
        "gigaam, whisper"


def test_worker_records_one_spot_across_three_passes(qapp, tmp_path,
                                                     monkeypatch):
    """Each pass re-catches «бог» a few ms later, as real passes do;
    the sidecar and the history count see one muted spot."""
    from pathlib import Path
    from wordmute_app.core import history
    from wordmute_app.core.jobs import JobOptions, QueueItem
    from wordmute_app.engine import wordmute as engine
    from wordmute_app.ui.worker import ProcessWorker

    monkeypatch.setenv("APPDATA", str(tmp_path))
    calls = []

    def shifting_transcribe(media, *a, **k):
        calls.append(media)
        shift = 0.04 * (len(calls) - 1)
        return [{"w": "бог", "s": 1.0 + shift, "e": 1.4 + shift}]

    def fake_mute(media, intervals, out, beep_hz=None):
        Path(out).write_bytes(b"muted")
        engine._emit("mute_done", out=str(out))

    monkeypatch.setattr(engine, "transcribe", shifting_transcribe)
    monkeypatch.setattr(engine, "mute", fake_mute)
    src = tmp_path / "v.mp4"
    src.write_bytes(b"x")
    worker = ProcessWorker(
        [QueueItem(kind="file", path=src)], ({"бог"}, [], [], []),
        [("gigaam", "v3"), ("gigaam", "v3"), ("whisper", "small")],
        JobOptions(device="cpu", force_passes=True))
    worker.run()
    data = review.load_review(review.review_path_for(
        tmp_path / "v.clean.mp4"))
    assert len(data["intervals"]) == 1
    assert data["intervals"][0]["passes"] == [1, 2, 3]
    assert history.load_history()[-1]["muted"] == 1
