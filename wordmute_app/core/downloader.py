"""yt-dlp integration: format listing and downloading with progress.

Uses yt-dlp's Python API rather than shelling out, so format data and
download progress arrive as callbacks. yt_dlp is imported lazily to
keep app startup fast."""

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

    The file is loaded into a jar rather than handed over as
    `cookiefile`: yt-dlp rewrites a cookiefile on every session close,
    and the probe, the format fetch and the download pump run
    concurrently — one session's save truncated the jar another had
    just loaded, and the user's export got corrupted."""
    if cookies:
        try:
            from yt_dlp.cookies import YoutubeDLCookieJar
            jar = YoutubeDLCookieJar(str(cookies))
            jar.load()
            opts["cookiejar"] = jar
        except Exception:
            opts["cookiefile"] = str(cookies)   # let yt-dlp report it
    return opts


def list_formats(url: str, cookies=None) -> dict:
    import yt_dlp
    with yt_dlp.YoutubeDL(_with_cookies(_base_opts(), cookies)) as ydl:
        info = ydl.extract_info(url, download=False)
    if _is_playlist(info):
        raise ValueError(PLAYLIST_MESSAGE)
    formats = [f for f in info.get("formats") or [] if _is_media(f)]
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
    resolution = f"{height}p" if height else ""
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


def download(url: str, format_spec: str, dest_dir,
             progress=None, cancelled=None, cookies=None) -> Path:
    """Download url at the given format spec into dest_dir. progress
    receives yt-dlp progress-hook dicts; cancelled is polled between
    chunks and aborts with DownloadCancelled. Returns the final file
    path (after any ffmpeg merge)."""
    import yt_dlp
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    def hook(d):
        if cancelled and cancelled():
            raise yt_dlp.utils.DownloadCancelled()
        if progress and d.get("status") in ("downloading", "finished"):
            progress(d)

    opts = _with_cookies(_base_opts() | {
        "format": format_spec or BEST_SPEC,
        "outtmpl": str(dest / "%(title).120B [%(id)s].%(ext)s"),
        "windowsfilenames": True,
        "overwrites": True,
        "progress_hooks": [hook],
        # HLS/DASH (rutube/VK/Boosty): per-fragment latency serializes
        # the download, worse behind VPNs — 4 parallel fragments is a
        # 2-4x win; do NOT raise it (high values can skip the m3u8
        # fixup and produce broken MP4s, yt-dlp #14302)
        "concurrent_fragment_downloads": 4,
    }, cookies)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            # extract first, process (= download) second: a bare
            # playlist/channel URL is refused before a byte is fetched
            probe = ydl.extract_info(url, download=False, process=False)
            if _is_playlist(probe):
                raise ValueError(PLAYLIST_MESSAGE)
            info = ydl.process_ie_result(probe, download=True)
    except yt_dlp.utils.DownloadCancelled:
        raise DownloadCancelled() from None

    requested = (info.get("requested_downloads") or [{}])[0]
    path = requested.get("filepath")
    if not path:
        raise RuntimeError("yt-dlp did not report the downloaded file path")
    return Path(path)
