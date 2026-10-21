"""The sign-in inside the cookies file: a paying Boosty user got «This
post requires a subscription» because the token in their exported file
(22 Aug) had died on 30 Aug. The app now reads that date offline and
says what to do — on the failed item, in Add URL and in Settings."""

import json
import time
import urllib.parse

import pytest

from wordmute_app.core import site_login

DAY = 86400
BOOSTY_ERROR = (
    "ERROR: [Boosty] This post requires a subscription. Use "
    "--cookies-from-browser or --cookies for the authentication. See  "
    "https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-"
    "yt-dlp  for how to manually pass cookies")
POST = "https://boosty.to/androidbroadcast/posts/d6e196b4-ed16"


def auth_value(token_expires: float) -> str:
    return urllib.parse.quote(json.dumps({
        "accessToken": "secret-access", "refreshToken": "secret-refresh",
        "expiresAt": int(token_expires * 1000), "isNewUser": False}))


def cookie_file(tmp_path, token_expires=None, cookie_expires=None,
                auth=None, name="c.txt", http_only=False):
    """A Netscape export like the browser extensions write."""
    lines = ["# Netscape HTTP Cookie File",
             ".boosty.to\tTRUE\t/\tFALSE\t1830000000\t_ga\tGA1.1.2",
             ".youtube.com\tTRUE\t/\tTRUE\t1830000000\tSID\tyt"]
    if auth is None and token_expires is not None:
        auth = auth_value(token_expires)
    if auth is not None:
        prefix = "#HttpOnly_" if http_only else ""
        lines.append(f"{prefix}.boosty.to\tTRUE\t/\tFALSE\t"
                     f"{int(cookie_expires or 0)}\tauth\t{auth}")
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_site_of_matches_the_site_and_its_subdomains():
    assert site_login.site_of(POST) == "boosty.to"
    assert site_login.site_of("https://www.boosty.to/x") == "boosty.to"
    assert site_login.site_of("https://notboosty.to/x") is None
    assert site_login.site_of("https://youtube.com/watch?v=1") is None
    assert site_login.site_of(None) is None


def test_expired_token_is_found_with_its_date(tmp_path):
    now = time.time()
    path = cookie_file(tmp_path, token_expires=now - 5 * DAY,
                       cookie_expires=now + 30 * DAY, http_only=True)
    [login] = site_login.logins(path)
    assert login.site == "boosty.to" and login.found
    assert login.expires == pytest.approx(now - 5 * DAY, abs=1)
    assert login.expired()
    assert site_login.login_for(path, POST) == login


def test_whichever_dies_first_cookie_or_token(tmp_path):
    now = time.time()
    path = cookie_file(tmp_path, token_expires=now + 20 * DAY,
                       cookie_expires=now + 3 * DAY)
    [login] = site_login.logins(path)
    assert login.expires == pytest.approx(now + 3 * DAY, abs=1)
    assert not login.expired()
    assert login.expired(now=now + 4 * DAY)


def test_unreadable_token_falls_back_to_the_cookie_date(tmp_path):
    now = time.time()
    [login] = site_login.logins(
        cookie_file(tmp_path, auth="not-json", cookie_expires=now + DAY))
    assert login.expires == pytest.approx(now + DAY, abs=1)
    [session] = site_login.logins(
        cookie_file(tmp_path, auth="not-json", name="s.txt"))
    assert session.found and session.expires is None
    assert not session.expired()


def test_file_without_a_boosty_sign_in(tmp_path):
    path = cookie_file(tmp_path)              # trackers only, no auth
    assert site_login.logins(path) == []
    login = site_login.login_for(path, POST)
    assert login.site == "boosty.to" and not login.found
    assert not login.expired()
    # sites this module can't judge, or no file: nothing to say
    assert site_login.login_for(path, "https://youtube.com/w") is None
    assert site_login.login_for(tmp_path / "missing.txt", POST) is None
    assert site_login.logins(tmp_path / "missing.txt") == []
    assert site_login.login_for("", POST) is None


@pytest.fixture
def ru():
    from wordmute_app.ui import i18n
    i18n.set_language("ru")
    yield
    i18n.set_language("en")


