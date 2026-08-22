"""Editing behaviour of the Add-URL box — every case below is a bug a
real paste session hit: text eaten while typing, links jumping to the
second row, the window collapsing after a batch."""

MANY = "\n".join(f"https://s{i}.example/v" for i in range(6))


def make_dialog(qapp):
    from wordmute_app.ui.url_dialog import AddUrlDialog
    dialog = AddUrlDialog(auto_fetch=False)
    dialog._apply_single_geometry()     # normally a singleShot(0)
    return dialog


def test_typing_a_link_by_hand_is_not_erased(qapp):
    """The box used to be rewritten to «the URLs we found» on every
    keystroke, so a half-typed link vanished at its first letter."""
    dialog = make_dialog(qapp)
    dialog.url_edit.setPlainText("https://a.com/1\nhttps://b.com/2")
    cursor = dialog.url_edit.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    dialog.url_edit.setTextCursor(cursor)
    for char in "\nhttps://c.com/3":
        dialog.url_edit.insertPlainText(char)
    assert dialog.url_edit.toPlainText() == (
        "https://a.com/1\nhttps://b.com/2\nhttps://c.com/3")


def test_editing_in_the_middle_keeps_the_caret(qapp):
    dialog = make_dialog(qapp)
    dialog.url_edit.setPlainText(
        "https://a.com/1\nhttps://b.com/2\nhttps://c.com/3")
    cursor = dialog.url_edit.textCursor()
    block = cursor.document().findBlockByNumber(1)
    cursor.setPosition(block.position() + block.length() - 1)
    dialog.url_edit.setTextCursor(cursor)
    dialog.url_edit.insertPlainText("9")
    assert dialog.url_edit.toPlainText().splitlines()[1] == \
        "https://b.com/29"
    assert dialog.url_edit.textCursor().blockNumber() == 1


def test_stray_blank_line_from_a_paste_is_dropped(qapp):
    """A link pasted under an empty first line used to sit on row 2."""
    dialog = make_dialog(qapp)
    dialog.url_edit.setPlainText("\nhttps://a.com/1\nhttps://b.com/2")
    assert dialog.url_edit.toPlainText() == \
        "https://a.com/1\nhttps://b.com/2"


def test_joined_paste_is_split_one_link_per_line(qapp):
    dialog = make_dialog(qapp)
    dialog.url_edit.setPlainText("https://a.com/1 https://b.com/2")
    assert dialog.url_edit.toPlainText() == \
        "https://a.com/1\nhttps://b.com/2"


def test_non_link_lines_survive_and_are_counted(qapp):
    dialog = make_dialog(qapp)
    dialog.url_edit.setPlainText(
        "https://a.com/1\nпросто текст\nhttps://b.com/2")
    # the line stays so it can be fixed; a warn chip explains it
    assert "просто текст" in dialog.url_edit.toPlainText()
    chips = [dialog._chips_layout.itemAt(i).widget()
             for i in range(dialog._chips_layout.count())]
    assert any(chip.property("state") == "warn" for chip in chips)
    assert dialog._multi_urls == ["https://a.com/1", "https://b.com/2"]


def test_batch_then_single_restores_the_window(qapp):
    dialog = make_dialog(qapp)
    tall = dialog.height()
    dialog.url_edit.setPlainText("https://a.com/1\nhttps://b.com/2")
    assert dialog.height() != tall          # batch sizes to its content
    dialog.url_edit.setPlainText("https://only.com/1")
    assert dialog.height() == tall          # and gives the room back


def test_input_holds_a_full_paste_without_scrolling(qapp):
    from wordmute_app.ui.url_dialog import MAX_LINES

    dialog = make_dialog(qapp)
    dialog.show()
    dialog.url_edit.setPlainText(MANY)
    qapp.processEvents()
    assert dialog.url_edit.verticalScrollBar().maximum() == 0
    dialog.url_edit.setPlainText(
        "\n".join(f"https://s{i}.example/v" for i in range(MAX_LINES + 6)))
    qapp.processEvents()
    # past the cap it scrolls, but never by more than the overflow
    hidden = dialog.url_edit.verticalScrollBar().maximum()
    assert 0 < hidden <= 6
    dialog.close()


def test_input_never_shrinks_below_the_stylesheet_minimum(qapp):
    """A fixed height under the sheet's min-height let the status label
    paint on top of the input's own border."""
    dialog = make_dialog(qapp)
    assert dialog.url_edit.height() >= \
        dialog.url_edit.minimumSizeHint().height()


def test_chips_wrap_instead_of_clipping(qapp):
    """Five hosts plus the warning used to clip the last chip mid-word."""
    dialog = make_dialog(qapp)
    dialog.show()
    dialog.url_edit.setPlainText("\n".join([
        "https://kinescope.io/embed/a", "https://www.youtube.com/watch?v=b",
        "https://vkvideo.ru/video-1", "https://rutube.ru/video/2",
        "https://boosty.to/x/posts/3", "просто текст"]))
    qapp.processEvents()
    chips = [dialog._chips_layout.itemAt(i).widget()
             for i in range(dialog._chips_layout.count())]
    assert len(chips) == 6                      # five hosts + the warning
    rows = {chip.y() for chip in chips}
    assert len(rows) > 1                        # wrapped, not squeezed
    for chip in chips:
        assert chip.width() >= chip.sizeHint().width()
    dialog.close()
