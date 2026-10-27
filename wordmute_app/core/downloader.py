"""yt-dlp integration: format listing and downloading with progress.

Uses yt-dlp's Python API rather than shelling out, so format data and
download progress arrive as callbacks. yt_dlp is imported lazily to
keep app startup fast."""

import copy
import io
import math
import time
import urllib.parse
from pathlib import Path

BEST_SPEC = "bv*+ba/b"
BEST_LABEL = "best quality"

# Batch adds (several links at once) can't show a format table per
# link, so the user picks ONE cap for the whole batch. Height caps
# fall back to the best available below the cap, then to any single
# stream, so a link that has nothing that small still downloads.
QUALITY_PRESETS = (
    ("best", "best quality", BEST_SPEC),
    ("2160", "up to 2160p (4K)",
     "bv*[height<=2160]+ba/b[height<=2160]/bv*+ba/b"),
    ("1440", "up to 1440p",
     "bv*[height<=1440]+ba/b[height<=1440]/bv*+ba/b"),
    ("1080", "up to 1080p",
     "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b"),
    ("720", "up to 720p",
     "bv*[height<=720]+ba/b[height<=720]/bv*+ba/b"),
    ("480", "up to 480p",
     "bv*[height<=480]+ba/b[height<=480]/bv*+ba/b"),
    ("audio", "audio only (smallest)", "ba/b"),
)
DEFAULT_QUALITY = "1080"   # sane default: HD without 4K-sized files


def quality_spec(key: str) -> tuple:
    """(format spec, label) for a batch quality preset key."""
    for name, label, spec in QUALITY_PRESETS:
        if name == key:
            return spec, label
    return BEST_SPEC, BEST_LABEL


class DownloadCancelled(Exception):
    pass


PLAYLIST_MESSAGE = "Playlists are not supported — paste a single video URL."


def _base_opts() -> dict:
    # noplaylist: a watch URL copied while a playlist was open carries
    # &list=… — without it yt-dlp downloaded the WHOLE playlist (hours,
    # gigabytes) and then the item failed with a bogus error
    return {"quiet": True, "no_warnings": True, "noprogress": True,
            "noplaylist": True}


def _is_playlist(info) -> bool:
    return (info or {}).get("_type") in ("playlist", "multi_video")


def _has_video(f) -> bool:
    return (f.get("vcodec") or "none") != "none"


def _has_audio(f) -> bool:
    return (f.get("acodec") or "none") != "none"


def _is_media(f) -> bool:
    if f.get("ext") == "mhtml":  # storyboard thumbnails
        return False
    return _has_video(f) or _has_audio(f)


# 16:9 quality classes matched by the LONG side: a 2.39:1 film at
# 1920×800 is the «1080p» stream of that title, and a vertical
# 1080×1920 short is 1080p too — labelling by raw height made both
# read as something worse («800p»). The raw WxH stays in the note.
_CLASS_BY_LONG_SIDE = ((3840, 2160), (2560, 1440), (1920, 1080),
                       (1280, 720), (854, 480), (640, 360), (426, 240))


def quality_class(width, height) -> str:
    if not height:
        return ""
    if width:
        long_side = max(width, height)
        for std_width, std_height in _CLASS_BY_LONG_SIDE:
            if abs(long_side - std_width) <= std_width * 0.06:
                return f"{std_height}p"
    return f"{height}p"


def _dedupe_formats(formats) -> list:
    """rutube (and other HLS sites) serve one rendition from several
    mirrors — four identical «800p · 3.81 GB» rows are one choice."""
    seen = set()
    out = []
    for f in formats:
        key = (f.get("width"), f.get("height"), f.get("ext"),
               f.get("fps"), format_kind(f),
               int((f.get("tbr") or 0) / 50),
               f.get("filesize") or f.get("filesize_approx"))
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def sort_formats(formats) -> list:
    """Video formats first (best resolution on top), audio-only after."""
    def key(f):
        return (0 if _has_video(f) else 1,
                -(f.get("height") or 0),
                -(f.get("fps") or 0),
                -(f.get("tbr") or 0))
    return sorted(formats, key=key)


