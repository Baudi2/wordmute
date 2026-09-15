"""No test can reach the user's real WordMute data: worker tests used to
append fake runs to %APPDATA%\\WordMute\\history.jsonl (conftest's
isolated_app_data)."""

import os
from pathlib import Path


def test_profile_dirs_are_isolated(tmp_path_factory):
    from wordmute_app.core import config, runtime_env

    base = Path(tmp_path_factory.getbasetemp()).resolve()
    for value in (os.environ["APPDATA"], os.environ["LOCALAPPDATA"],
                  config.data_dir(), runtime_env.runtime_dir()):
        assert base in Path(value).resolve().parents, value
