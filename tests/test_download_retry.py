"""A queued rutube episode failed on the spot — «Unable to download
options JSON: Read timed out (read timeout=20.0)» — while the next one
downloaded at 26 MB/s, and its card kept saying «загрузка…» with no
progress until its turn came an hour later. Now a transient network
error is retried a few times (the card says so), and a download the
pump gives up on is shown on the card at once."""

import time
from types import SimpleNamespace

import pytest
import yt_dlp

from wordmute_app.core import downloader

TIMEOUT = ("ERROR: [rutube] ef3f6229: Unable to download options JSON: "
           "HTTPSConnectionPool(host='rutube.ru', port=443): Read timed "
           "out. (read timeout=20.0)")
FORBIDDEN = "ERROR: unable to download video data: HTTP Error 403: Forbidden"


class FlakyYDL:
    """Fails the first `failures` sessions with `error`, then succeeds."""
    failures, error, sessions = 0, TIMEOUT, []

    def __init__(self, opts):
        FlakyYDL.sessions.append(opts)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False, process=True):
        if len(FlakyYDL.sessions) <= FlakyYDL.failures:
            raise yt_dlp.utils.DownloadError(FlakyYDL.error)
        return {"id": "x", "title": "v", "webpage_url": url}

    def process_ie_result(self, probe, download=True):
        return {"requested_downloads": [{"filepath": "v.mp4"}]}


@pytest.fixture
def flaky(monkeypatch):
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FlakyYDL)
    monkeypatch.setattr(downloader, "RETRY_WAITS", (0.01, 0.01, 0.01))
    FlakyYDL.failures, FlakyYDL.error, FlakyYDL.sessions = 0, TIMEOUT, []
    return FlakyYDL


def test_transient_errors_mean_not_now():
    assert downloader.is_transient_error(RuntimeError(TIMEOUT))
    assert downloader.is_transient_error(RuntimeError(
        "('Connection aborted.', ConnectionResetError(10054, ...))"))
    assert downloader.is_transient_error(RuntimeError("HTTP Error 503"))
    assert not downloader.is_transient_error(RuntimeError(FORBIDDEN))
    assert not downloader.is_transient_error(RuntimeError(
        "[Boosty] This post requires a subscription"))
    assert not downloader.is_transient_error(RuntimeError("Video unavailable"))


def test_a_timeout_is_retried_and_the_card_is_told(flaky, tmp_path):
    flaky.failures = 2
    told = []
    path = downloader.download("https://rutube.ru/video/x/", "", tmp_path,
                               retry=lambda *a: told.append(a))
    assert str(path).endswith("v.mp4")
    assert len(flaky.sessions) == 3
    assert [(a, n) for a, n, _w, _e in told] == [(2, 4), (3, 4)]
    assert all(isinstance(e, yt_dlp.utils.DownloadError) for *_, e in told)


def test_every_attempt_gets_a_fresh_cookies_stream(flaky, tmp_path):
    """A session consumes its cookiefile stream (yt-dlp saves back into
    it): a retry that reused it would sign in as a guest."""
    cookies = tmp_path / "c.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n"
                       ".boosty.to\tTRUE\t/\tFALSE\t0\tauth\tx\n",
                       encoding="utf-8")
    flaky.failures = 1
    downloader.download("https://rutube.ru/video/x/", "", tmp_path,
                        cookies=cookies)
    streams = [o["cookiefile"] for o in flaky.sessions]
    assert len(streams) == 2 and streams[0] is not streams[1]
    assert all(s.getvalue().count("auth") == 1 for s in streams)


def test_the_fourth_failure_is_final(flaky, tmp_path):
    flaky.failures = 99
    with pytest.raises(yt_dlp.utils.DownloadError):
        downloader.download("https://rutube.ru/video/x/", "", tmp_path)
    assert len(flaky.sessions) == 4


def test_a_403_is_not_retried(flaky, tmp_path):
    flaky.failures, flaky.error = 99, FORBIDDEN
    with pytest.raises(yt_dlp.utils.DownloadError):
        downloader.download("https://rutube.ru/video/x/", "", tmp_path)
    assert len(flaky.sessions) == 1


def test_cancel_during_the_wait_stops_at_once(flaky, tmp_path, monkeypatch):
    monkeypatch.setattr(downloader, "RETRY_WAITS", (30,))
    flaky.failures = 99
    t0 = time.monotonic()
    with pytest.raises(downloader.DownloadCancelled):
        downloader.download("https://rutube.ru/video/x/", "", tmp_path,
                            cancelled=lambda: True)
    assert time.monotonic() - t0 < 2


def test_pump_reports_a_failed_download_before_its_turn():
    from wordmute_app.ui import worker as w

    events = []

    def download(item, index):
        if item.url == "bad":
            raise RuntimeError(TIMEOUT)
        return f"{item.url}.mp4"

    fake = SimpleNamespace(_cancelled=False, _cookies=None,
                           _download=download,
                           engine_event=SimpleNamespace(
                               emit=lambda e, d: events.append((e, d))))
    jobs = [(1, SimpleNamespace(url="bad")), (2, SimpleNamespace(url="ok"))]
    pump = w._DownloadPump(fake, jobs)
    pump.run()                       # synchronous: the thread body itself
    assert pump.wait_for(1)[0] is None and pump.wait_for(2) == ("ok.mp4", None)
    assert [e for e, _ in events] == ["download_failed"]
    assert events[0][1]["row"] == 1
    assert "Read timed out" in events[0][1]["message"]
    assert "--" not in events[0][1]["message"]        # no yt-dlp CLI advice


def test_pump_stays_quiet_about_cancellation():
    from wordmute_app.ui import worker as w

    events = []
    fake = SimpleNamespace(
        _cancelled=False, _cookies=None,
        _download=lambda item, index: (_ for _ in ()).throw(
            downloader.DownloadCancelled()),
        engine_event=SimpleNamespace(emit=lambda e, d: events.append(e)))
    pump = w._DownloadPump(fake, [(0, SimpleNamespace(url="u"))])
    pump.run()
    assert events == []
    assert isinstance(pump.wait_for(0)[1], downloader.DownloadCancelled)


def test_cards_show_the_retry_and_the_failure(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import gpu
    from wordmute_app.core.jobs import QueueItem
    from wordmute_app.ui import i18n
    monkeypatch.setattr(gpu, "detect_gpus", lambda: [])
    from wordmute_app.ui.main_window import STATE_ROLE, MainWindow

    i18n.set_language("ru")
    try:
        window = MainWindow()
        for n in (1, 2):
            window._add_url_row(QueueItem(kind="url", url=f"https://r/{n}",
                                          format_spec="b", format_label="b"))
        window._active_rows = [0, 1]
        before = window.status_text(0)
        window._on_engine_event("download_retry", {
            "row": 1, "attempt": 2, "attempts": 4, "wait": 5})
        assert window.status_text(1) == "ошибка сети — попытка 2/4 через 5 с"
        window._on_engine_event("download_failed", {
            "row": 1, "message": "Read timed out"})
        assert window.status_text(1) == "загрузка не удалась: Read timed out"
        assert window.queue.item(1).data(STATE_ROLE) == "err"
        assert window.status_text(0) == before            # the other card
        window.close()
    finally:
        i18n.set_language("en")
