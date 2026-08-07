"""Render engine reporter events as log lines for the GUI.

Returns None for events the window handles specially (live progress)."""

from ..engine.wordmute import fmt_ts


def format_event(event: str, d: dict):
    if event == "model_load":
        if d["engine"] == "whisper":
            return (f"Loading whisper model {d['model']} on {d['device']} "
                    f"({d['compute']}) — first load takes a while...")
        return f"Loading GigaAM model {d['model']} on {d['device']}..."
    if event == "cache_hit":
        return f"Using cached {d['engine']} transcript: {d['cache']}"
    if event == "cache_saved":
        return f"Transcript cached -> {d['cache']}"
    if event == "asr_start":
        return (f"Transcribing {d['file']} with {d['engine']} "
                f"(first run is the slow part)...")
    if event == "asr_progress":
        return None  # shown in the live status label instead
    if event == "asr_progress_end":
        return None
    if event == "words_count":
        return f"{d['count']} words in transcript"
    if event == "pass_start":
        return f"— pass {d['n']}/{d['total']} ({d['engine']}) —"
    if event == "match_none":
        return ("No unwanted words found — nothing to do."
                if d["pass_n"] == 1 else
                "No unwanted words left — output is clean.")
    if event == "match_found":
        lines = [f"{len(d['intervals'])} interval(s) to mute:"]
        for s, e, t in d["intervals"]:
            lines.append(f"    {fmt_ts(s)} - {fmt_ts(e)}   {t}")
        return "\n".join(lines)
    if event == "mute_start":
        return f"Muting {d['count']} segment(s) with ffmpeg..."
    if event == "mute_done":
        return f"Written: {d['out']}"
    if event == "file_error":
        return f"Error in {d['name']}: {d['error']}"
    if event == "download_start":
        return f"Downloading ({d['label']}): {d['url']}"
    if event == "download_done":
        return f"Downloaded -> {d['path']}"
    if event == "review_saved":
        return f"Review data -> {d['path']}"
    if event == "item_output":
        return f"Output -> {d['path']}"
    return None
