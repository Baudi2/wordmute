"""Background processing thread.

Runs the engine over a list of files, forwarding reporter events as Qt
signals. Only one worker runs at a time (the engine's reporter is
module-global)."""

from PySide6.QtCore import QThread, Signal

from ..engine import wordmute as engine


class JobCancelled(Exception):
    pass


class ProcessWorker(QThread):
    engine_event = Signal(str, dict)        # raw reporter events
    file_started = Signal(int, str)         # row index, file name
    file_finished = Signal(int, bool, str)  # row index, ok, error text
    all_finished = Signal(int, int)         # done count, total

    def __init__(self, files, wordlist, plan, options, output_dir=None,
                 parent=None):
        super().__init__(parent)
        self._files = list(files)
        self._wordlist = wordlist
        self._plan = plan
        self._options = options
        self._output_dir = output_dir
        self._cancelled = False

    def cancel(self):
        # Takes effect at the next reporter event (per transcribed
        # segment for whisper) or file boundary; a running ffmpeg mux
        # finishes first.
        self._cancelled = True

    def _report(self, event: str, data: dict):
        if self._cancelled:
            raise JobCancelled()
        self.engine_event.emit(event, data)

    def run(self):
        engine.set_reporter(self._report)
        done = 0
        total = len(self._files)
        # output_for treats an out path as a file unless it's an existing
        # directory, so a configured output folder must exist up front
        if self._output_dir is not None:
            self._output_dir.mkdir(parents=True, exist_ok=True)
        try:
            for i, inp in enumerate(self._files):
                if self._cancelled:
                    self.file_finished.emit(i, False, "cancelled")
                    continue
                self.file_started.emit(i, inp.name)
                out = engine.output_for(inp, self._output_dir, multi=total > 1)
                try:
                    engine.process_file(inp, out, self._wordlist,
                                        self._options, self._plan)
                except JobCancelled:
                    self.file_finished.emit(i, False, "cancelled")
                except Exception as exc:
                    self.file_finished.emit(i, False, str(exc))
                else:
                    done += 1
                    self.file_finished.emit(i, True, "")
        finally:
            engine.set_reporter(None)
            self.all_finished.emit(done, total)