def _with_cookies(opts: dict, cookies) -> dict:
    """cookies: path to a Netscape-format cookie file (as exported by
    yt-dlp or browser extensions) for sites that need a login.

    Each yt-dlp session gets the file's TEXT as an in-memory stream,
    never the path: yt-dlp rewrites a path-type `cookiefile` on every
    session close, and the probe, the format fetch and the download
    pump run concurrently — one session's save truncated the file
    another had just loaded, and the user's export got corrupted. A
    stream is a documented `cookiefile` value (read on open, saved
    back into the stream on close).

    0.7.0-0.7.1 handed over a loaded jar as opts["cookiejar"] — yt-dlp
    has no such option and ignored it, so NO cookies reached any site:
    Boosty answered «This post requires a subscription» to a paying
    user with a valid export. tests/test_downloader.py now checks what
    a real YoutubeDL sees.

    An unreadable or missing file sends no cookies (and never makes
    yt-dlp create one at that path); the site's sign-in error then
    reaches the card, where humanize_download_error names the file."""
    if cookies:
        try:
            # utf-8-sig: a BOM turned the header line into a bogus entry
            text = Path(cookies).read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            return opts
        opts["cookiefile"] = io.StringIO(text)
    return opts


def list_formats(url: str, cookies=None) -> dict:
    import yt_dlp
    with yt_dlp.YoutubeDL(_with_cookies(_base_opts(), cookies)) as ydl:
        info = ydl.extract_info(url, download=False)
    if _is_playlist(info):
        raise ValueError(PLAYLIST_MESSAGE)
    formats = _dedupe_formats(
        f for f in info.get("formats") or [] if _is_media(f))
    return {"title": info.get("title") or url,
            "duration": info.get("duration"),
            "url": info.get("webpage_url") or url,
            "formats": sort_formats(formats)}


def probe_url(url: str, cookies=None) -> dict:
    """Lightweight metadata for a queued link: real title, duration and
    a thumbnail URL — so batch-added cards stop reading as bare URLs
    until the download finishes. One extract_info call, no download."""
    import yt_dlp
    with yt_dlp.YoutubeDL(_with_cookies(_base_opts(), cookies)) as ydl:
        info = ydl.extract_info(url, download=False)
    if _is_playlist(info):
        # the card must not masquerade as the first video: the download
        # will refuse the playlist, so say so where the title goes
        return {"title": "[playlist] " + (info.get("title") or url),
                "duration": None, "thumbnail_url": "", "playlist": True}
    return {"title": info.get("title") or "",
            "duration": info.get("duration"),
            "thumbnail_url": info.get("thumbnail") or ""}


def spec_for_format(f) -> str:
    """yt-dlp format selector for one row of the format table. Video-only
    streams get paired with the best audio (falling back to the bare
    stream if no separate audio exists)."""
    fid = str(f["format_id"])
    if _has_video(f) and not _has_audio(f):
        return f"{fid}+ba/{fid}"
    return fid


def format_kind(f) -> str:
    if _has_video(f):
        return "video+audio" if _has_audio(f) else "video only"
    return "audio only"


def fmt_size(n) -> str:
    if not n:
        return ""
    mb = n / (1024 * 1024)
    return f"{mb / 1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"


def describe_format(f, duration=None) -> dict:
    height = f.get("height")
    width = f.get("width")
    # quality reads as "2160p"; the raw WxH moves to the note column
    resolution = quality_class(width, height)
    raw = f.get("resolution") or (f"{width}x{height}"
                                  if width and height else "")
    size_bytes = f.get("filesize") or f.get("filesize_approx")
    if size_bytes:
        size = fmt_size(size_bytes)
    elif duration and f.get("tbr"):
        # sites don't always report sizes (HLS/some DASH); estimate
        # from bitrate x duration, marked as approximate
        size = "~" + fmt_size(int(f["tbr"] * 1000 / 8 * duration))
    else:
        size = ""
    return {
        "id": str(f.get("format_id", "")),
        "ext": f.get("ext") or "",
        "resolution": resolution,
        "fps": f.get("fps"),
        "note": raw,
        "size": size,
        "kind": format_kind(f),
    }


