"""Single-file downloads from CDNs that cap each connection go as
parallel byte ranges. Measured on a Boosty post (okcdn.ru): one
connection 1.03-1.08 MB/s however it was asked, 4 parallel range
requests 10-15 MB/s. Runs the REAL yt-dlp (selection, HLS fragment
downloader, merger, fixups) against a local server that honours Range
and throttles every connection; only extract_info is replaced."""

import copy
import hashlib
import http.server
import shutil
import subprocess
import threading
import time

import pytest
import yt_dlp

from wordmute_app.core import downloader

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None,
                                reason="ffmpeg is not on PATH")

PAGE = "https://boosty.to/someone/posts/abc"
PART = 1024 * 1024


class CappedCdn:
    """Serves files with (or without) Range support, each connection
    capped at `rate` bytes/s; records requests and peak concurrency."""

    def __init__(self, files, ranges=True, rate=4 * 1024 * 1024):
        self.files, self.ranges, self.rate = files, ranges, rate
        self.requests, self.active, self.peak = [], 0, 0
        self.lock = threading.Lock()
        cdn = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_GET(self):
                body = cdn.files.get(self.path.split("?")[0])
                if body is None:
                    self.send_error(404)
                    return
                wanted = self.headers.get("Range")
                with cdn.lock:
                    cdn.requests.append((self.path, wanted))
                    cdn.active += 1
                    cdn.peak = max(cdn.peak, cdn.active)
                try:
                    start, end, status = 0, len(body) - 1, 200
                    if wanted and cdn.ranges:
                        a, _, b = wanted.split("=")[1].partition("-")
                        start = int(a)
                        end = min(int(b), len(body) - 1) if b else end
                        status = 206
                    self.send_response(status)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Accept-Ranges",
                                     "bytes" if cdn.ranges else "none")
                    self.send_header("Content-Length", str(end - start + 1))
                    if status == 206:
                        self.send_header("Content-Range",
                                         f"bytes {start}-{end}/{len(body)}")
                    self.end_headers()
                    piece = 64 * 1024
                    for pos in range(start, end + 1, piece):
                        chunk = body[pos:min(pos + piece, end + 1)]
                        self.wfile.write(chunk)
                        time.sleep(len(chunk) / cdn.rate)
                except (ConnectionError, OSError):
                    pass
                finally:
                    with cdn.lock:
                        cdn.active -= 1

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
                                                      Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever,
                         daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def range_requests(self, path):
        return [r for p, r in self.requests if p == path and r]


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    """Real 2-5 MB files: muxed mp4, video-only mp4, audio-only m4a."""
    d = tmp_path_factory.mktemp("cdn")
    noise = "nullsrc=s=160x120:d=4,geq=random(1)*255:128:128"
    ffmpeg("-f", "lavfi", "-i", noise, "-f", "lavfi", "-i",
           "sine=frequency=440:duration=4", "-c:v", "libx264",
           "-preset", "ultrafast", "-qp", "0", "-c:a", "aac",
           "-shortest", str(d / "muxed.mp4"))
    ffmpeg("-i", str(d / "muxed.mp4"), "-map", "0:v", "-c", "copy",
           str(d / "video.mp4"))
    ffmpeg("-f", "lavfi", "-i", "anoisesrc=d=20:a=0.5", "-ac", "2",
           "-ar", "48000", "-c:a", "alac", str(d / "audio.m4a"))
    files = {f"/{p.name}": p.read_bytes() for p in d.iterdir()}
    assert all(len(b) > 2 * PART for b in files.values()), \
        {k: len(v) for k, v in files.items()}
    return files


@pytest.fixture
def parts(monkeypatch):
    monkeypatch.setattr(downloader, "RANGE_PART", PART)


def fake_extraction(monkeypatch, formats, duration=4.0):
    probe = {"id": "abc", "title": "Post", "duration": duration,
             "extractor": "boosty", "extractor_key": "Boosty",
             "webpage_url": PAGE, "formats": formats}
    monkeypatch.setattr(yt_dlp.YoutubeDL, "extract_info",
                        lambda self, url, download=True, process=True:
                        copy.deepcopy(probe))


