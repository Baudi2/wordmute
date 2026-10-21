"""yt-dlp wrapper: format filtering/sorting/specs and download flow,
all against a fake YoutubeDL (no network)."""

import http.cookiejar
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


BOOSTY_AUTH = "%7B%22accessToken%22%3A%22token%22%2C%22expiresAt%22%3A1%7D"
COOKIES = "".join("\t".join(row) + "\n" for row in (
    ("# Netscape HTTP Cookie File",),
    ("#HttpOnly_.boosty.to", "TRUE", "/", "FALSE", "4102444800", "auth",
     BOOSTY_AUTH),
    (".youtube.com", "TRUE", "/", "TRUE", "0", "SID", "session"),
))


def test_cookies_reach_a_real_youtubedl(tmp_path):
    """0.7.0-0.7.1 handed a jar over as opts["cookiejar"]: yt-dlp has no
    such option, so no site ever saw the cookies — Boosty told a paying
    user with a valid export «This post requires a subscription». The
    old test only inspected a FakeYDL's opts; this one asks the REAL
    YoutubeDL (offline), down to the Boosty extractor's own lookup."""
    cookies = tmp_path / "cookies.txt"
    cookies.write_text(COOKIES, encoding="utf-8")
    opts = downloader._with_cookies(downloader._base_opts(), cookies)
    with yt_dlp.YoutubeDL(opts) as ydl:
        header = ydl.cookiejar.get_cookie_header("https://boosty.to/x")
        assert f"auth={BOOSTY_AUTH}" in header
        boosty = ydl.get_info_extractor("Boosty")
        assert (boosty._get_cookies("https://boosty.to/")["auth"].value
                == BOOSTY_AUTH)
        assert "SID=session" in ydl.cookiejar.get_cookie_header(
            "https://www.youtube.com/watch?v=1")


def test_the_users_cookie_file_is_never_rewritten(tmp_path):
    """yt-dlp saves a path-type cookiefile on every close; the probe,
    the format fetch and the download pump overlap, and one session's
    save corrupted the export another had just loaded (audit, 0.7.0).
    Two real sessions open at once, both close: the file is untouched."""
    cookies = tmp_path / "cookies.txt"
    cookies.write_text(COOKIES, encoding="utf-8")
    before = cookies.read_bytes()
    first = yt_dlp.YoutubeDL(
        downloader._with_cookies(downloader._base_opts(), cookies))
    second = yt_dlp.YoutubeDL(
        downloader._with_cookies(downloader._base_opts(), cookies))
    with first, second:
        # a site setting a cookie mid-session must not reach the file
        first.cookiejar.set_cookie(http.cookiejar.Cookie(
            0, "new", "1", None, False, ".boosty.to", True, True, "/", True,
            False, 4102444800, False, None, None, {}))
        assert "auth=" in second.cookiejar.get_cookie_header(
            "https://boosty.to/")
    assert cookies.read_bytes() == before


def test_cookie_file_with_a_bom_still_signs_in(tmp_path):
    cookies = tmp_path / "bom.txt"
    cookies.write_text(COOKIES, encoding="utf-8-sig")
    with yt_dlp.YoutubeDL(downloader._with_cookies(
            downloader._base_opts(), cookies)) as ydl:
        assert "auth=" in ydl.cookiejar.get_cookie_header(
            "https://boosty.to/")


def test_missing_cookie_file_sends_none_and_creates_nothing(tmp_path):
    missing = tmp_path / "gone" / "cookies.txt"
    opts = downloader._with_cookies(downloader._base_opts(), missing)
    assert "cookiefile" not in opts
    with yt_dlp.YoutubeDL(opts):
        pass
    assert not missing.exists() and not missing.parent.exists()


def test_every_session_gets_its_own_stream(fake_ydl, tmp_path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text(COOKIES, encoding="utf-8")
    downloader.list_formats("https://example.com/v", cookies=cookies)
    fetch = FakeYDL.captured_opts["cookiefile"]
    downloader.download("https://example.com/v", "", tmp_path / "dl",
                        cookies=cookies)
    download = FakeYDL.captured_opts["cookiefile"]
    for stream in (fetch, download):
        assert not isinstance(stream, (str, Path))     # never the path
        assert stream.getvalue() == COOKIES
    assert fetch is not download
    assert "cookiejar" not in FakeYDL.captured_opts


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