def format_label(f) -> str:
    """Short queue-row label, e.g. '720p mp4' or 'audio m4a'."""
    d = describe_format(f)
    base = d["resolution"] or ("audio" if d["kind"] == "audio only" else d["id"])
    return f"{base} {d['ext']}".strip()


# CDNs that cap EVERY connection. Measured on a Boosty post (2026-10,
# okcdn.ru, 300 Mbit/s line): one connection got 1.03-1.08 MB/s however
# it was asked — the whole file, or 2/5/10 MB ranges in a row — while 4
# parallel range requests got 10-15 MB/s, as did 4 parallel HLS
# fragments. VK and OK serve their video from the same CDN.
PARALLEL_SITES = ("boosty.to", "vk.com", "vk.ru", "vkvideo.ru", "ok.ru")
RANGE_PART = 4 * 1024 * 1024


def _parallel_site(url) -> bool:
    host = (urllib.parse.urlsplit(str(url or "")).hostname or "").lower()
    return any(host == site or host.endswith("." + site)
               for site in PARALLEL_SITES)


def _content_length(ydl, fmt):
    """The file's size when its server answers range requests (206 +
    Content-Range), else None. Costs one 1-byte request."""
    from yt_dlp.networking import Request
    headers = dict(fmt.get("http_headers") or {}, Range="bytes=0-0")
    try:
        with ydl.urlopen(Request(fmt["url"], headers=headers)) as response:
            if response.status != 206:
                return None
            total = (response.headers.get("Content-Range") or ""
                     ).rpartition("/")[2]
            return int(total) if total.isdigit() else None
    except Exception:
        return None


def _byte_range_playlist(url: str, size: int, duration) -> str:
    """An HLS media playlist whose segments are consecutive byte ranges
    of ONE file: yt-dlp's fragment downloader then fetches 4 of them at
    a time and appends them in order — byte for byte the same file."""
    starts = range(0, size, RANGE_PART)
    step = (duration or len(starts)) / len(starts)
    lines = ["#EXTM3U", "#EXT-X-VERSION:4",
             f"#EXT-X-TARGETDURATION:{math.ceil(step)}",
             "#EXT-X-MEDIA-SEQUENCE:0"]
    for start in starts:
        lines += [f"#EXTINF:{step:.3f},",
                  f"#EXT-X-BYTERANGE:{min(RANGE_PART, size - start)}@{start}",
                  url]
    lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"


def _split_into_ranges(ydl, probe):
    """Pick formats exactly as yt-dlp would, then hand every picked
    single-file format to its HLS fragment downloader as a byte-range
    playlist (`hls_media_playlist_data`, a documented info field).
    Quality and bytes stay the same; only the connections multiply.
    Returns the exact format spec to download, or None to leave the
    download as it was (no formats in the probe, nothing single-file,
    or a server that ignores Range)."""
    if probe.get("_type", "video") != "video" or not probe.get("formats"):
        return None
    try:
        chosen = ydl.process_ie_result(copy.deepcopy(probe), download=False)
    except Exception:
        return None     # the real pass reports whatever went wrong
    picked = chosen.get("requested_formats") or [chosen]
    ids = [f.get("format_id") for f in picked]
    by_id = {f.get("format_id"): f for f in probe["formats"]}
    if not ids or not all(fid in by_id for fid in ids):
        return None
    from yt_dlp.utils import determine_protocol
    split = False
    for fid in ids:
        fmt = by_id[fid]
        # extractors usually leave `protocol` for processing to fill in
        protocol = fmt.get("protocol") or determine_protocol(fmt)
        if protocol not in ("http", "https") or fmt.get("fragments"):
            continue
        size = _content_length(ydl, fmt)
        if not size or size <= RANGE_PART:
            continue
        fmt["protocol"] = "m3u8_native"
        fmt["hls_media_playlist_data"] = _byte_range_playlist(
            fmt["url"], size, probe.get("duration"))
        fmt["filesize"] = fmt.get("filesize") or size   # real progress
        split = True
    return "+".join(ids) if split else None


