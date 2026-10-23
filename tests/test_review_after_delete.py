"""«Удалить исходник и JSON» takes the review sidecar with it. A user
processed three episodes, deleted all three sources, and then found
«Проверка» dead on the two they had not reviewed yet: the button
stayed on the card and did nothing when pressed. Now the confirmation
warns first, the card follows the files on disk, and a press without
a sidecar explains how to get it back from the Recycle Bin."""

import pytest
from PySide6.QtCore import QEvent

from wordmute_app.core import cleanup, review


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    from wordmute_app.core import gpu
    monkeypatch.setattr(gpu, "detect_gpus", lambda: [])
    from wordmute_app.ui.main_window import MainWindow
    w = MainWindow()
    yield w
    w.close()


@pytest.fixture
def finished(window, tmp_path):
    """One queue card after a successful run: source + cache, clean
    output + review sidecar, Review and Open showing."""
    from wordmute_app.ui.main_window import OUTPUT_ROLE, REVIEW_ROLE
    src = tmp_path / "ep12.mp4"
    out = tmp_path / "ep12.clean.mp4"
    src.write_bytes(b"src")
    out.write_bytes(b"out")
    (tmp_path / "ep12.mp4.gigaam.v2.words.json").write_text(
        "[]", encoding="utf-8")
    sidecar = review.save_review(src, out, 100, [
        {"s": 1.0, "e": 2.0, "text": "x", "pass": 1, "engine": "gigaam",
         "muted": True}])
    window._add_files([src])
    item = window.queue.item(0)
    item.setData(OUTPUT_ROLE, str(out))
    item.setData(REVIEW_ROLE, str(sidecar))
    card = window._card(0)
    card.set_actions(review=True, open_=True)
    return window, card, src, out, sidecar


@pytest.fixture
def recycle(monkeypatch):
    """Stand-in Recycle Bin: files really disappear, nothing is kept."""
    gone = []

    def to_bin(files):
        for f in files:
            gone.append(f.name)
            f.unlink()
    monkeypatch.setattr(cleanup, "send_to_recycle_bin", to_bin)
    return gone


@pytest.fixture
def notices(monkeypatch):
    shown = []
    monkeypatch.setattr("wordmute_app.ui.main_window.inform",
                        lambda parent, **kw: shown.append(kw))
    return shown


def test_confirmation_warns_when_the_review_would_go(tmp_path, monkeypatch):
    from wordmute_app.ui import file_delete

    out = tmp_path / "v.clean.mp4"
    sidecar = tmp_path / "v.clean.mp4.wordmute.json"
    source = tmp_path / "v.mp4"
    assert file_delete.loses_review([source, sidecar])
    # «Удалить все файлы» takes the output too: nothing left to review
    assert not file_delete.loses_review([source, sidecar, out])
    assert not file_delete.loses_review([source])

    asked = []
    monkeypatch.setattr(file_delete, "confirm",
                        lambda parent, **kw: asked.append(kw) or False)
    file_delete.confirm_and_recycle(None, [source, sidecar])
    file_delete.confirm_and_recycle(None, [source, sidecar, out])
    assert "can't be reviewed or rebuilt" in asked[0]["body"]
    assert "Recycle Bin" in asked[0]["body"]
    assert "reviewed" not in asked[1]["body"]


def test_warning_is_translated(qapp):
    from wordmute_app.ui import i18n
    from wordmute_app.ui.file_delete import confirm_and_recycle  # noqa
    i18n.set_language("ru")
    try:
        assert "Сначала проверьте видео" in i18n.tr(
            "The review file goes too: after this the video can't be "
            "reviewed or rebuilt — bringing a word back needs the "
            "original. Review it first.")
        assert i18n.tr("The review file is gone") == \
            "Файла проверки больше нет"
    finally:
        i18n.set_language("en")


