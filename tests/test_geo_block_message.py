"""A TV channel's YouTube upload («Титаны 5 сезон, выпуск 5») was
blocked for Russia by the channel. yt-dlp's default web client only
said «Video unavailable» (the android/ios clients name the country
block), and the video showed up fine elsewhere, so the user read it
as a WordMute bug. The card now says what the words mean."""

import pytest

from wordmute_app.ui.worker import humanize_download_error


@pytest.fixture
def ru():
    from wordmute_app.ui import i18n
    i18n.set_language("ru")
    yield
    i18n.set_language("en")


def test_video_unavailable_explains_the_three_causes(ru):
    text = humanize_download_error(
        "ERROR: [youtube] 8qlmTsh4PcA: Video unavailable")
    assert text.startswith("[youtube] 8qlmTsh4PcA: Video unavailable — ")
    assert "удалено, скрыто или закрыто каналом для вашей страны" in text
    assert "VPN" in text


def test_country_block_names_the_cure(ru):
    text = humanize_download_error(
        "ERROR: [youtube] 8qlmTsh4PcA: The uploader has not made this "
        "video available in your country")
    assert "канал закрыл это видео для вашей страны" in text
    assert "VPN" in text


def test_other_errors_keep_their_own_hints():
    assert humanize_download_error("boom") == "boom"
    assert "yt-dlp" in humanize_download_error(
        "ERROR: unable to download video data: HTTP Error 403: Forbidden")