# Transient network failures. One rutube API timeout («Unable to
# download options JSON: Read timed out (read timeout=20.0)») failed a
# queued episode on the spot while the next one downloaded at 26 MB/s:
# yt-dlp's `retries` covers the media transfer only; the extractor's
# own requests get one shot. Errors that mean «not now» (not «never»)
# earn a few more attempts, with the card saying so.
TRANSIENT_MARKERS = (
    "timed out", "timeout", "connection reset", "connection aborted",
    "remote end closed", "incompleteread", "temporary failure",
    "getaddrinfo failed", "name or service not known",
    "network is unreachable", "eof occurred", "http error 5",
    "server error", "service unavailable", "bad gateway",
)
RETRY_WAITS = (5, 15, 30)      # seconds before attempts 2, 3 and 4


def is_transient_error(exc) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in TRANSIENT_MARKERS)


def _wait(seconds: float, cancelled=None) -> None:
    """Sleep in small steps so Cancel is honoured within 0.25 s."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if cancelled and cancelled():
            raise DownloadCancelled()
        time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))


def download(url: str, format_spec: str, dest_dir,
             progress=None, cancelled=None, cookies=None,
             retry=None) -> Path:
    """Download url at the given format spec into dest_dir. progress
    receives yt-dlp progress-hook dicts; cancelled is polled between
    chunks and aborts with DownloadCancelled; retry(attempt, attempts,
    wait_seconds, error) is told before each repeat after a transient
    network error. Returns the final file path (after any ffmpeg
    merge)."""
    import yt_dlp
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    def hook(d):
        if cancelled and cancelled():
            raise yt_dlp.utils.DownloadCancelled()
        if progress and d.get("status") in ("downloading", "finished"):
            progress(d)

    def session_opts():
        return _with_cookies(_base_opts() | {
            "format": format_spec or BEST_SPEC,
            "outtmpl": str(dest / "%(title).120B [%(id)s].%(ext)s"),
            "windowsfilenames": True,
            "overwrites": True,
            "progress_hooks": [hook],
            # the CLI's retry defaults (10) live in its option parser, NOT
            # in the library: embedded like this, yt-dlp retried NOTHING —
            # one dropped connection mid-file («9977792 bytes read, 191073
            # more expected») failed the whole item on the spot
            "retries": 10,
            "fragment_retries": 10,
            "file_access_retries": 3,
            "extractor_retries": 3,
            # HLS/DASH (rutube/VK/Boosty): per-fragment latency serializes
            # the download, worse behind VPNs — 4 parallel fragments is a
            # 2-4x win; do NOT raise it (high values can skip the m3u8
            # fixup and produce broken MP4s, yt-dlp #14302)
            "concurrent_fragment_downloads": 4,
        }, cookies)

    attempts = len(RETRY_WAITS) + 1
    for attempt in range(1, attempts + 1):
        try:
            with yt_dlp.YoutubeDL(session_opts()) as ydl:
                # extract first, process (= download) second: a bare
                # playlist/channel URL is refused before a byte is fetched
                probe = ydl.extract_info(url, download=False, process=False)
                if _is_playlist(probe):
                    raise ValueError(PLAYLIST_MESSAGE)
                if _parallel_site(url):
                    exact = _split_into_ranges(ydl, probe)
                    if exact:   # the same choice, now downloaded in parts
                        ydl.format_selector = ydl.build_format_selector(exact)
                info = ydl.process_ie_result(probe, download=True)
        except yt_dlp.utils.DownloadCancelled:
            raise DownloadCancelled() from None
        except Exception as exc:
            if attempt == attempts or not is_transient_error(exc):
                raise
            wait = RETRY_WAITS[attempt - 1]
            if retry:
                retry(attempt + 1, attempts, wait, exc)
            _wait(wait, cancelled)
        else:
            break

    requested = (info.get("requested_downloads") or [{}])[0]
    path = requested.get("filepath")
    if not path:
        raise RuntimeError("yt-dlp did not report the downloaded file path")
    return Path(path)
