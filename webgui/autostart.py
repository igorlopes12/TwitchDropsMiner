"""
"Start with the system" support, ported from the Tk GUI's SettingsPanel.
Windows: registry Run key. Linux: XDG autostart .desktop file. macOS: LaunchAgent plist.
"""
from __future__ import annotations

import os
import sys
import shlex
import plistlib
from pathlib import Path
from textwrap import dedent

from constants import IS_PACKAGED, LOGGING_LEVELS, SCRIPTS_PATH, SELF_PATH

AUTOSTART_NAME: str = "TwitchDropsMiner"
AUTOSTART_KEY: str = "HKCU/Software/Microsoft/Windows/CurrentVersion/Run"


def _self_path() -> str:
    # double quotes in case the path contains spaces
    return f'"{SELF_PATH.resolve()!s}"'


def _command(*, tray: bool, logging_level: int) -> str:
    flags: list[str] = []
    for lvl_idx, lvl_value in LOGGING_LEVELS.items():
        if lvl_value == logging_level:
            if lvl_idx > 0:
                flags.append(f"-{'v' * lvl_idx}")
            break
    if tray:
        flags.append("--tray")
    if not IS_PACKAGED:
        # non-packaged autostart has to go through the venv's pythonw
        return f"\"{SCRIPTS_PATH / 'pythonw'!s}\" {_self_path()} {' '.join(flags)}"
    return f"{_self_path()} {' '.join(flags)}"


def entry_file() -> Path:
    if sys.platform == "darwin":
        return Path(
            Path.home(), f"Library/LaunchAgents/com.devilxd.{AUTOSTART_NAME.lower()}.plist"
        )
    folder = Path("~/.config/autostart").expanduser()
    if (config_home := os.environ.get("XDG_CONFIG_HOME")) is not None:
        config_autostart = Path(config_home, "autostart").expanduser()
        if config_autostart.exists():
            folder = config_autostart
    return folder / f"{AUTOSTART_NAME}.desktop"


def query() -> bool:
    if sys.platform == "win32":
        from registry import RegistryKey, ValueType, ValueNotFound

        with RegistryKey(AUTOSTART_KEY, read_only=True) as key:
            try:
                value_type, value = key.get(AUTOSTART_NAME)
            except ValueNotFound:
                return False
            return value_type is ValueType.REG_SZ and _self_path() in value
    path = entry_file()
    if not path.exists():
        return False
    contents = path.read_text(encoding="utf8", errors="replace")
    if sys.platform == "darwin":
        return str(SELF_PATH.resolve()) in contents
    return _self_path() in contents


def update(enabled: bool, *, tray: bool, logging_level: int) -> None:
    if sys.platform == "win32":
        from registry import RegistryKey, ValueType

        with RegistryKey(AUTOSTART_KEY) as key:
            if enabled:
                key.set(
                    AUTOSTART_NAME, ValueType.REG_SZ,
                    _command(tray=tray, logging_level=logging_level),
                )
            else:
                key.delete(AUTOSTART_NAME, silent=True)
        return
    path = entry_file()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    command = _command(tray=tray, logging_level=logging_level)
    if sys.platform == "darwin":
        plist_data = {
            "Label": f"com.devilxd.{AUTOSTART_NAME.lower()}",
            "ProgramArguments": shlex.split(command),
            "RunAtLoad": True,
        }
        with path.open("wb") as file:
            plistlib.dump(plist_data, file)
    else:
        path.write_text(dedent(
            f"""
            [Desktop Entry]
            Type=Application
            Name=Twitch Drops Miner
            Description=Mine timed drops on Twitch
            Exec=sh -c '{command}'
            """
        ), encoding="utf8")
