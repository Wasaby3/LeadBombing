from __future__ import annotations

import os
import pathlib

from .common import running_mac, running_windows


def data_path() -> pathlib.Path:
    """Get package's data path."""
    if '_MEIPASS2' in os.environ:
        here = os.environ['_MEIPASS2']
    else:
        here = os.path.dirname(os.path.abspath(__file__))

    path = os.path.join(here, 'data')
    return pathlib.Path(path)


def user_path(is_config: bool = True) -> pathlib.Path:
    """Get user path depending on running OS.

    Note:
        Possible path location depending on running OS:
        * Unix: ~/.config/leadbombing or ~/.local/share/leadbombing (depends on `is_config` flag)
        * Mac: ~/Library/Application Support/leadbombing/
        * Win: C:\\Users\\%USERPROFILE%\\AppData\\Local\\leadbombing
    """
    if running_windows():
        import ctypes

        CSIDL_LOCAL_APPDATA = 28
        buf = ctypes.create_unicode_buffer(1024)
        ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_LOCAL_APPDATA, None, 0, buf)  # type: ignore
        path = buf.value
    elif running_mac():
        path = os.path.expanduser('~/Library/Application Support')
    else:
        if is_config:
            path = os.getenv('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
        else:
            path = os.getenv('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))

    path = os.path.join(path, 'leadbombing')
    return pathlib.Path(path)