def test_deleting_the_source_hides_review_keeps_open(finished, recycle,
                                                    confirm_yes):
    window, card, src, out, sidecar = finished
    window._delete_row_files(0, include_output=False)
    assert sidecar.name in recycle and src.name in recycle
    assert out.exists()
    assert card.review_button.isHidden()
    assert not card.open_button.isHidden()


def test_pressing_review_without_a_sidecar_explains(finished, notices):
    window, card, src, out, sidecar = finished
    sidecar.unlink()              # e.g. deleted from History or Explorer
    window._card_review(0)
    assert notices and notices[0]["title"] == "The review file is gone"
    assert "Recycle Bin" in notices[0]["body"]
    assert notices[0]["files"] == [sidecar.name]
    assert card.review_button.isHidden()
    # double-click says the same, not «Nothing to review yet»
    window._on_row_double_clicked(window.queue.item(0))
    assert notices[1]["title"] == "The review file is gone"


def test_restore_from_the_bin_brings_review_back(finished, recycle,
                                                 confirm_yes, monkeypatch):
    window, card, src, out, sidecar = finished
    window._delete_row_files(0, include_output=False)
    assert card.review_button.isHidden()
    # «Восстановить» in the Recycle Bin, then back to the app window
    src.write_bytes(b"src")
    review.save_review(src, out, 100, [
        {"s": 1.0, "e": 2.0, "text": "x", "pass": 1, "engine": "gigaam",
         "muted": True}])
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.changeEvent(QEvent(QEvent.ActivationChange))
    assert not card.review_button.isHidden()


def test_history_deletion_shows_up_on_the_queue_tab(finished):
    window, card, src, out, sidecar = finished
    window.tabs.setCurrentWidget(window.history_tab)
    sidecar.unlink()
    out.unlink()
    window.tabs.setCurrentWidget(window._queue_page)
    assert card.review_button.isHidden()
    assert card.open_button.isHidden()


def test_buttons_are_left_alone_during_a_run(finished):
    window, card, src, out, sidecar = finished
    sidecar.unlink()
    window._worker = object()     # a run is in progress
    try:
        window._sync_card_files()
        assert not card.review_button.isHidden()
    finally:
        window._worker = None


def test_long_confirmation_is_not_clipped(qapp):
    """The warning made the body four lines long: the dialog measured
    it before the sheet's font and cut it at the top and bottom; a
    one-file box also lost its descenders. Checked under the real
    theme, in Russian (the longer language)."""
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QLabel
    from wordmute_app.ui import i18n
    from wordmute_app.ui.dialogs import ConfirmDialog
    from wordmute_app.ui.theme import apply_theme

    apply_theme(qapp, "dark")
    i18n.set_language("ru")
    try:
        body = i18n.tr(
            "The review file goes too: after this the video can't be "
            "reviewed or rebuilt — bringing a word back needs the "
            "original. Review it first.") + "\n\n" + i18n.tr(
            "They can be restored from the Recycle Bin.")
        name = ("Лучше звоните Солу  – 6 сезон 12 серия ⧸ Better Call "
                "Saul [a29584d3bd03fbd6ecfc8024e04afb24]")
        for files in ([name + ".mp4"], [f"{name} {i}.mp4" for i in range(9)]):
            d = ConfirmDialog(None, title="?", body=body, files=files,
                              ok_text="ok")
            d.show()
            qapp.processEvents()
            label = d.findChild(QLabel, "wm_confirm_body")
            assert label.height() >= label.heightForWidth(label.width())
            listing = d._files_widget
            rows = min(len(files), 6)
            needed = (rows * QFontMetrics(listing.font()).lineSpacing()
                      + 2 * listing.document().documentMargin())
            assert listing.viewport().height() >= needed
            # and no half-visible extra row below the last whole one
            assert listing.viewport().height() < needed + QFontMetrics(
                listing.font()).lineSpacing()
            d.close()
    finally:
        i18n.set_language("en")
