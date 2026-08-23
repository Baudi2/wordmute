"""Background processing thread.

Runs the engine over a list of queue items (local files and/or URLs),
forwarding reporter and download events as Qt signals. URL items are
downloaded by a continuously rolling pump thread — one download at a
time, but the network leg never idles while the CPU/GPU leg is busy
processing. Only one worker runs at a time (the engine's reporter is
module-global)."""

import dataclasses
import re
import sys
import threading
import time
import traceback

from PySide6.QtCore import QThread, Signal

from ..core import downloader, history, review
from .i18n import tr
from ..engine import wordmute as engine


class JobCancelled(Exception):
    pass



def humanize_download_error(text: str) -> str:
    """Attach a fix to the errors users can actually act on. A bare
    «HTTP Error 403: Forbidden» made a real user conclude YouTube
    downloads were dead — the actual cure was updating yt-dlp."""
    # yt-dlp's own prefixes add nothing on a card: «ERROR: \r[download]
    # Got error: …»
    text = re.sub(r"^(ERROR:\s*)+", "", text.strip())
    text = re.sub(r"^\s*\[download\]\s*Got error:\s*", "", text).strip()
    if "403" in text and "forbidden" in text.lower():
        return (text + " — " +
                tr("this usually means yt-dlp needs updating: Models "
                   "tab → Check for updates → Update all, then restart "
                   "the app. Retrying once also sometimes helps."))
    lowered = text.lower()
    if ("more expected" in lowered or "incompleteread" in lowered
            or "connection reset" in lowered or "timed out" in lowered):
        return (text + " — " +
                tr("the connection dropped mid-download. Retry resumes "
                   "from where it stopped; if it keeps happening, pick a "
                   "lower quality."))
    return text

class _DownloadPump(threading.Thread):
    """Downloads every URL item in queue order, back to back. Each
    item's result (path or the exception) is picked up by the main
    loop when that item's turn comes, so error/cancel handling stays
    identical to an inline download — a failed download only fails
    ITS item, the pump rolls on to the next one."""

    def __init__(self, worker, jobs):
        super().__init__(daemon=True)
        self._worker = worker
        self._jobs = jobs                 # [(item index, QueueItem)]
        self._results = {}                # index -> (path, error)
        self._done = {index: threading.Event() for index, _ in jobs}

    def wait_for(self, index):
        """Block until item `index` finished downloading; returns
        (path, error) — exactly one of the two is set."""
        self._done[index].wait()
        return self._results[index]

    def run(self):
        for index, item in self._jobs:
            if self._worker._cancelled:
                self._results[index] = (None, JobCancelled())
            else:
                try:
                    path = self._worker._download(item, index)
                    self._results[index] = (path, None)
                except BaseException as exc:
                    self._results[index] = (None, exc)
            self._done[index].set()


