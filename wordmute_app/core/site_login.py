"""Is the sign-in inside the user's cookies file still alive?

A cookies file is a SNAPSHOT of the browser. Sites keep a sign-in alive
in the browser by renewing a short-lived token; the exported file never
gets the new one. Boosty's token (the `auth` cookie) lasts about 30
days — after that yt-dlp fetches as a guest and Boosty answers «This
post requires a subscription», which a paying user reads as nonsense
(a real user's file, exported 22 Aug, held a token that died 30 Aug).
Reading the token's expiry lets the app say what is actually wrong, and
Settings can say when the file will stop working.

Read-only and offline. Cookie values never leave this module: callers
get the site and dates only."""

import json
import os
import time
import urllib.parse
from dataclasses import dataclass


def _boosty_expiry(value: str) -> float:
    # url-encoded JSON {accessToken, refreshToken, expiresAt (ms), …}
    stamp = float(json.loads(urllib.parse.unquote(value))["expiresAt"])
    return stamp / 1000 if stamp > 1e11 else stamp


# site -> (the cookie that carries the sign-in, how to read its expiry)
LOGIN_COOKIES = {"boosty.to": ("auth", _boosty_expiry)}


@dataclass(frozen=True)
class Login:
    site: str
    found: bool              # the file holds this site's sign-in cookie
    expires: float | None    # unix time it stops working; None = unknown
    exported: float          # the file's modification time

    def expired(self, now: float | None = None) -> bool:
        if not self.found or self.expires is None:
            return False
        return self.expires <= (time.time() if now is None else now)


def _on_site(host: str, site: str) -> bool:
    host = host.lstrip(".").lower()
    return host == site or host.endswith("." + site)


def site_of(url) -> str | None:
    """The known sign-in site a URL belongs to (None for the rest)."""
    host = urllib.parse.urlsplit(str(url or "")).hostname or ""
    return next((s for s in LOGIN_COOKIES if _on_site(host, s)), None)


def _rows(path):
    """(domain, name, expires, value) for each Netscape cookie line."""
    with open(path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\r\n")
            if line.startswith("#HttpOnly_"):
                line = line[len("#HttpOnly_"):]
            elif line.startswith("#") or not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) != 7:
                continue
            domain, _flag, _path, _secure, expires, name, value = parts
            try:
                expires = int(expires or 0)
            except ValueError:
                expires = 0
            yield domain, name, expires, value


def logins(path) -> list:
    """The sign-ins for known sites that the file holds — empty when
    there is no file, it is unreadable, or it has none of them."""
    try:
        exported = os.path.getmtime(path)
        rows = list(_rows(path))
    except (OSError, TypeError, ValueError):
        return []
    found = []
    for site, (name, read_expiry) in LOGIN_COOKIES.items():
        for domain, cookie, cookie_expires, value in rows:
            if cookie != name or not _on_site(domain, site):
                continue
            # whichever dies first: the cookie or the token inside it
            stamps = [cookie_expires] if cookie_expires else []
            try:
                stamps.append(read_expiry(value))
            except (ValueError, KeyError, TypeError):
                pass
            found.append(Login(site, True, min(stamps) if stamps else None,
                               exported))
            break
    return found


def login_for(path, url) -> Login | None:
    """The sign-in the file holds for url's site. found=False: the site
    needs one and the file has none. None: no file, or a site this
    module can't judge."""
    site = site_of(url)
    if not site or not path:
        return None
    try:
        exported = os.path.getmtime(path)
    except (OSError, TypeError, ValueError):
        return None
    for login in logins(path):
        if login.site == site:
            return login
    return Login(site, False, None, exported)
