"""The version is a single source of truth: wordmute_app.__version__
feeds the installer name, the in-app update check and the release
tag. A stale number ships a release that nags every user to «update»
to what they just installed."""

import re
from pathlib import Path

import wordmute_app

ROOT = Path(__file__).resolve().parent.parent


def test_version_is_pep440():
    from packaging.version import Version
    Version(wordmute_app.__version__)      # raises on garbage


def test_changelog_top_entry_matches_version():
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    heading = re.search(r"^## (\S+)", text, re.MULTILINE)
    assert heading, "CHANGELOG.md has no '## <version>' heading"
    assert heading.group(1) == wordmute_app.__version__


def test_installer_script_has_no_version_fallback():
    iss = (ROOT / "packaging" / "installer.iss").read_text(encoding="utf-8")
    assert "#error" in iss
    assert '#define MyAppVersion "' not in iss