def test_error_names_the_expired_sign_in(qapp, tmp_path, ru):
    from wordmute_app.ui.worker import humanize_download_error

    expired = time.mktime((2026, 8, 30, 17, 22, 0, 0, 0, -1))
    path = cookie_file(tmp_path, token_expires=expired)
    text = humanize_download_error(BOOSTY_ERROR, url=POST, cookies=str(path))
    assert text.startswith("[Boosty] This post requires a subscription — ")
    assert "вход на boosty.to в файле cookies истёк 30 августа 2026" in text
    assert "выберите новый в Настройках" in text
    # yt-dlp's command-line advice is gone, and no token leaks out
    assert "--cookies" not in text and "github.com" not in text
    assert "secret" not in text


def test_error_for_each_other_cookie_state(qapp, tmp_path, ru):
    from wordmute_app.ui.worker import humanize_download_error

    def hint(cookies):
        return humanize_download_error(BOOSTY_ERROR, url=POST,
                                       cookies=cookies)

    assert "нужен вход на сайт" in hint(None)
    assert "Файл cookies" in hint(None)
    missing = str(tmp_path / "gone.txt")
    assert f"файл cookies не найден: {missing}" in hint(missing)
    no_auth = cookie_file(tmp_path, name="trackers.txt")
    assert "нет входа на boosty.to" in hint(str(no_auth))
    valid = cookie_file(tmp_path, token_expires=time.time() + 20 * DAY,
                        name="fresh.txt")
    assert "сайт не принял вход" in hint(str(valid))
    # another site that wants a sign-in: the generic advice
    yt = humanize_download_error(
        "ERROR: [youtube] abc: Sign in to confirm you're not a bot. Use "
        "--cookies-from-browser or --cookies for the authentication. See  "
        "https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to"
        "-yt-dlp  for how to manually pass cookies",
        url="https://youtube.com/watch?v=abc", cookies=str(valid))
    assert yt.startswith("[youtube] abc: Sign in to confirm you're not a bot")
    assert "сайт не принял вход" in yt and "--cookies" not in yt


def test_add_url_dialog_explains_the_expired_sign_in(qapp, tmp_path, ru):
    from wordmute_app.ui.url_dialog import AddUrlDialog

    path = cookie_file(tmp_path, token_expires=time.time() - DAY)
    d = AddUrlDialog(url=POST, cookies=str(path), auto_fetch=False)
    d._on_fetch_error(BOOSTY_ERROR, POST)
    status = d.status.text()
    assert status.startswith("Не удалось получить форматы: [Boosty]")
    assert "вход на boosty.to в файле cookies истёк" in status
    assert "--cookies" not in status


def test_settings_says_how_long_the_sign_in_lasts(qapp, tmp_path, ru,
                                                  monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import config
    from wordmute_app.ui.settings_tab import SettingsTab

    tab = SettingsTab(config.load_settings())
    assert tab.cookies_status.isHidden()               # no file chosen

    fresh = cookie_file(tmp_path, name="fresh.txt",
                        token_expires=time.mktime(
                            (2099, 11, 20, 13, 55, 0, 0, 0, -1)))
    tab.cookies_edit.setText(str(fresh))
    assert not tab.cookies_status.isHidden()
    assert tab.cookies_status.text() == \
        "Вход на boosty.to в этом файле действует до 20 ноября 2099."
    assert tab.cookies_status.property("state") == "ok"

    stale = cookie_file(tmp_path, name="stale.txt",
                        token_expires=time.mktime(
                            (2026, 8, 30, 17, 22, 0, 0, 0, -1)))
    tab.cookies_edit.setText(str(stale))
    assert tab.cookies_status.text() == ("Вход на boosty.to в этом файле "
                                         "истёк 30 августа 2026 — "
                                         "экспортируйте cookies заново.")
    assert tab.cookies_status.property("state") == "warn"

    tab.cookies_edit.setText(str(tmp_path / "nope.txt"))
    assert tab.cookies_status.text() == "Файл не найден."
    assert tab.cookies_status.property("state") == "warn"

    # cookies for sites without a known sign-in: nothing to claim
    tab.cookies_edit.setText(str(cookie_file(tmp_path, name="yt.txt")))
    assert tab.cookies_status.isHidden()
    tab.cookies_edit.setText("")
    assert tab.cookies_status.isHidden()
