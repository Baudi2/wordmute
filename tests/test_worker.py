"""Worker pipeline with stubbed ASR/ffmpeg: signal flow, output files,
cancellation, per-file error isolation."""

from pathlib import Path

from wordmute_app.core.jobs import JobOptions
from wordmute_app.engine import wordmute as engine


def make_worker(files, monkeypatch, words=None, fail_for=()):
    from wordmute_app.ui.worker import ProcessWorker

    words = words or [{"w": "бог", "s": 1.0, "e": 1.5}]

    def fake_transcribe(media, *a, **k):
        if media.name in fail_for:
            raise RuntimeError("boom")
        return words

    def fake_mute(media, intervals, out):
        Path(out).write_bytes(b"muted")

    monkeypatch.setattr(engine, "transcribe", fake_transcribe)
    monkeypatch.setattr(engine, "mute", fake_mute)

    worker = ProcessWorker(files, ({"бог"}, [], [], []),
                           [("whisper", "small")], JobOptions(device="cpu"))
    log = {"events": [], "files": [], "finished": []}
    worker.engine_event.connect(lambda e, d: log["events"].append(e))
    worker.file_finished.connect(
        lambda i, ok, err: log["files"].append((i, ok, err)))
    worker.all_finished.connect(lambda d, t: log["finished"].append((d, t)))
    return worker, log


def test_single_file_success(qapp, tmp_path, monkeypatch):
    inp = tmp_path / "v.mp4"
    inp.write_bytes(b"x")
    worker, log = make_worker([inp], monkeypatch)
    worker.run()  # synchronous: we test the pipeline, not threading

    assert log["files"] == [(0, True, "")]
    assert log["finished"] == [(1, 1)]
    assert (tmp_path / "v.clean.mp4").read_bytes() == b"muted"
    assert "words_count" in log["events"]
    assert "match_found" in log["events"]


def test_error_isolation_between_files(qapp, tmp_path, monkeypatch):
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    a.write_bytes(b"x")
    b.write_bytes(b"x")
    worker, log = make_worker([a, b], monkeypatch, fail_for={"a.mp4"})
    worker.run()

    assert log["files"][0] == (0, False, "boom")
    assert log["files"][1] == (1, True, "")
    assert log["finished"] == [(1, 2)]
    assert (tmp_path / "b.clean.mp4").exists()


def test_cancel_before_run_marks_all_cancelled(qapp, tmp_path, monkeypatch):
    a = tmp_path / "a.mp4"
    a.write_bytes(b"x")
    worker, log = make_worker([a], monkeypatch)
    worker.cancel()
    worker.run()

    assert log["files"] == [(0, False, "cancelled")]
    assert log["finished"] == [(0, 1)]
    assert not (tmp_path / "a.clean.mp4").exists()


def test_output_dir_is_created_and_used(qapp, tmp_path, monkeypatch):
    inp = tmp_path / "v.mp4"
    inp.write_bytes(b"x")
    worker, log = make_worker([inp], monkeypatch)
    out_dir = tmp_path / "out" / "nested"
    worker._output_dir = out_dir
    worker.run()

    assert log["files"] == [(0, True, "")]
    assert (out_dir / "v.clean.mp4").read_bytes() == b"muted"
    assert not (tmp_path / "v.clean.mp4").exists()


def test_reporter_restored_after_run(qapp, tmp_path, monkeypatch):
    inp = tmp_path / "v.mp4"
    inp.write_bytes(b"x")
    worker, _ = make_worker([inp], monkeypatch)
    worker.run()
    assert engine._reporter is engine._default_reporter