class ProcessWorker(QThread):
    engine_event = Signal(str, dict)        # reporter + download events
    file_started = Signal(int, str)         # row index, display name
    file_finished = Signal(int, bool, str)  # row index, ok, error text
    all_finished = Signal(int, int)         # done count, total

    def __init__(self, items, wordlist, plan, options, output_dir=None,
                 download_dir=None, cookies=None, profiles=None,
                 parent=None):
        super().__init__(parent)
        self._items = list(items)
        self._wordlist = wordlist
        self._plan = plan
        self._options = options
        # per-item language profiles: profile key -> (wordlist, plan,
        # asr language or None = keep options.language). "auto" is the
        # run's main setup.
        self._profiles = {"auto": (wordlist, plan, None)}
        self._profiles.update(profiles or {})
        self._output_dir = output_dir
        self._download_dir = download_dir
        self._cookies = cookies
        self._cancelled = False
        self._records = []      # muted intervals of the current item
        self._cur_pass = 1
        self._cur_engine = plan[0][0] if plan else "whisper"
        # measure-first: wall-clock per stage, keyed by item index
        # (download can belong to a PREFETCHED item, hence per-index)
        self._timings = {}
        self._asr_t0 = None
        self._cur_index = None

    def cancel(self):
        # Takes effect at the next reporter event (per transcribed
        # segment for whisper), download chunk, or item boundary; a
        # running ffmpeg mux finishes first.
        self._cancelled = True

    def _report(self, event: str, data: dict):
        if self._cancelled:
            raise JobCancelled()
        if event == "pass_start":
            self._cur_pass = data["n"]
            self._cur_engine = data["engine"]
        elif event == "asr_start":
            self._cur_engine = data["engine"]
        elif event == "match_found":
            self._record_intervals(data["intervals"])
        elif event == "mute_done":
            self._wrote_output = True
        self._time_stage(event, data)
        self.engine_event.emit(event, data)

    def _time_stage(self, event: str, data: dict):
        timing = self._timings.get(self._cur_index)
        if timing is None:
            return
        now = time.monotonic()
        if event == "asr_start":
            self._asr_t0 = now
        elif event == "asr_progress_end" and self._asr_t0 is not None:
            timing.setdefault("passes", []).append(
                {"engine": self._cur_engine,
                 "seconds": round(now - self._asr_t0, 1)})
            self._asr_t0 = None
        elif event == "cache_hit":
            timing.setdefault("passes", []).append(
                {"engine": data.get("engine", self._cur_engine),
                 "seconds": 0.0, "cached": True})
        elif event == "mute_start":
            timing["_mute_t0"] = now
        elif event == "mute_done" and "_mute_t0" in timing:
            timing["mute"] = round(now - timing.pop("_mute_t0"), 1)

    def _finish_timing(self, index: int, item_t0: float) -> dict:
        timing = self._timings.get(index, {})
        timing.pop("_mute_t0", None)
        timing["total"] = round(time.monotonic() - item_t0, 1)
        self._asr_t0 = None
        return timing

    def _record_intervals(self, intervals):
        # a later forced pass can re-find an already-recorded interval
        # in the fresh transcript; keep one entry per (s, e)
        for s, e, text in intervals:
            if any(abs(r["s"] - s) < 0.002 and abs(r["e"] - e) < 0.002
                   for r in self._records):
                continue
            self._records.append({
                "s": s, "e": e, "text": text,
                "pass": self._cur_pass, "engine": self._cur_engine,
                "muted": True,
            })

    def _download(self, item, index: int):
        # "row" = worker item index; the UI maps it to the queue row, so
        # a prefetch download paints ITS card, not the active one
        self.engine_event.emit("download_start",
                               {"url": item.url, "label": item.format_label,
                                "row": index})
        dl_t0 = time.monotonic()
        path = downloader.download(
            item.url, item.format_spec, self._download_dir,
            cookies=self._cookies,
            progress=lambda d: self.engine_event.emit("download_progress", {
                "status": d.get("status"),
                "downloaded": d.get("downloaded_bytes"),
                "total": (d.get("total_bytes")
                          or d.get("total_bytes_estimate")),
                "speed": d.get("speed"),
                "eta": d.get("eta"),
                "row": index,
            }),
            cancelled=lambda: self._cancelled,
        )
        self.engine_event.emit("download_done",
                               {"path": str(path), "row": index})
        self._timings.setdefault(index, {})["download"] = \
            round(time.monotonic() - dl_t0, 1)
        if not item.title:
            # batch-added links skip the format fetch and have no
            # title — the downloaded file's name (yt-dlp's outtmpl)
            # is the real one; history/logs use display_name
            item.title = path.stem
        return path

    def _log_history(self, item, status: str, error: str, output=None,
                     source=None, dl_bytes: int = 0, stages=None):
        try:
            history.append_history({
                "name": item.display_name,
                # prefer the local media path (post-download for URLs) —
                # the history cleanup actions need a real file
                "source": (str(source) if source
                           else item.url if item.kind == "url"
                           else str(item.path)),
                "output": str(output) if output else "",
                "status": status,
                "error": error,
                "muted": len(self._records),
                "plan": " -> ".join(f"{e}({m})" for e, m in self._plan),
                # traffic stat («скачано за месяц» in History)
                "downloaded_bytes": int(dl_bytes),
                # measure-first: wall-clock per stage (History tooltip)
                "stage_seconds": stages or {},
            })
        except OSError:
            pass  # history must never break processing

    def _finish(self, index: int, ok: bool, message: str):
        self._finished.add(index)
        self.file_finished.emit(index, ok, message)

    def _output_path(self, path, total: int, used: set):
        out = engine.output_for(path, self._output_dir, multi=total > 1)
        if self._output_dir is not None:
            # folder mode keys the output by file name alone: two
            # «01.mp4» from different folders (Season 1 / Season 2)
            # silently overwrote each other's result and review sidecar
            base, n = out, 2
            while out in used:
                out = base.with_name(f"{path.stem} ({n}).clean{path.suffix}")
                n += 1
        used.add(out)
        return out

    def run(self):
        # the engine reporter is process-global. Route by thread: our
        # own events come here, anything another thread raises (a
        # review re-render that was already running when Start was
        # pressed) keeps flowing to whatever was installed before —
        # replacing it outright sent the re-render's progress onto the
        # active card and Cancel killed the re-render
        prev = engine._reporter
        ident = threading.get_ident()

        def reporter(event, data):
            if threading.get_ident() == ident:
                self._report(event, data)
            elif prev is not None:
                prev(event, data)

        engine.set_reporter(reporter)
        done = 0
        total = len(self._items)
        self._finished = set()
        used_outputs = set()
        pump = None
        try:
            # output_for treats an out path as a file unless it's an
            # existing directory, so a configured output folder must
            # exist up front — and an unreachable one (unplugged drive,
            # a typo) must fail visibly: an exception escaping run()
            # left the window stuck in «running» with no reason shown
            if self._output_dir is not None:
                try:
                    self._output_dir.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    raise RuntimeError(
                        tr("Output folder is not available: {}")
                        .format(exc)) from exc
            url_jobs = [(i, item) for i, item in enumerate(self._items)
                        if item.kind == "url"]
            pump = _DownloadPump(self, url_jobs) if url_jobs else None
            if pump is not None:
                pump.start()
            for i, item in enumerate(self._items):
                if self._cancelled:
                    self._finish(i, False, "cancelled")
                    continue
                self.file_started.emit(i, item.display_name)
                self._records = []
                self._wrote_output = False
                self._cur_pass = 1
                dl_bytes = 0
                item_t0 = time.monotonic()
                self._cur_index = i
                self._timings.setdefault(i, {})
                # per-item language profile (word list / plan / ASR
                # language); self._plan feeds the history record too
                wordlist, plan, language = self._profiles.get(
                    getattr(item, "lang_profile", "auto") or "auto",
                    self._profiles["auto"])
                self._plan = plan
                self._cur_engine = plan[0][0] if plan else "whisper"
                options = (dataclasses.replace(self._options,
                                               language=language)
                           if language else self._options)
                try:
                    path = item.path
                    if item.kind == "url":
                        path, error = pump.wait_for(i)
                        if error is not None:
                            raise error
                        try:
                            dl_bytes = path.stat().st_size
                        except OSError:
                            dl_bytes = 0
                    out = self._output_path(path, total, used_outputs)
                    engine.process_file(path, out, wordlist,
                                        options, plan)
                except (JobCancelled, downloader.DownloadCancelled):
                    self._log_history(item, "cancelled", "", source=path,
                                      dl_bytes=dl_bytes,
                                      stages=self._finish_timing(i, item_t0))
                    self._finish(i, False, "cancelled")
                except Exception as exc:
                    message = humanize_download_error(str(exc))
                    self._log_history(item, "error", message, source=path,
                                      dl_bytes=dl_bytes,
                                      stages=self._finish_timing(i, item_t0))
                    self._finish(i, False, message)
                else:
                    done += 1
                    # only what THIS run wrote counts: a .clean file
                    # left by an earlier run (older word list) used to
                    # be presented as this run's result when nothing
                    # matched now
                    if self._wrote_output:
                        self.engine_event.emit("item_output",
                                               {"path": str(out)})
                    if self._records:  # something was muted -> reviewable
                        try:
                            rp = review.save_review(
                                path, out, self._options.pad, self._records,
                                beep_hz=self._options.beep_hz)
                        except OSError as exc:   # the item itself is fine
                            print(f"review sidecar not written: {exc}",
                                  file=sys.stderr)
                        else:
                            self.engine_event.emit("review_saved",
                                                   {"path": str(rp)})
                    self._log_history(item, "ok", "",
                                      output=out if self._wrote_output
                                      else None,
                                      source=path, dl_bytes=dl_bytes,
                                      stages=self._finish_timing(i, item_t0))
                    self._finish(i, True, "")
        except Exception as exc:
            # a run-level failure ends every item that has no verdict yet
            # instead of escaping run() — that killed the thread before
            # the finally, with all_finished never emitted
            print(traceback.format_exc(), file=sys.stderr)
            message = humanize_download_error(str(exc))
            for i in range(total):
                if i not in self._finished:
                    self._finish(i, False, message)
        finally:
            if pump is not None:  # cancel mid-run: let it wind down
                pump.join()
            if engine._reporter is reporter:   # still ours: hand back
                engine.set_reporter(prev)
            self.all_finished.emit(done, total)
