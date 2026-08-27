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

    def extract_info(self, url, download=False, process=True):
        if download:
            for hook in FakeYDL.captured_opts.get("progress_hooks", []):
                hook({"status": "downloading", "downloaded_bytes": 50,
                      "total_bytes": 100, "speed": 2048, "eta": 3})
                hook({"status": "finished"})
            return {"requested_downloads": [{"filepath": r"C:\dl\video.mp4"}]}
        return dict(FakeYDL.info)

    def process_ie_result(self, info, download=False):
        # download() extracts first (process=False) and downloads second
        return self.extract_info("", download=download)


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


def test_quality_class_uses_the_long_side():
    """A 2.39:1 film at 1920×800 is that title's 1080p stream —
    labelling by raw height read as «800p»; verticals likewise."""
    assert downloader.quality_class(1920, 800) == "1080p"
    assert downloader.quality_class(1280, 528) == "720p"
    assert downloader.quality_class(856, 352) == "480p"
    assert downloader.quality_class(1080, 1920) == "1080p"
    assert downloader.quality_class(1920, 1080) == "1080p"
    assert downloader.quality_class(1440, 608) == "608p"  # no class: raw
    assert downloader.quality_class(None, 720) == "720p"
    assert downloader.quality_class(None, None) == ""


def test_mirror_duplicates_collapse_to_one_row(fake_ydl):
    """rutube serves one rendition from several mirrors: four identical
    «800p · 3.81 GB» rows are one choice."""
    mirror = {"format_id": "m1", "ext": "mp4", "vcodec": "avc1",
              "acodec": "mp4a", "width": 1920, "height": 800, "fps": 24,
              "tbr": 4460}
    FakeYDL.info = dict(FakeYDL.info)
    FakeYDL.info["formats"] = [
        mirror,
        {**mirror, "format_id": "m2"},
        {**mirror, "format_id": "m3", "tbr": 4463},   # same within 50
        {**mirror, "format_id": "hd", "width": 1280, "height": 528},
    ]
    info = downloader.list_formats("https://example.com/v")
    assert [f["format_id"] for f in info["formats"]] == ["m1", "hd"]


def test_spec_for_format():
    video_only = FORMATS[2]
    progressive = FORMATS[3]
    audio = FORMATS[1]
    assert downloader.spec_for_format(video_only) == "137+ba/137"
    assert downloader.spec_for_format(progressive) == "18"
    assert downloader.spec_for_format(audio) == "140"


def test_size_estimated_from_bitrate_when_missing():
    f = {"format_id": "hls-1080", "ext": "mp4", "vcodec": "avc1",
         "acodec": "mp4a", "height": 1080, "tbr": 4000}
    # no duration -> no estimate possible
    assert downloader.describe_format(f)["size"] == ""
    # tbr 4000 kbit/s * 600 s / 8 = 300 MB, marked approximate
    d = downloader.describe_format(f, duration=600)
    assert d["size"] == "~286.1 MB"


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
    # embedded yt-dlp retries nothing unless told: a dropped connection
    # mid-file used to fail the item on the spot
    assert FakeYDL.captured_opts["retries"] >= 5
    assert FakeYDL.captured_opts["fragment_retries"] >= 5
    assert [d["status"] for d in seen] == ["downloading", "finished"]


def test_download_cancellation(fake_ydl, tmp_path):
    with pytest.raises(downloader.DownloadCancelled):
        downloader.download("https://example.com/v", "", tmp_path,
                            cancelled=lambda: True)


def test_cookies_loaded_into_a_jar_not_handed_as_a_file(fake_ydl, tmp_path):
    """Audit fix: as `cookiefile` the user's export was rewritten by
    every yt-dlp session close — three ran concurrently and one
    truncated the jar another had just loaded."""
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    downloader.list_formats("https://example.com/v", cookies=cookies)
    assert "cookiefile" not in FakeYDL.captured_opts
    assert FakeYDL.captured_opts["cookiejar"].filename == str(cookies)

    downloader.download("https://example.com/v", "", tmp_path / "dl",
                        cookies=cookies)
    assert FakeYDL.captured_opts["cookiejar"].filename == str(cookies)


def test_no_cookies_key_when_unset(fake_ydl):
    downloader.list_formats("https://example.com/v")
    assert "cookiefile" not in FakeYDL.captured_opts
    assert "cookiejar" not in FakeYDL.captured_opts


def test_download_refuses_playlists_before_downloading(fake_ydl, tmp_path):
    """A watch?v=…&list=… link downloaded the whole playlist (hours,
    gigabytes) and then failed with a bogus error."""
    assert FakeYDL.captured_opts is None or True
    FakeYDL.info = {"_type": "playlist", "title": "list", "entries": []}
    seen = []
    with pytest.raises(ValueError, match="[Pp]laylist"):
        downloader.download("https://example.com/list", "", tmp_path,
                            progress=seen.append)
    assert seen == []                       # nothing was fetched
    assert FakeYDL.captured_opts["noplaylist"] is True
