"""v0.4.0 quality-of-life batch: keep-awake during runs, finish
notification, initial-window-size clamp, repair/disk in Models,
download-traffic stat in History."""

from pathlib import Path

import pytest


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import gpu
    monkeypatch.setattr(gpu, "detect_gpus", lambda: [])
    from wordmute_app.ui.main_window import MainWindow
    w = MainWindow()
    yield w
    # session-long windows/tray icons accumulate and crash Qt teardown
    tray = w._tray
    if tray is not None and hasattr(tray, "deleteLater"):  # not a fake
        tray.hide()
        tray.deleteLater()
    w._tray = None
    w.deleteLater()
    qapp.processEvents()


# ------------------------------------------------------------ keep-awake
def test_keep_awake_calls_windows_api(monkeypatch):
    import ctypes
    from wordmute_app.core import power

    calls = []
    monkeypatch.setattr(ctypes.windll.kernel32, "SetThreadExecutionState",
                        calls.append, raising=False)
    power.keep_awake(True)
    power.keep_awake(False)
    assert len(calls) == 2
    on, off = (c.value for c in calls)
    assert on == power.ES_CONTINUOUS | power.ES_SYSTEM_REQUIRED
    assert off == power.ES_CONTINUOUS


def test_run_state_toggles_keep_awake(window, monkeypatch):
    from wordmute_app.core import power

    states = []
    monkeypatch.setattr(power, "keep_awake", states.append)
    window._set_running(True)
    window._set_running(False)
    assert states == [True, False]


# ---------------------------------------------------------- notification
def test_finish_notifies_when_in_background(window, monkeypatch):
    messages = []

    class FakeTray:
        def showMessage(self, title, text, *a):
            messages.append((title, text))

    window._tray = FakeTray()
    monkeypatch.setattr(window, "isActiveWindow", lambda: False)
    window._on_all_finished(2, 3)
    assert messages and messages[0][0] == "WordMute"
    assert "2/3" in messages[0][1]


def test_finish_stays_quiet_when_window_active(window, monkeypatch):
    messages = []

    class FakeTray:
        def showMessage(self, *a):
            messages.append(a)

    window._tray = FakeTray()
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window._on_all_finished(1, 1)
    assert messages == []


def test_finish_without_tray_does_not_crash(window, monkeypatch):
    window._tray = None
    monkeypatch.setattr(window, "isActiveWindow", lambda: False)
    window._on_all_finished(1, 1)  # QApplication.alert path only


