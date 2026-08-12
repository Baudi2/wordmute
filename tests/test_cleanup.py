"""File cleanup: resolving the source, collecting related files, and
the delete actions in the history tab. The Recycle Bin call itself is
stubbed — tests must not touch the real bin."""

import pytest

from wordmute_app.core import cleanup, review


@pytest.fixture
def processed(tmp_path):
    """A realistic on-disk aftermath: source + caches, clean + sidecar."""
    src = tmp_path / "v.mp4"
    out = tmp_path / "v.clean.mp4"
    src.write_bytes(b"src")
    out.write_bytes(b"out")
    (tmp_path / "v.mp4.words.json").write_text("[]", encoding="utf-8")
    (tmp_path / "v.mp4.gigaam.words.json").write_text("[]", encoding="utf-8")
    review.save_review(src, out, 100, [
        {"s": 1.0, "e": 2.0, "text": "x", "pass": 1,
         "engine": "whisper", "muted": True}])
    return src, out


def test_resolve_source_prefers_sidecar(processed, tmp_path):
    src, out = processed
    # even with a wrong fallback, the sidecar wins
    assert cleanup.resolve_source(output=out,
                                  fallback=tmp_path / "nope.mp4") == src


def test_resolve_source_fallback_without_sidecar(tmp_path):
    assert cleanup.resolve_source(output=tmp_path / "no.clean.mp4",
                                  fallback=tmp_path / "no.mp4") \
        == tmp_path / "no.mp4"
    assert cleanup.resolve_source() is None


def test_related_files_keep_output(processed):
    src, out = processed
    files = cleanup.related_files(source=src, output=out,
                                  include_output=False)
    names = {f.name for f in files}
    assert names == {"v.mp4", "v.mp4.words.json",
                     "v.mp4.gigaam.words.json", "v.clean.mp4.wordmute.json"}


def test_related_files_delete_all(processed):
    src, out = processed
    files = cleanup.related_files(source=src, output=out,
                                  include_output=True)
    assert {f.name for f in files} == {
        "v.mp4", "v.mp4.words.json", "v.mp4.gigaam.words.json",
        "v.clean.mp4.wordmute.json", "v.clean.mp4"}


def test_source_protected_when_no_clean_copy(tmp_path):
    """No matches -> no .clean file -> the source is the user's ONLY
    copy: «удалить исходник» must degrade to JSONs only; «удалить все»
    may still take the source."""
    src = tmp_path / "v.mp4"
    src.write_bytes(b"src")
    (tmp_path / "v.mp4.words.json").write_text("[]", encoding="utf-8")
    out = tmp_path / "v.clean.mp4"          # recorded but NEVER created

    keep = cleanup.related_files(source=src, output=out,
                                 include_output=False)
    assert {f.name for f in keep} == {"v.mp4.words.json"}

    everything = cleanup.related_files(source=src, output=out,
                                       include_output=True)
    assert {f.name for f in everything} == {"v.mp4", "v.mp4.words.json"}

    # once a clean copy exists, keep-mode includes the source again
    out.write_bytes(b"out")
    keep = cleanup.related_files(source=src, output=out,
                                 include_output=False)
    assert "v.mp4" in {f.name for f in keep}


def test_related_files_skips_missing(tmp_path):
    # nothing on disk -> nothing to delete, menu stays disabled
    assert cleanup.related_files(source=tmp_path / "gone.mp4",
                                 output=tmp_path / "gone.clean.mp4",
                                 include_output=True) == []


def test_history_tab_delete_actions(qapp, tmp_path, monkeypatch, processed):
    src, out = processed
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    from wordmute_app.core import history
    from wordmute_app.ui import file_delete, history_tab

    history.append_history({"name": "v.mp4", "status": "ok", "muted": 1,
                            "plan": "whisper(small)", "source": str(src),
                            "output": str(out)})
    tab = history_tab.HistoryTab()

    # both variants see the right file sets before deleting
    assert {f.name for f in tab._files_for_row(0, False)} == {
        "v.mp4", "v.mp4.words.json", "v.mp4.gigaam.words.json",
        "v.clean.mp4.wordmute.json"}
    assert "v.clean.mp4" in {f.name for f in tab._files_for_row(0, True)}

    recycled = []
    monkeypatch.setattr(cleanup, "send_to_recycle_bin", recycled.extend)
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    tab._delete_row_files(0, include_output=False)
    assert {f.name for f in recycled} == {
        "v.mp4", "v.mp4.words.json", "v.mp4.gigaam.words.json",
        "v.clean.mp4.wordmute.json"}
    assert "v.clean.mp4" not in {f.name for f in recycled}


def test_files_glyph_states(tmp_path):
    from wordmute_app.ui.history_tab import _files_glyph

    src = tmp_path / "v.mp4"
    out = tmp_path / "v.clean.mp4"
    src.write_bytes(b"s")
    out.write_bytes(b"o")
    rec = {"source": str(src), "output": str(out)}
    assert _files_glyph(rec) == ("●", "Files on disk")
    src.unlink()
    assert _files_glyph(rec) == ("◐", "Source deleted")
    out.unlink()
    assert _files_glyph(rec) == ("○", "Files deleted")
    src.write_bytes(b"s")
    assert _files_glyph(rec) == ("◐", "Output deleted")
    # old records: URL source, no output -> nothing tracked, no glyph
    assert _files_glyph({"source": "https://x/v", "output": ""}) == ("", "")


def test_history_tab_shows_files_glyph(qapp, tmp_path, monkeypatch,
                                       processed):
    src, out = processed
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    from wordmute_app.core import history
    from wordmute_app.ui.history_tab import FILES_COL, HistoryTab

    history.append_history({"name": "v.mp4", "status": "ok", "muted": 1,
                            "plan": "whisper(small)", "source": str(src),
                            "output": str(out)})
    tab = HistoryTab()
    assert tab.table.item(0, FILES_COL).text() == "●"
    src.unlink()
    tab.refresh()
    assert tab.table.item(0, FILES_COL).text() == "◐"


def test_confirm_declined_deletes_nothing(qapp, monkeypatch, processed):
    src, out = processed
    from wordmute_app.ui import file_delete
    from PySide6.QtWidgets import QMessageBox

    recycled = []
    monkeypatch.setattr(cleanup, "send_to_recycle_bin", recycled.extend)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.No)
    assert not file_delete.confirm_and_recycle(None, [src])
    assert recycled == []
