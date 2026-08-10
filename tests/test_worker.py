"""Worker pipeline with stubbed ASR/ffmpeg: signal flow, output files,
cancellation, per-file error isolation."""

from pathlib import Path

from wordmute_app.core.jobs import JobOptions, QueueItem
from wordmute_app.engine import wordmute as engine


def make_worker(files, monkeypatch, words=None, fail_for=(), plan=None):
    from wordmute_app.ui.worker import ProcessWorker

    words = words or [{"w": "бог", "s": 1.0, "e": 1.5}]

    def fake_transcribe(media, *a, **k):
        if media.name in fail_for:
            raise RuntimeError("boom")
        return words

    def fake_mute(media, intervals, out, beep_hz=None):
        Path(out).write_bytes(b"muted")

    monkeypatch.setattr(engine, "transcribe", fake_transcribe)
    monkeypatch.setattr(engine, "mute", fake_mute)

    items = [f if isinstance(f, QueueItem) else QueueItem(kind="file", path=f)
             for f in files]
    worker = ProcessWorker(items, ({"бог"}, [], [], []),
                           plan or [("whisper", "small")],
                           JobOptions(device="cpu"))
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


def test_item_output_event_carries_final_path(qapp, tmp_path, monkeypatch):
    inp = tmp_path / "v.mp4"
    inp.write_bytes(b"x")
    events = []
    worker, log = make_worker([inp], monkeypatch)
    worker.engine_event.connect(
        lambda e, d: events.append(d) if e == "item_output" else None)
    worker.run()
    assert events == [{"path": str(tmp_path / "v.clean.mp4")}]


def test_no_output_event_when_nothing_muted(qapp, tmp_path, monkeypatch):
    inp = tmp_path / "v.mp4"
    inp.write_bytes(b"x")
    worker, log = make_worker([inp], monkeypatch,
                              words=[{"w": "мир", "s": 0.0, "e": 0.5}])
    worker.run()
    assert "item_output" not in log["events"]


def test_review_sidecar_written_with_pass_info(qapp, tmp_path, monkeypatch):
    from wordmute_app.core import review

    inp = tmp_path / "v.mp4"
    inp.write_bytes(b"x")
    worker, log = make_worker([inp], monkeypatch)
    worker.run()

    assert "review_saved" in log["events"]
    data = review.load_review(
        review.review_path_for(tmp_path / "v.clean.mp4"))
    assert data["source"] == str(inp)
    assert len(data["intervals"]) == 1
    iv = data["intervals"][0]
    assert iv["text"] == "бог"
    assert iv["pass"] == 1
    assert iv["engine"] == "whisper"
    assert iv["muted"] is True


def test_review_dedupes_repeat_finds_across_passes(qapp, tmp_path,
                                                   monkeypatch):
    # the stubbed transcribe returns the same words every pass, so a
    # 2-pass plan re-finds the identical interval; it must appear once
    from wordmute_app.core import review

    inp = tmp_path / "v.mp4"
    inp.write_bytes(b"x")
    worker, _ = make_worker([inp], monkeypatch,
                            plan=[("whisper", "small"), ("gigaam", "v3")])
    worker.run()

    data = review.load_review(
        review.review_path_for(tmp_path / "v.clean.mp4"))
    assert len(data["intervals"]) == 1


def test_no_review_when_nothing_muted(qapp, tmp_path, monkeypatch):
    from wordmute_app.core import review

    inp = tmp_path / "v.mp4"
    inp.write_bytes(b"x")
    worker, log = make_worker([inp], monkeypatch,
                              words=[{"w": "мир", "s": 0.0, "e": 0.5}])
    worker.run()

    assert log["files"] == [(0, True, "")]
    assert "review_saved" not in log["events"]
    assert not review.review_path_for(tmp_path / "v.clean.mp4").exists()


def test_url_item_downloads_then_processes(qapp, tmp_path, monkeypatch):
    from wordmute_app.core import downloader

    def fake_download(url, spec, dest_dir, progress=None, cancelled=None,
                      cookies=None):
        assert url == "https://example.com/v"
        assert spec == "bv*+ba/b"
        progress({"status": "downloading", "downloaded_bytes": 10,
                  "total_bytes": 100, "speed": 1024, "eta": 5})
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)  # real download does this
        p = dest / "video.mp4"
        p.write_bytes(b"x")
        return p

    monkeypatch.setattr(downloader, "download", fake_download)
    item = QueueItem(kind="url", url="https://example.com/v",
                     format_spec="bv*+ba/b", title="Video")
    worker, log = make_worker([item], monkeypatch)
    worker._download_dir = tmp_path / "dl"
    worker.run()

    assert log["files"] == [(0, True, "")]
    assert "download_start" in log["events"]
    assert "download_progress" in log["events"]
    assert "download_done" in log["events"]
    assert (tmp_path / "dl" / "video.clean.mp4").read_bytes() == b"muted"


def test_second_url_downloads_while_first_processes(qapp, tmp_path,
                                                    monkeypatch):
    """Pipelining: once item 1 is downloaded and processing begins,
    item 2's download starts — it must not wait for item 1 to finish."""
    import threading
    from wordmute_app.core import downloader

    downloads = []
    second_started = threading.Event()

    def fake_download(url, spec, dest_dir, progress=None, cancelled=None,
                      cookies=None):
        downloads.append(url)
        if url == "u2":
            second_started.set()
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        p = dest / f"{url}.mp4"
        p.write_bytes(b"x")
        return p

    monkeypatch.setattr(downloader, "download", fake_download)
    worker, log = make_worker(
        [QueueItem(kind="url", url="u1", title="One"),
         QueueItem(kind="url", url="u2", title="Two")], monkeypatch)

    stub_transcribe = engine.transcribe  # installed by make_worker

    def transcribe_blocking(media, *a, **k):
        if media.name == "u1.mp4":
            assert second_started.wait(5), \
                "second download did not start during first processing"
        return stub_transcribe(media, *a, **k)

    monkeypatch.setattr(engine, "transcribe", transcribe_blocking)

    rows = []
    worker.engine_event.connect(
        lambda e, d: rows.append((e, d.get("row")))
        if e.startswith("download_") else None)
    worker._download_dir = tmp_path / "dl"
    worker.run()
    # the prefetch thread's signals are queued cross-thread; deliver them
    qapp.processEvents()

    assert log["files"] == [(0, True, ""), (1, True, "")]
    assert downloads == ["u1", "u2"]
    # every download event carries its item index for row routing
    assert ("download_start", 0) in rows and ("download_start", 1) in rows
    assert ("download_done", 0) in rows and ("download_done", 1) in rows
    assert all(row is not None for _, row in rows)


def test_url_download_failure_isolated(qapp, tmp_path, monkeypatch):
    from wordmute_app.core import downloader

    monkeypatch.setattr(
        downloader, "download",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network down")))
    local = tmp_path / "ok.mp4"
    local.write_bytes(b"x")
    item = QueueItem(kind="url", url="https://example.com/bad")
    worker, log = make_worker([item, local], monkeypatch)
    worker._download_dir = tmp_path / "dl"
    worker.run()

    assert log["files"][0] == (0, False, "network down")
    assert log["files"][1] == (1, True, "")
    assert log["finished"] == [(1, 2)]