# --------------------------------------------------- models tab: disk/repair
@pytest.fixture
def models_tab(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    from wordmute_app.core import gpu, models
    monkeypatch.setattr(gpu, "detect_gpus", lambda: [])
    monkeypatch.setattr(models, "whisper_model_status", lambda: [
        {"model": "large-v3", "downloaded": True,
         "size_bytes": 3_000_000_000},
        {"model": "small", "downloaded": False, "size_bytes": None}])
    monkeypatch.setattr(models, "gigaam_cache_dirs",
                        lambda: [("x", 500_000_000)])
    from wordmute_app.ui.models_tab import ModelsTab
    tab = ModelsTab()
    yield tab
    tab.shutdown()


def test_runtime_disk_usage_walks_files(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from wordmute_app.core import runtime_env

    assert runtime_env.disk_usage() == 0   # nothing installed
    sub = runtime_env.runtime_dir() / "python" / "Lib"
    sub.mkdir(parents=True)
    (sub / "a.py").write_bytes(b"x" * 100)
    (runtime_env.runtime_dir() / "b.bin").write_bytes(b"y" * 23)
    assert runtime_env.disk_usage() == 123


def test_disk_label_combines_components(models_tab):
    from wordmute_app.core.models import fmt_size

    models_tab._on_disk_result(2_000_000_000)
    legend = models_tab.disk_legend
    assert fmt_size(2_000_000_000) in legend["components"].text()
    assert fmt_size(3_000_000_000) in legend["whisper"].text()
    assert fmt_size(500_000_000) in legend["gigaam"].text()
    assert fmt_size(5_500_000_000) in models_tab.disk_total.text()
    # the stacked bar: stretch factors follow the sizes (in MB)
    bar = models_tab._disk_bar
    stretches = {key: bar.stretch(bar.indexOf(seg))
                 for key, seg in models_tab.disk_segments.items()}
    assert stretches["whisper"] > stretches["components"]
    assert stretches["components"] > stretches["gigaam"] > 0


def test_repair_deletes_runtime_and_reopens_setup(models_tab, monkeypatch,
                                                  tmp_path, confirm_yes):
    from wordmute_app.core import runtime_env

    marker = runtime_env.runtime_dir() / "python" / "python.exe"
    marker.parent.mkdir(parents=True)
    marker.touch()
    opened = []
    monkeypatch.setattr(models_tab, "_open_components",
                        lambda: opened.append(True))
    models_tab._repair_components()
    assert not runtime_env.runtime_dir().exists()
    assert opened == [True]


def test_repair_declined_keeps_runtime(models_tab, monkeypatch):
    """no_modal_dialogs answers Cancel by default."""
    from wordmute_app.core import runtime_env

    runtime_env.runtime_dir().mkdir(parents=True)
    models_tab._repair_components()
    assert runtime_env.runtime_dir().exists()


# ------------------------------------------------------------- traffic
def test_month_traffic_sums_current_month_only(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    import json
    from wordmute_app.core import history

    history.append_history({"name": "a", "downloaded_bytes": 700})
    history.append_history({"name": "b", "downloaded_bytes": 300})
    history.append_history({"name": "old-style-no-field"})
    # a record from another month is ignored
    with history.history_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps({"time": "1999-01-02T10:00:00",
                            "downloaded_bytes": 10 ** 9}) + "\n")
    assert history.month_traffic() == 1000


def test_worker_records_download_bytes(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    from wordmute_app.core import downloader, history
    from wordmute_app.core.jobs import QueueItem
    from test_worker import make_worker

    def fake_download(url, spec, dest_dir, progress=None, cancelled=None,
                      cookies=None):
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        p = dest / "video.mp4"
        p.write_bytes(b"x" * 4096)
        return p

    monkeypatch.setattr(downloader, "download", fake_download)
    worker, log = make_worker(
        [QueueItem(kind="url", url="https://e.com/v", title="V")],
        monkeypatch)
    worker._download_dir = tmp_path / "dl"
    worker.run()
    assert log["files"] == [(0, True, "")]
    records = history.load_history()
    assert records[0]["downloaded_bytes"] == 4096
    assert history.month_traffic() == 4096


def test_history_footer_shows_month_traffic(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import history
    from wordmute_app.core.models import fmt_size
    from wordmute_app.ui.history_tab import HistoryTab

    tab = HistoryTab()
    assert tab.traffic_label.text() == ""      # nothing downloaded yet
    history.append_history({"name": "v.mp4", "status": "ok", "muted": 0,
                            "plan": "whisper(s)",
                            "downloaded_bytes": 123_456_789})
    tab.refresh()
    assert fmt_size(123_456_789) in tab.traffic_label.text()


# ---------------------------------------------------------- self-update
def _fake_release(monkeypatch, tag, url="https://x/rel"):
    import io
    import urllib.request
    import json as json_mod

    def fake_urlopen(request, timeout=0):
        class R(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return R(json_mod.dumps(
            {"tag_name": tag, "html_url": url}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


def test_app_update_detected(monkeypatch):
    import wordmute_app
    from wordmute_app.core import updates

    monkeypatch.setattr(wordmute_app, "__version__", "0.3.0")
    _fake_release(monkeypatch, "v9.9.9")
    info = updates.check_app_update()
    assert info["update"] is True
    assert info["latest"] == "9.9.9"
    assert info["url"] == "https://x/rel"


def test_app_update_current_and_offline(monkeypatch):
    import urllib.request
    import wordmute_app
    from wordmute_app.core import updates

    monkeypatch.setattr(wordmute_app, "__version__", "9.9.9")
    _fake_release(monkeypatch, "v0.3.0")
    assert updates.check_app_update()["update"] is False

    def boom(*a, **k):
        raise OSError("offline")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    info = updates.check_app_update()   # never raises
    assert info["update"] is False and info["latest"] is None


def test_startup_check_notifies_via_tray(window, monkeypatch):
    messages = []

    class FakeTray:
        class _Sig:
            def connect(self, *a):
                pass

            def disconnect(self, *a):
                pass
        messageClicked = _Sig()

        def showMessage(self, title, text, *a):
            messages.append(text)

    window._tray = FakeTray()
    window._on_app_update_result(
        {"update": True, "current": "0.3.0", "latest": "0.4.0",
         "url": "https://x/rel"})
    assert messages and "0.4.0" in messages[0]
    assert window._update_url == "https://x/rel"
    # no update -> silent
    messages.clear()
    window._on_app_update_result({"update": False})
    assert messages == []


# ------------------------------------------------- setup: model choice
def test_setup_dialog_model_choice(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    from wordmute_app.core import config, gpu
    monkeypatch.setattr(gpu, "detect_gpus", lambda: [])
    from wordmute_app.ui.setup_dialog import MODEL_CHOICES, SetupDialog

    d = SetupDialog(first_run=True)
    # default reflects settings (large-v3), radios are their own group:
    # picking a model must not uncheck the CPU/GPU flavor
    assert d.model_radios["large-v3"].isChecked()
    flavor_before = d.cpu_radio.isChecked()
    d.model_radios["medium"].setChecked(True)
    assert d.cpu_radio.isChecked() == flavor_before
    assert not d.model_radios["large-v3"].isChecked()
    d.accept()
    assert config.load_settings()["model"] == "medium"

    # the wizard doubles as the component manager: same pages, so the
    # model choice exists there too and accept() persists it
    d2 = SetupDialog(first_run=False)
    assert set(d2.model_radios) == {c[0] for c in MODEL_CHOICES}
    d2.accept()
    assert config.load_settings()["model"] == "medium"


# ------------------------------------------------------ setup wizard
@pytest.fixture
def wizard(qapp, tmp_path, monkeypatch):
    """A pristine machine: nothing installed, no GPU. The UI language
    is process-global — restore it so a switch test can't leak into
    every other test in the session."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    from wordmute_app.core import gpu
    from wordmute_app.ui import i18n
    monkeypatch.setattr(gpu, "detect_gpus", lambda: [])
    before = i18n.current_language()
    from wordmute_app.ui.setup_dialog import SetupDialog
    dialog = SetupDialog(first_run=True)
    yield dialog
    i18n.set_language(before)
    dialog.deleteLater()


def test_wizard_has_eight_steps_and_navigates(wizard):
    from wordmute_app.ui.setup_dialog import STEP_KEYS

    assert list(STEP_KEYS) == ["intro", "python", "whisper", "ytdlp",
                               "ffmpeg", "gigaam", "review", "install"]
    assert wizard.pages.count() == 8
    assert wizard._step == 0
    assert not wizard.btn_back.isEnabled()          # first step

    wizard._next_clicked()
    assert wizard._step == 1 and wizard.btn_back.isEnabled()
    assert "2" in wizard.step_counter.text()   # 1-based: "Step 2 of 8"
    assert "8" in wizard.step_counter.text()

    # the rail jumps back to visited steps only
    wizard._rail_clicked(0)
    assert wizard._step == 0
    wizard._rail_clicked(5)
    assert wizard._step == 0


def test_gigaam_downloads_its_model_during_setup(wizard):
    """Must-do: opting into GigaAM downloads engine AND model now —
    nothing may be left for the first video."""
    wizard.gigaam_check.setChecked(True)
    keys = [key for key, _step in wizard._build_steps()]
    assert "gigaam" in keys and "gigaam_model" in keys
    assert keys.index("gigaam") < keys.index("gigaam_model")

    # ... and the whisper weights too, so no run stalls on a download
    assert "whisper_model" in keys

    # the page advertises the full size, not just the package
    _key, _label, _sub, mb, on = [row for row in wizard._plan()
                                  if row[0] == "gigaam"][0]
    assert on and mb >= runtime_env_gigaam_size()

    wizard.gigaam_check.setChecked(False)
    keys = [key for key, _step in wizard._build_steps()]
    assert "gigaam" not in keys and "gigaam_model" not in keys


def runtime_env_gigaam_size():
    from wordmute_app.core import runtime_env
    return runtime_env.GIGAAM_ONNX_SIZE_MB


def test_ffmpeg_is_required_not_optional(wizard):
    """Tester feedback: ffmpeg cannot be 'recommended' — without it
    nothing can be muted at all."""
    from wordmute_app.ui.setup_dialog import SetupDialog

    from PySide6.QtWidgets import QCheckBox

    page = wizard.pages.widget(STEP_INDEX("ffmpeg"))
    badges = [w.property("badge") for w in page.findChildren(object)
              if hasattr(w, "property") and w.property("badge")]
    assert "required" in badges
    assert "optional" not in badges
    assert isinstance(wizard, SetupDialog)

    # and it cannot be declined: no checkbox lives on that page, the
    # plan installs it regardless of any stale flag
    assert page.findChildren(QCheckBox) == []
    assert not wizard.ffmpeg_check.isEnabled()
    assert wizard.ffmpeg_check.isChecked()          # missing -> install
    assert "ffmpeg" in [k for k, _s in wizard._build_steps()]

    # the optional pages DO have their checkbox card
    for key in ("ytdlp", "gigaam"):
        opt_page = wizard.pages.widget(STEP_INDEX(key))
        assert opt_page.findChildren(QCheckBox)


def STEP_INDEX(key):
    from wordmute_app.ui.setup_dialog import STEP_KEYS
    return list(STEP_KEYS).index(key)


def test_wizard_language_switch_keeps_selections(wizard):
    wizard.gigaam_check.setChecked(True)
    wizard.model_radios["small"].setChecked(True)
    wizard.set_step(3)
    wizard._set_language("ru")
    # pages rebuilt, state intact
    assert wizard.gigaam_check.isChecked()
    assert wizard.model_radios["small"].isChecked()
    assert wizard._step == 3
    assert wizard.pages.count() == 8
    assert wizard.step_counter.text().startswith("Шаг")
    wizard._set_language("en")
    assert wizard.step_counter.text().startswith("Step")


def test_review_totals_track_choices(wizard):
    wizard.set_step(STEP_INDEX("review"))
    # GigaAM is on by default now — unchecking must lower the total
    assert wizard.gigaam_check.isChecked()
    with_gigaam = wizard.total_mb()
    wizard.gigaam_check.setChecked(False)
    wizard._refresh_review()
    assert wizard.total_mb() < with_gigaam
    wizard.gigaam_check.setChecked(True)
    wizard._refresh_review()
    assert wizard.total_mb() == with_gigaam
    assert "GB" in wizard.review_total.text() \
        or "ГБ" in wizard.review_total.text()


# ------------------------------------------------ background thumbnails
def test_bulk_add_defers_probing(window, tmp_path, monkeypatch):
    from wordmute_app.ui import main_window as mw

    probes = []
    monkeypatch.setattr(mw, "media_duration",
                        lambda p: probes.append(p) or 42.0)
    thumbs_called = []
    monkeypatch.setattr(mw.thumbs, "thumbnail_path",
                        lambda p: thumbs_called.append(p) or None)
    queued = []
    monkeypatch.setattr(window, "_probe_in_background", queued.append)

    files = []
    for name in ("a.mp4", "b.mp4", "c.mp4"):
        f = tmp_path / name
        f.touch()
        files.append(f)
    window._add_files(files)

    # bulk: nothing probed inline, every item handed to the worker,
    # cards exist immediately with a duration placeholder
    assert probes == [] and thumbs_called == []
    assert len(queued) == 3
    assert window.queue.count() == 3
    assert "—" in window.queue.item(0).data(mw.META_ROLE)

    # worker results stream in and fill the card
    item = queued[0]
    window._on_media_probed(item, 125.0, "")
    assert window.queue.item(0).data(mw.DURATION_ROLE) == 125.0
    assert "2:05" in window.queue.item(0).data(mw.META_ROLE)
    # a result for an item removed meanwhile is ignored quietly
    window.queue.takeItem(2)
    window._on_media_probed(queued[2], 9.0, "")


def test_single_add_probes_inline(window, tmp_path, monkeypatch):
    from wordmute_app.ui import main_window as mw

    monkeypatch.setattr(mw, "media_duration", lambda p: 60.0)
    monkeypatch.setattr(mw.thumbs, "thumbnail_path", lambda p: None)
    queued = []
    monkeypatch.setattr(window, "_probe_in_background", queued.append)

    f = tmp_path / "solo.mp4"
    f.touch()
    window._add_files([f])
    assert queued == []     # no worker involved
    assert window.queue.item(0).data(mw.DURATION_ROLE) == 60.0


# ------------------------------------------- history URL-name repair
def test_history_repairs_url_names_from_source(qapp, tmp_path,
                                               monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import history
    from wordmute_app.ui.history_tab import FILE_COL, HistoryTab

    history.append_history({
        "name": "https://www.youtube.com/watch?v=zGVyStp27bw",
        "status": "ok", "muted": 0, "plan": "whisper(s)",
        "source": r"C:\dl\How to Maintain your Car [brofphmC7GI].webm"})
    history.append_history({  # URL name and URL source: nothing better
        "name": "https://x.com/v", "status": "error", "muted": 0,
        "plan": "whisper(s)", "source": "https://x.com/v"})
    tab = HistoryTab()
    assert tab.table.item(1, FILE_COL).text() == \
        "How to Maintain your Car [brofphmC7GI]"
    assert tab.table.item(0, FILE_COL).text() == "https://x.com/v"


# ------------------------------------------------- per-item language
def test_item_language_menu_updates_meta(window, tmp_path):
    from wordmute_app.ui import main_window as mw

    f = tmp_path / "v.mp4"
    f.touch()
    window._add_files([f])
    window._set_item_lang(0, "en")
    item = window.queue.item(0).data(mw.ITEM_ROLE)
    assert item.lang_profile == "en"
    assert "EN" in window.queue.item(0).data(mw.META_ROLE)
    window._set_item_lang(0, "auto")
    assert "EN" not in window.queue.item(0).data(mw.META_ROLE)


# ------------------------------------------------------- SRT export
def test_export_srt_format_and_filtering(tmp_path):
    from wordmute_app.core.review import export_srt

    data = {"intervals": [
        {"s": 2.48, "e": 3.1, "text": "чудеса", "muted": True},
        {"s": 61.5, "e": 62.0, "text": "обожаю", "muted": False},
        {"s": 3661.25, "e": 3662.0, "text": "верю", "muted": True},
    ]}
    dest = tmp_path / "out.srt"
    assert export_srt(data, dest) == 2          # unmuted one skipped
    text = dest.read_text(encoding="utf-8")
    assert "1\n00:00:02,480 --> 00:00:03,100\nчудеса\n" in text
    assert "2\n01:01:01,250 --> 01:01:02,000\nверю\n" in text
    assert "обожаю" not in text
    assert export_srt(data, dest, muted_only=False) == 3


def test_review_dialog_srt_button(qapp, tmp_path, monkeypatch):
    from wordmute_app.core import review
    from wordmute_app.ui import review_dialog as rd

    class DummyPlayer:
        def play(self, *a): pass
        def stop(self): pass
        def dispose(self): pass

    monkeypatch.setattr(rd, "SnippetPlayer", DummyPlayer)
    src = tmp_path / "v.mp4"
    src.write_bytes(b"x")
    out = tmp_path / "v.clean.mp4"
    out.write_bytes(b"x")
    rp = review.save_review(src, out, 100, [
        {"s": 1.0, "e": 1.5, "text": "бог", "pass": 1,
         "engine": "whisper", "muted": True}])
    dialog = rd.ReviewDialog(rp)
    dest = tmp_path / "export.srt"
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(dest), "")))
    dialog._export_srt()
    assert "бог" in dest.read_text(encoding="utf-8")
    assert "export.srt" in dialog.status_label.text()
    dialog._wave_worker = None
    dialog.close()


# ---------------------------------------------------- fade-edged mutes
def test_mute_fades_edges_real_ffmpeg(tmp_path):
    """Acoustic contract: the muted core is silent, the 40 ms ramps
    carry intermediate levels, and audio outside is untouched."""
    import subprocess
    from array import array
    from wordmute_app.engine import wordmute as engine

    rate = 48000     # realistic rate: at 8 kHz the 256-sample frames
    src = tmp_path / "tone.wav"          # are as long as the ramp
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", "sine=frequency=300:duration=3",
                    "-ar", str(rate), str(src)], check=True)
    out = tmp_path / "tone.clean.wav"
    engine.mute(src, [(1.0, 1.5, "x")], out)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(out),
                          "-f", "s16le", "-ac", "1", "-ar", str(rate),
                          "-"], capture_output=True, check=True).stdout
    samples = array("h")
    samples.frombytes(raw[:len(raw) - len(raw) % 2])

    def peak(t0, t1):
        a, b = int(t0 * rate), int(t1 * rate)
        return max(abs(v) for v in samples[a:b]) / 32768.0

    loud = peak(0.2, 0.8)
    assert loud > 0.08                     # sine baseline (amp 1/8)
    assert peak(1.05, 1.45) < loud * 0.02  # core: silent
    assert peak(1.5 + 0.05, 2.8) > loud * 0.8   # after: restored
    # second half of the down-ramp: volume must be partial (≈50% at
    # its start, falling to 0) — proves a ramp exists at all
    ramp = peak(1.0 - engine.FADE_S / 2, 1.0)
    assert loud * 0.05 < ramp < loud * 0.75


# ----------------------------------------------------- UI polish (Г)
def test_toast_helper_smokes(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from PySide6.QtWidgets import QWidget
    from wordmute_app.ui.toasts import show_toast

    host = QWidget()
    host.show()
    show_toast(host, "Готово", "Лекция_01.clean.mp4")
    qapp.processEvents()
    host.hide()


def test_card_skeleton_pulse(qapp):
    from wordmute_app.ui.queue_card import QueueCard

    card = QueueCard("t", "m")
    assert card._pulse is None
    card.set_loading(True)
    assert card._pulse is not None
    card.set_loading(True)          # idempotent
    card.set_loading(False)
    assert card._pulse is None
    card.set_loading(False)         # idempotent again


def test_waveform_worker_extracts_peaks(qapp, tmp_path):
    import subprocess
    from wordmute_app.ui.waveform import BARS, WaveformWorker

    wav = tmp_path / "tone.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=6",
                    "-ar", "8000", str(wav)], check=True)
    got = []
    worker = WaveformWorker(wav, row=3, start=2.5, end=3.0)
    worker.ready.connect(lambda *a: got.append(a))
    worker.run()                    # synchronous: logic, not threading
    assert got, "no peaks emitted"
    row, peaks, f0, f1 = got[0]
    assert row == 3
    assert 0 < len(peaks) <= BARS
    assert all(0.0 <= p <= 1.0 for p in peaks)
    assert max(peaks) > 0.1         # lavfi sine amplitude is 1/8
    # the muted span sits in the middle of the ±2s window
    assert 0.3 < f0 < f1 < 0.8


def test_waveform_strip_paints(qapp):
    from wordmute_app.ui.waveform import WaveformStrip

    strip = WaveformStrip()
    strip.resize(400, 56)
    strip.set_peaks([0.1, 0.9, 0.5] * 20, 0.4, 0.6)
    strip.show()
    qapp.processEvents()
    pixmap = strip.grab()
    assert not pixmap.isNull()
    strip.clear()
    strip.hide()


# ------------------------------------------------ first-run language
def test_first_run_follows_os_language(tmp_path, monkeypatch):
    """Tester report: the Windows installer was Russian but the app's
    first-run window was English. With no settings file the OS
    language decides; a stored choice always wins."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import config

    monkeypatch.setattr(config, "detect_ui_language", lambda: "ru")
    assert config.load_settings()["ui_language"] == "ru"

    monkeypatch.setattr(config, "detect_ui_language", lambda: "en")
    assert config.load_settings()["ui_language"] == "en"

    # once saved, the user's choice is never overridden by the OS
    settings = config.load_settings()
    settings["ui_language"] = "ru"
    config.save_settings(settings)
    monkeypatch.setattr(config, "detect_ui_language", lambda: "en")
    assert config.load_settings()["ui_language"] == "ru"


def test_detect_ui_language_returns_supported_code():
    from wordmute_app.core import config
    assert config.detect_ui_language() in ("en", "ru")


# ------------------------------------------- gigaam backend routing
def test_gigaam_backend_choice(window, monkeypatch):
    """Regression: installing onnx-asr silently moved GigaAM off the
    user's GPU onto the CPU. torch must win when a CUDA GPU is
    actually usable; onnx-asr wins everywhere else."""
    import importlib.util

    installed = {"gigaam", "onnx_asr"}
    monkeypatch.setattr(
        importlib.util, "find_spec",
        lambda name: object() if name in installed else None)

    window._gpus = [object()]        # a GPU is present
    assert window._pick_gigaam_backend({"device": "cuda"}) == "torch"
    # CPU device chosen in settings -> onnx (torch on CPU is slow)
    assert window._pick_gigaam_backend({"device": "cpu"}) == "onnx"
    # no GPU detected -> onnx even with device=cuda in settings
    window._gpus = []
    assert window._pick_gigaam_backend({"device": "cuda"}) == "onnx"

    # only onnx installed -> onnx; only torch installed -> torch
    window._gpus = [object()]
    installed = {"onnx_asr"}
    assert window._pick_gigaam_backend({"device": "cuda"}) == "onnx"
    installed = {"gigaam"}
    assert window._pick_gigaam_backend({"device": "cpu"}) == "torch"

    # explicit setting always wins
    installed = {"gigaam", "onnx_asr"}
    assert window._pick_gigaam_backend(
        {"device": "cuda", "gigaam_backend": "onnx"}) == "onnx"
    assert window._pick_gigaam_backend(
        {"device": "cpu", "gigaam_backend": "torch"}) == "torch"


# ---------------------------------------------- gigaam onnx backend
def test_chars_to_words_conversion():
    """Character-level tokens (v3 ctc/rnnt): bare space separates."""
    from wordmute_app.engine.wordmute import _chars_to_words

    tokens = list("бог") + [" "] + list("из")
    times = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5]
    words = _chars_to_words(tokens, times, offset=10.0)
    assert words == [
        {"w": "бог", "s": 11.0, "e": round(10 + 1.2 + 0.08, 3)},
        {"w": "из", "s": 11.4, "e": round(10 + 1.5 + 0.08, 3)},
    ]
    assert _chars_to_words([], [], 0.0) == []
    # leading/double spaces never produce empty words
    only = _chars_to_words([" ", "а", " ", " "], [0, 1, 2, 3], 0.0)
    assert [w["w"] for w in only] == ["а"]


def test_subword_tokens_split_into_words():
    """Regression (real user report): the *_e2e_* models use
    SentencePiece subwords where a LEADING space starts a word — the
    old splitter only cut on a bare ' ' token, so whole sentences
    became a single 'word' and muting one cut the whole sentence."""
    from wordmute_app.engine.wordmute import _chars_to_words

    # shape produced by gigaam-v3-e2e-rnnt (leading-space subwords,
    # punctuation attached, occasional bare-space token)
    tokens = [" Замен", "ят", " ли", " программист", "ов", "?",
              " Этот", " вопрос", ","]
    times = [0.0, 0.2, 0.4, 0.6, 0.9, 1.0, 1.2, 1.5, 1.7]
    words = _chars_to_words(tokens, times, offset=100.0)
    assert [w["w"] for w in words] == [
        "Заменят", "ли", "программистов?", "Этот", "вопрос,"]
    assert words[0]["s"] == 100.0
    assert words[2]["s"] == 100.6          # word starts at its subword
    # every word must be short — no sentence-long spans
    assert all(w["e"] - w["s"] < 1.0 for w in words)

    # raw sentencepiece marker form is handled too
    raw = _chars_to_words(["▁мас", "совый", "▁звез", "дец", "."],
                          [0.0, 0.3, 0.6, 0.9, 1.1], offset=0.0)
    assert [w["w"] for w in raw] == ["массовый", "звездец."]

    # and the matching engine sees single words, not sentences
    from wordmute_app.engine import wordmute as engine
    exact, stems, phrases, subs = engine.parse_wordlist_lines(["звездец"])
    hits = engine.find_hits(raw, exact, stems, phrases, subs, pad_ms=100)
    assert len(hits) == 1
    assert hits[0][1] - hits[0][0] < 1.0   # ~one word, not a sentence


def test_gigaam_backend_routing(tmp_path, monkeypatch):
    import types
    from wordmute_app.engine import wordmute as engine

    monkeypatch.setattr(engine, "GIGAAM_BACKEND", "torch")  # restore
    onnx_calls = []
    monkeypatch.setattr(
        engine, "_transcribe_gigaam_onnx",
        lambda media, name: onnx_calls.append(name)
        or [{"w": "бог", "s": 1.0, "e": 1.5}])

    media = tmp_path / "v.mp4"
    media.write_bytes(b"x")
    engine.configure_gigaam_backend("onnx")
    words = engine.transcribe(media, "gigaam", "v3_rnnt", "cpu", "ru")
    assert onnx_calls == ["v3_rnnt"]
    assert words == [{"w": "бог", "s": 1.0, "e": 1.5}]
    assert (tmp_path / "v.mp4.gigaam.words.json").exists()

    # torch backend still routes to the original gigaam package path
    class FakeWord:
        text, start, end = " чудо ", 2.0, 2.5

    class FakeTorchModel:
        def transcribe_longform(self, path, word_timestamps):
            assert word_timestamps is True
            return types.SimpleNamespace(words=[FakeWord()])

    monkeypatch.setattr(engine, "get_gigaam_model",
                        lambda n, d: FakeTorchModel())
    engine.configure_gigaam_backend("torch")
    media2 = tmp_path / "v2.mp4"
    media2.write_bytes(b"x")
    words = engine.transcribe(media2, "gigaam", "v3_rnnt", "cpu", "ru")
    assert words == [{"w": "чудо", "s": 2.0, "e": 2.5}]


# -------------------------------------------------- fast whisper mode
def test_fast_mode_uses_batched_pipeline(tmp_path, monkeypatch):
    import sys
    import types
    from wordmute_app.engine import wordmute as engine

    calls = []

    class FakeSeg:
        def __init__(self):
            self.words = [types.SimpleNamespace(word=" бог",
                                                start=1.0, end=1.5)]
            self.end = 2.0

    class FakePipe:
        def __init__(self, model):
            calls.append("init")

        def transcribe(self, path, **kw):
            calls.append(("batched", kw.get("batch_size"),
                          kw.get("word_timestamps")))
            return [FakeSeg()], None

    fake = types.ModuleType("faster_whisper")
    fake.BatchedInferencePipeline = FakePipe
    monkeypatch.setitem(sys.modules, "faster_whisper", fake)
    monkeypatch.setattr(engine, "get_whisper_model",
                        lambda n, d: object())
    monkeypatch.setattr(engine, "FAST_MODE", False)  # restore on teardown

    media = tmp_path / "v.mp4"
    media.write_bytes(b"x")
    engine.configure_fast_mode(True)
    words = engine.transcribe(media, "whisper", "small", "cpu", "ru")
    assert words == [{"w": "бог", "s": 1.0, "e": 1.5}]
    assert ("batched", 4, True) in calls      # CPU batch size, words on

    # vad=False must fall back to the sequential path (batched
    # decoding requires VAD on long audio)
    calls.clear()
    sequential = []

    class FakeSeqModel:
        def transcribe(self, path, **kw):
            sequential.append(kw)
            return [FakeSeg()], None

    monkeypatch.setattr(engine, "get_whisper_model",
                        lambda n, d: FakeSeqModel())
    media2 = tmp_path / "v2.mp4"
    media2.write_bytes(b"x")
    engine.transcribe(media2, "whisper", "small", "cpu", "ru", vad=False)
    assert calls == [] and len(sequential) == 1


def test_fast_mode_settings_roundtrip(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import config
    assert config.load_settings()["fast_mode"] is False  # default off


# ------------------------------------------------------ stage timing
def test_worker_records_stage_timings(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    from wordmute_app.core import downloader, history
    from wordmute_app.core.jobs import QueueItem
    from test_worker import make_worker

    def fake_download(url, spec, dest_dir, progress=None, cancelled=None,
                      cookies=None):
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        p = dest / "video.mp4"
        p.write_bytes(b"x")
        return p

    monkeypatch.setattr(downloader, "download", fake_download)
    worker, log = make_worker(
        [QueueItem(kind="url", url="https://e.com/v", title="V")],
        monkeypatch)
    worker._download_dir = tmp_path / "dl"
    worker.run()
    assert log["files"] == [(0, True, "")]
    stages = history.load_history()[0]["stage_seconds"]
    assert stages["download"] >= 0
    assert stages["total"] >= 0
    assert isinstance(stages.get("passes", []), list)


def test_stage_tooltip_formatting(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import history
    from wordmute_app.ui.history_tab import FILE_COL, HistoryTab, _fmt_stages

    text = _fmt_stages({"download": 130, "mute": 45, "total": 660,
                        "passes": [
                            {"engine": "whisper", "seconds": 483},
                            {"engine": "gigaam", "seconds": 0.0,
                             "cached": True}]})
    assert "Whisper" in text and "GigaAM" in text
    assert _fmt_stages({}) == ""

    history.append_history({"name": "v.mp4", "status": "ok", "muted": 1,
                            "plan": "whisper(s)", "output": "C:/x/v.clean.mp4",
                            "stage_seconds": {"total": 12,
                                              "passes": [{"engine": "whisper",
                                                          "seconds": 10}]}})
    tab = HistoryTab()
    tip = tab.table.item(0, FILE_COL).toolTip()
    assert "Whisper" in tip and "C:/x/v.clean.mp4" in tip


# --------------------------------------------------- large-v3-turbo
def test_large_v3_turbo_wired_everywhere():
    from wordmute_app.core.gpu import WHISPER_VRAM_MB
    from wordmute_app.core.models import WHISPER_REPOS
    from wordmute_app.ui.settings_tab import WHISPER_MODELS
    from wordmute_app.ui.setup_dialog import MODEL_CHOICES

    assert WHISPER_REPOS["large-v3-turbo"] == \
        "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
    assert "large-v3-turbo" in WHISPER_MODELS
    assert "large-v3-turbo" in WHISPER_VRAM_MB
    assert "large-v3-turbo" in [c[0] for c in MODEL_CHOICES]
    # faster-whisper itself must resolve the name to the SAME repo,
    # or the Models tab would track a different cache than the engine
    from faster_whisper.utils import _MODELS
    assert _MODELS["large-v3-turbo"] == WHISPER_REPOS["large-v3-turbo"]


# ------------------------------------------------------- multi-URL add
def test_extract_urls_handles_paste_shapes():
    from wordmute_app.ui.url_dialog import extract_urls

    # newlines, commas, spaces — and QLineEdit's no-separator join
    assert extract_urls("https://a.com/1\nhttps://b.com/2") == \
        ["https://a.com/1", "https://b.com/2"]
    assert extract_urls("https://a.com/1, https://b.com/2") == \
        ["https://a.com/1", "https://b.com/2"]
    assert extract_urls("https://a.com/1https://b.com/2") == \
        ["https://a.com/1", "https://b.com/2"]
    # dedupe, order kept, junk around ignored
    assert extract_urls("see https://a.com/1 and https://a.com/1 !") == \
        ["https://a.com/1"]
    assert extract_urls("no links here") == []


def test_url_dialog_multi_mode(qapp):
    from wordmute_app.core import downloader
    from wordmute_app.ui.url_dialog import AddUrlDialog

    d = AddUrlDialog(auto_fetch=False)
    d.url_edit.setPlainText("https://a.com/1 https://b.com/2 https://c.com/3")
    assert d._multi_urls == ["https://a.com/1", "https://b.com/2",
                             "https://c.com/3"]
    assert "3" in d.best_button.text()
    # the quality selector appears only in batch mode, defaulting to
    # the cap (NOT best) so nobody silently pulls 4K files
    assert d.quality_row.isVisibleTo(d)
    assert d.quality() == downloader.DEFAULT_QUALITY == "1080"
    items = (d._accept_best(), d.result_items())[1]
    assert [i.url for i in items] == ["https://a.com/1",
                                      "https://b.com/2", "https://c.com/3"]
    spec, label = downloader.quality_spec("1080")
    assert all(i.format_spec == spec for i in items)
    assert all("1080" in i.format_spec for i in items)
    assert all(i.format_label == label for i in items)


def test_batch_quality_presets_and_selection(qapp):
    from wordmute_app.core import downloader
    from wordmute_app.ui.url_dialog import AddUrlDialog

    # every preset resolves, and caps fall back to "any" so a link
    # without a small enough stream still downloads
    for key, _label, spec in downloader.QUALITY_PRESETS:
        got_spec, _got_label = downloader.quality_spec(key)
        assert got_spec == spec
        if key not in ("best", "audio"):
            assert spec.endswith("/bv*+ba/b")
    assert downloader.quality_spec("nonsense")[0] == downloader.BEST_SPEC

    # a remembered choice is preselected and honoured
    d = AddUrlDialog(auto_fetch=False, quality="480")
    d.url_edit.setPlainText("https://a.com/1 https://b.com/2")
    assert d.quality() == "480"
    assert "480" in d.status.text() or "480" in d.result_items()[0].format_spec
    d.quality_combo.setCurrentIndex(d.quality_combo.findData("audio"))
    assert d.result_items()[0].format_spec == "ba/b"

    # single-link mode never shows the batch selector
    single = AddUrlDialog(auto_fetch=False)
    single.url_edit.setPlainText("https://only.com/1")
    assert not single.quality_row.isVisibleTo(single)


def test_batch_mode_input_grows_and_lists_one_per_line(qapp):
    from PySide6.QtWidgets import QDialogButtonBox
    from wordmute_app.ui.url_dialog import AddUrlDialog

    d = AddUrlDialog(auto_fetch=False)
    d._apply_single_geometry()          # normally a singleShot(0)
    single_h = d.url_edit.height()
    assert d.table.isVisibleTo(d)

    d.url_edit.setPlainText(
        "https://a.com/1 https://b.com/2 https://c.com/3")
    # pasted on one line -> rewritten one per line, no text lost
    assert d.url_edit.toPlainText() == \
        "https://a.com/1\nhttps://b.com/2\nhttps://c.com/3"
    # design 1c: the input is sized to its content instead of taking
    # the table's whole space; table + "add selected" gone
    assert not d.table.isVisibleTo(d)
    assert not d.buttons.button(QDialogButtonBox.Ok).isVisibleTo(d)
    assert d.url_edit.height() > single_h
    assert d.layout().stretch(d.layout().indexOf(d.url_edit)) == 0
    # one chip per host (with its count), and the button carries the total
    assert d.chips_row.isVisibleTo(d)
    # chips render rich text (the leading dot); the plain string is
    # kept on a property for exactly this kind of check
    chips = [d._chips_layout.itemAt(i).widget().property("chipText")
             for i in range(d._chips_layout.count())]
    assert chips == ["a.com · 1", "b.com · 1", "c.com · 1"]
    assert "3" in d.best_button.text()

    # editing the list further must not fight the caret or re-wrap
    d.url_edit.setPlainText("https://a.com/1\nhttps://b.com/2")
    assert d._multi_urls == ["https://a.com/1", "https://b.com/2"]
    assert d.url_edit.toPlainText() == \
        "https://a.com/1\nhttps://b.com/2"

    # back to one link -> single-mode layout and window size restored
    d.url_edit.setPlainText("https://only.com/1")
    assert d.table.isVisibleTo(d)
    assert d.buttons.button(QDialogButtonBox.Ok).isVisibleTo(d)
    assert d.url_edit.height() == single_h
    assert d.size() == d._single_size
    assert not d.chips_row.isVisibleTo(d)

    # back to a single link: normal mode, single result
    d2 = AddUrlDialog(auto_fetch=False)
    d2.url_edit.setPlainText("https://a.com/1 https://b.com/2")
    d2.url_edit.setPlainText("https://only.com/1")
    assert d2._multi_urls == []
    d2._use_best = True
    assert [i.url for i in d2.result_items()] == ["https://only.com/1"]


# ------------------------------------------------------------ size clamp
def test_initial_size_clamps_to_small_screens():
    from wordmute_app.ui.main_window import _initial_size

    assert _initial_size(1920, 1040) == (1100, 760)  # big screen: as-is
    assert _initial_size(911, 512) == (887, 464)     # 1366x768 @150%
    assert _initial_size(0, 0) == (1100, 760)        # unknown screen
    # the floor keeps the window usable even on absurd geometry
    assert _initial_size(300, 200) == (480, 360)


# --------------------------------------------- URL cards: title + poster
def test_url_card_gets_title_and_thumb_before_download(window, monkeypatch,
                                                       tmp_path):
    """Batch-added links must show the real video name (and poster)
    right away — a queue of bare URLs made per-video language profiles
    unusable on mixed RU/EN batches."""
    from wordmute_app.core import downloader, thumbs
    from wordmute_app.core.jobs import QueueItem
    from wordmute_app.ui.main_window import THUMB_ROLE, TITLE_ROLE

    fake_thumb = tmp_path / "poster.jpg"
    fake_thumb.write_bytes(b"jpg")
    monkeypatch.setattr(
        downloader, "probe_url",
        lambda url, cookies=None: {"title": "Настоящее имя видео",
                                   "duration": 321,
                                   "thumbnail_url": "https://x/p.jpg"})
    monkeypatch.setattr(thumbs, "remote_thumbnail_path",
                        lambda video_url, thumb_url: fake_thumb)

    item = QueueItem(kind="url", url="https://e.com/v",
                     format_spec="best", format_label="best")
    window._add_url_row(item)          # WORDMUTE_SYNC_PROBE: runs inline
    list_item = window.queue.item(0)
    assert list_item.data(TITLE_ROLE) == "Настоящее имя видео"
    assert item.title == "Настоящее имя видео"
    assert item.duration == 321
    assert list_item.data(THUMB_ROLE) == str(fake_thumb)


def test_url_probe_failure_leaves_card_as_url(window, monkeypatch):
    from wordmute_app.core import downloader
    from wordmute_app.core.jobs import QueueItem
    from wordmute_app.ui.main_window import TITLE_ROLE

    def boom(url, cookies=None):
        raise OSError("site is down")

    monkeypatch.setattr(downloader, "probe_url", boom)
    item = QueueItem(kind="url", url="https://e.com/v",
                     format_spec="best", format_label="best")
    window._add_url_row(item)
    assert window.queue.item(0).data(TITLE_ROLE) == "https://e.com/v"


def test_url_probe_never_overwrites_download_backfill(window, monkeypatch):
    """A slow probe result must not clobber the real local file name
    the finished download already wrote onto the card."""
    from wordmute_app.core.jobs import QueueItem
    from wordmute_app.ui.main_window import TITLE_ROLE

    item = QueueItem(kind="url", url="https://e.com/v",
                     format_spec="best", format_label="best")
    window._insert_row(item)
    window.queue.item(0).setData(TITLE_ROLE, "видео.mp4")  # backfilled
    window._on_url_probed(item, "Позднее имя из пробы", 100, "")
    assert window.queue.item(0).data(TITLE_ROLE) == "видео.mp4"


# ------------------------------------------------- download error hints
def test_403_error_gets_the_yt_dlp_hint():
    from wordmute_app.ui.worker import humanize_download_error

    raw = "ERROR: unable to download video data: HTTP Error 403: Forbidden"
    hinted = humanize_download_error(raw)
    assert raw in hinted
    assert "yt-dlp" in hinted
    # anything else passes through untouched
    assert humanize_download_error("boom") == "boom"


def test_pip_upgrade_streams_lines(monkeypatch, tmp_path):
    import subprocess
    from wordmute_app.core import updates

    fake_python = tmp_path / "python.exe"
    fake_python.touch()
    monkeypatch.setattr(updates, "_pip_python", lambda: str(fake_python))

    class FakeProc:
        stdout = iter(["Collecting yt-dlp\n",
                       "Downloading yt_dlp-2026.8.19-py3-none-any.whl\n",
                       "Successfully installed yt-dlp-2026.8.19\n"])

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: FakeProc())
    seen = []
    ok, tail = updates.pip_upgrade(["yt-dlp"], log=seen.append)
    assert ok
    assert seen[0] == "Collecting yt-dlp"
    assert "Successfully installed" in tail
