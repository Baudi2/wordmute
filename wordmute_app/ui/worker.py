"""Background processing thread.

Runs the engine over a list of queue items (local files and/or URLs),
forwarding reporter and download events as Qt signals. URL items are
downloaded by a continuously rolling pump thread — one download at a
time, but the network leg never idles while the CPU/GPU leg is busy
processing. Only one worker runs at a time (the engine's reporter is
module-global)."""

import threading
import time

from PySide6.QtCore import QThread, Signal

from ..core import downloader, history, review
from ..engine import wordmute as engine


class JobCancelled(Exception):
    pass


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
                 download_dir=None, cookies=None, parent=None):
        super().__init__(parent)
        self._items = list(items)
        self._wordlist = wordlist
        self._plan = plan
        self._options = options
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

    def run(self):
        engine.set_reporter(self._report)
        done = 0
        total = len(self._items)
        url_jobs = [(i, item) for i, item in enumerate(self._items)
                    if item.kind == "url"]
        pump = _DownloadPump(self, url_jobs) if url_jobs else None
        if pump is not None:
            pump.start()

        # output_for treats an out path as a file unless it's an existing
        # directory, so a configured output folder must exist up front
        if self._output_dir is not None:
            self._output_dir.mkdir(parents=True, exist_ok=True)
        try:
            for i, item in enumerate(self._items):
                if self._cancelled:
                    self.file_finished.emit(i, False, "cancelled")
                    continue
                self.file_started.emit(i, item.display_name)
                self._records = []
                self._cur_pass = 1
                dl_bytes = 0
                item_t0 = time.monotonic()
                self._cur_index = i
                self._timings.setdefault(i, {})
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
                    out = engine.output_for(path, self._output_dir,
                                            multi=total > 1)
                    engine.process_file(path, out, self._wordlist,
                                        self._options, self._plan)
                except (JobCancelled, downloader.DownloadCancelled):
                    self._log_history(item, "cancelled", "", source=path,
                                      dl_bytes=dl_bytes,
                                      stages=self._finish_timing(i, item_t0))
                    self.file_finished.emit(i, False, "cancelled")
                except Exception as exc:
                    self._log_history(item, "error", str(exc), source=path,
                                      dl_bytes=dl_bytes,
                                      stages=self._finish_timing(i, item_t0))
                    self.file_finished.emit(i, False, str(exc))
                else:
                    done += 1
                    if out.exists():  # nothing muted -> no output file
                        self.engine_event.emit("item_output",
                                               {"path": str(out)})
                    if self._records:  # something was muted -> reviewable
                        rp = review.save_review(path, out, self._options.pad,
                                                self._records,
                                                beep_hz=self._options.beep_hz)
                        self.engine_event.emit("review_saved",
                                               {"path": str(rp)})
                    self._log_history(item, "ok", "", output=out,
                                      source=path, dl_bytes=dl_bytes,
                                      stages=self._finish_timing(i, item_t0))
                    self.file_finished.emit(i, True, "")
        finally:
            if pump is not None:  # cancel mid-run: let it wind down
                pump.join()
            engine.set_reporter(None)
            self.all_finished.emit(done, total)
