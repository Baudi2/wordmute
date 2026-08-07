"""Background processing thread.

Runs the engine over a list of queue items (local files and/or URLs),
forwarding reporter and download events as Qt signals. URL items are
downloaded first, then processed like local files. Only one worker runs
at a time (the engine's reporter is module-global)."""

from PySide6.QtCore import QThread, Signal

from ..core import downloader, review
from ..engine import wordmute as engine


class JobCancelled(Exception):
    pass


class ProcessWorker(QThread):
    engine_event = Signal(str, dict)        # reporter + download events
    file_started = Signal(int, str)         # row index, display name
    file_finished = Signal(int, bool, str)  # row index, ok, error text
    all_finished = Signal(int, int)         # done count, total

    def __init__(self, items, wordlist, plan, options, output_dir=None,
                 download_dir=None, parent=None):
        super().__init__(parent)
        self._items = list(items)
        self._wordlist = wordlist
        self._plan = plan
        self._options = options
        self._output_dir = output_dir
        self._download_dir = download_dir
        self._cancelled = False
        self._records = []      # muted intervals of the current item
        self._cur_pass = 1
        self._cur_engine = plan[0][0] if plan else "whisper"

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
        self.engine_event.emit(event, data)

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

    def _download(self, item):
        self.engine_event.emit("download_start",
                               {"url": item.url, "label": item.format_label})
        path = downloader.download(
            item.url, item.format_spec, self._download_dir,
            progress=lambda d: self.engine_event.emit("download_progress", {
                "status": d.get("status"),
                "downloaded": d.get("downloaded_bytes"),
                "total": (d.get("total_bytes")
                          or d.get("total_bytes_estimate")),
                "speed": d.get("speed"),
                "eta": d.get("eta"),
            }),
            cancelled=lambda: self._cancelled,
        )
        self.engine_event.emit("download_done", {"path": str(path)})
        return path

    def run(self):
        engine.set_reporter(self._report)
        done = 0
        total = len(self._items)
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
                try:
                    path = item.path
                    if item.kind == "url":
                        path = self._download(item)
                    out = engine.output_for(path, self._output_dir,
                                            multi=total > 1)
                    engine.process_file(path, out, self._wordlist,
                                        self._options, self._plan)
                except (JobCancelled, downloader.DownloadCancelled):
                    self.file_finished.emit(i, False, "cancelled")
                except Exception as exc:
                    self.file_finished.emit(i, False, str(exc))
                else:
                    done += 1
                    if self._records:  # something was muted -> reviewable
                        rp = review.save_review(path, out, self._options.pad,
                                                self._records)
                        self.engine_event.emit("review_saved",
                                               {"path": str(rp)})
                    self.file_finished.emit(i, True, "")
        finally:
            engine.set_reporter(None)
            self.all_finished.emit(done, total)
