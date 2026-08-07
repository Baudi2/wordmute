"""yt-dlp wrapper: format filtering/sorting/specs and download flow,
all against a fake YoutubeDL (no network)."""

from pathlib import Path

import pytest
import yt_dlp

from wordmute_app.core import downloader

FORMATS = [
    {"format_id": "sb0", "ext": "mhtml", "vcodec": "none", "acodec": "none",
     "format_note": "storyboard"},
    {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a",
     "tbr": 129, "format_note": "audio"},
    {"format_id": "137", "ext": "mp4", "vcodec": "avc1", "acodec": "none",
     "height": 1080, "fps": 25, "filesize": 200 * 1024 * 1024},
    {"format_id": "18", "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a",
     "height": 360, "fps": 25, "filesize_approx": 30 * 1024 * 1024},
]


class FakeYDL:
    captured_opts = None
    info = None

    def __init__(self, opts=None):
        FakeYDL.captured_opts = opts or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        if download:
            for hook in FakeYDL.captured_opts.get("progress_hooks", []):
                hook({"status": "downloading", "downloaded_bytes": 50,
                      "total_bytes": 100, "speed": 2048, "eta": 3})
                hook({"status": "finished"})
            return {"requested_downloads": [{"filepath": r"C:\dl\video.mp4"}]}
        return dict(FakeYDL.info)


@pytest.fixture
def fake_ydl(monkeypatch):
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    FakeYDL.info = {"title": "Тестовое видео", "duration": 300,
                    "webpage_url": "https://example.com/v",
                    "formats": list(FORMATS)}
    return FakeYDL


def test_list_formats_filters_and_sorts(fake_ydl):
    info = downloader.list_formats("https://example.com/v")
    assert info["title"] == "Тестовое видео"
    assert info["duration"] == 300
    ids = [f["format_id"] for f in info["formats"]]
    assert ids == ["137", "18", "140"]  # video by height desc, audio last


def test_list_formats_rejects_playlists(fake_ydl):
    FakeYDL.info = {"_type": "playlist", "title": "list"}
    with pytest.raises(ValueError, match="[Pp]laylist"):
        downloader.list_formats("https://example.com/list")


def test_spec_for_format():
    video_only = FORMATS[2]
    progressive = FORMATS[3]
    audio = FORMATS[1]
    assert downloader.spec_for_format(video_only) == "137+ba/137"
    assert downloader.spec_for_format(progressive) == "18"
    assert downloader.spec_for_format(audio) == "140"


def test_describe_and_label():
    d = downloader.describe_format(FORMATS[2])
    assert d["resolution"] == "1080p"
    assert d["kind"] == "video only"
    assert d["size"] == "200.0 MB"
    assert downloader.format_label(FORMATS[2]) == "1080p mp4"
    assert downloader.format_label(FORMATS[1]) == "audio m4a"


def test_download_reports_progress_and_returns_path(fake_ydl, tmp_path):
    seen = []
    path = downloader.download("https://example.com/v", "", tmp_path / "dl",
                               progress=seen.append)
    assert path == Path(r"C:\dl\video.mp4")
    assert (tmp_path / "dl").is_dir()  # created
    assert FakeYDL.captured_opts["format"] == downloader.BEST_SPEC
    assert FakeYDL.captured_opts["windowsfilenames"] is True
    assert [d["status"] for d in seen] == ["downloading", "finished"]


def test_download_cancellation(fake_ydl, tmp_path):
    with pytest.raises(downloader.DownloadCancelled):
        downloader.download("https://example.com/v", "", tmp_path,
                            cancelled=lambda: True)


def test_cookies_passed_to_ytdlp(fake_ydl, tmp_path):
    cookies = tmp_path / "cookies.txt"
    downloader.list_formats("https://example.com/v", cookies=cookies)
    assert FakeYDL.captured_opts["cookiefile"] == str(cookies)

    downloader.download("https://example.com/v", "", tmp_path / "dl",
                        cookies=cookies)
    assert FakeYDL.captured_opts["cookiefile"] == str(cookies)


def test_no_cookies_key_when_unset(fake_ydl):
    downloader.list_formats("https://example.com/v")
    assert "cookiefile" not in FakeYDL.captured_opts
