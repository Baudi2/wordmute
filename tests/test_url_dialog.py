"""Add-URL dialog: format table population and result items (offscreen,
fed with fake format info — no network)."""

INFO = {
    "title": "Тестовое видео",
    "duration": 300,
    "url": "https://example.com/v",
    "formats": [
        {"format_id": "137", "ext": "mp4", "vcodec": "avc1", "acodec": "none",
         "height": 1080, "fps": 25, "filesize": 200 * 1024 * 1024},
        {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a",
         "tbr": 129},
    ],
}


def make_dialog(qapp, url="https://example.com/v"):
    from wordmute_app.ui.url_dialog import AddUrlDialog
    return AddUrlDialog(url=url)


def test_quick_add_best_without_fetch(qapp):
    d = make_dialog(qapp)
    d._accept_best()
    item = d.result_item()
    assert item.kind == "url"
    assert item.url == "https://example.com/v"
    assert item.format_spec == "bv*+ba/b"
    assert item.format_label == "best quality"
    assert item.title == ""


def test_format_table_and_selection(qapp):
    d = make_dialog(qapp)
    d._on_formats_ready(INFO)
    # synthetic "best" row + 2 formats
    assert d.table.rowCount() == 3
    assert d.table.item(0, 0).text().startswith("Best")
    assert "Тестовое видео" in d.status.text()

    # default selection = best row
    item = d.result_item()
    assert item.format_spec == "bv*+ba/b"
    assert item.title == "Тестовое видео"
    assert item.duration == 300

    d.table.selectRow(1)  # 1080p video-only row
    item = d.result_item()
    assert item.format_spec == "137+ba/137"
    assert item.format_label == "1080p mp4"

    d.table.selectRow(2)  # audio-only row
    assert d.result_item().format_spec == "140"


def test_fetch_error_shown(qapp):
    d = make_dialog(qapp)
    d._on_fetch_error("Unsupported URL")
    assert "Unsupported URL" in d.status.text()
    assert d.fetch_button.isEnabled()