def fmt(cdn, name, fid, **codecs):
    # no "protocol": extractors leave it for processing to fill in, and
    # a split that required it never fired on the real Boosty probe
    return {"format_id": fid, "url": cdn.url + "/" + name,
            "ext": name.rsplit(".", 1)[1], **codecs}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def test_one_file_comes_in_parallel_ranges_byte_for_byte(
        media, parts, tmp_path, monkeypatch):
    cdn = CappedCdn(media)
    try:
        fake_extraction(monkeypatch, [
            fmt(cdn, "muxed.mp4", "ultra_hd", vcodec="h264", acodec="aac",
                height=240)])
        seen = []
        path = downloader.download(PAGE, downloader.BEST_SPEC, tmp_path,
                                   progress=seen.append)
    finally:
        cdn.close()
    assert sha(path.read_bytes()) == sha(media["/muxed.mp4"])
    ranges = cdn.range_requests("/muxed.mp4")
    assert ranges[0] == "bytes=0-0"               # the size probe
    size = len(media["/muxed.mp4"])
    assert len(ranges) - 1 == -(-size // PART)    # one request per part
    assert cdn.peak >= 2, "the parts were fetched one at a time"
    assert seen and seen[-1]["status"] == "finished"


def test_video_and_audio_both_split_then_merged(media, parts, tmp_path,
                                               monkeypatch):
    cdn = CappedCdn(media)
    try:
        fake_extraction(monkeypatch, [
            fmt(cdn, "video.mp4", "dash-7", vcodec="avc1", acodec="none",
                height=240, tbr=3000),
            fmt(cdn, "audio.m4a", "dash-13", vcodec="none",
                acodec="alac", tbr=1500)])
        path = downloader.download(PAGE, downloader.BEST_SPEC, tmp_path)
    finally:
        cdn.close()
    assert len(cdn.range_requests("/video.mp4")) > 2
    assert len(cdn.range_requests("/audio.m4a")) > 2
    streams = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True).stdout.split()
    assert sorted(streams) == ["audio", "video"]


def test_server_without_range_support_downloads_as_before(
        media, parts, tmp_path, monkeypatch):
    cdn = CappedCdn(media, ranges=False, rate=64 * 1024 * 1024)
    try:
        fake_extraction(monkeypatch, [
            fmt(cdn, "muxed.mp4", "ultra_hd", vcodec="h264", acodec="aac")])
        path = downloader.download(PAGE, downloader.BEST_SPEC, tmp_path)
    finally:
        cdn.close()
    assert sha(path.read_bytes()) == sha(media["/muxed.mp4"])
    # the 1-byte probe got a 200, so nothing was split
    assert cdn.range_requests("/muxed.mp4") == ["bytes=0-0"]


def test_other_sites_are_left_alone(media, parts, tmp_path, monkeypatch):
    cdn = CappedCdn(media, rate=64 * 1024 * 1024)
    try:
        fake_extraction(monkeypatch, [
            fmt(cdn, "muxed.mp4", "18", vcodec="h264", acodec="aac")])
        path = downloader.download("https://www.youtube.com/watch?v=x",
                                   downloader.BEST_SPEC, tmp_path)
    finally:
        cdn.close()
    assert sha(path.read_bytes()) == sha(media["/muxed.mp4"])
    assert cdn.range_requests("/muxed.mp4") == []
    assert cdn.peak == 1


def test_parallel_site_matching():
    assert downloader._parallel_site("https://boosty.to/a/posts/1")
    assert downloader._parallel_site("https://vkvideo.ru/video-1_2")
    assert downloader._parallel_site("https://m.vk.com/video1_2")
    assert downloader._parallel_site("https://ok.ru/video/1")
    assert not downloader._parallel_site("https://rutube.ru/video/1/")
    assert not downloader._parallel_site("https://notvk.com/x")
    assert not downloader._parallel_site(None)


def test_playlist_covers_the_file_exactly():
    text = downloader._byte_range_playlist("https://cdn/x.mp4",
                                           10 * 1024 * 1024 + 5, 100.0)
    ranges = [line.split(":")[1] for line in text.splitlines()
              if line.startswith("#EXT-X-BYTERANGE")]
    spans = [(int(r.split("@")[1]), int(r.split("@")[0])) for r in ranges]
    assert spans[0][0] == 0
    for (start, length), (nxt, _) in zip(spans, spans[1:]):
        assert start + length == nxt
    assert spans[-1][0] + spans[-1][1] == 10 * 1024 * 1024 + 5
    assert text.rstrip().endswith("#EXT-X-ENDLIST")
