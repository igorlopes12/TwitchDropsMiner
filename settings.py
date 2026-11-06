from __future__ import annotations

from typing import Any, Literal, TypedDict, TYPE_CHECKING

from yarl import URL

from utils import json_load, json_save, merge_json
from constants import SETTINGS_PATH, DEFAULT_LANG, PriorityMode

if TYPE_CHECKING:
    from main import ParsedArgs


class SettingsFile(TypedDict):
    proxy: URL
    language: str
    dark_mode: bool
    exclude: set[str]
    priority: list[str]
    autostart_tray: bool
    connection_quality: int
    tray_notifications: bool
    enable_badges_emotes: bool
    available_drops_check: bool
    priority_mode: PriorityMode
    theme: Literal["system", "light", "dark"]
    onboarding_done: bool


default_settings: SettingsFile = {
    "proxy": URL(),
    "priority": [],
    "exclude": set(),
    "dark_mode": False,
    "autostart_tray": False,
    "connection_quality": 1,
    "language": DEFAULT_LANG,
    "tray_notifications": True,
    "enable_badges_emotes": False,
    "available_drops_check": False,
    "priority_mode": PriorityMode.PRIORITY_ONLY,
    "theme": "system",
    "onboarding_done": False,
}


def migrate(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Fills in settings introduced by the web GUI, derived from older ones.
    Only missing keys are added; anything already present is kept.
    """
    if "theme" not in raw:
        raw["theme"] = "dark" if raw.get("dark_mode") else "system"
    if "onboarding_done" not in raw:
        # existing users who already picked games (or don't filter by priority) skip onboarding
        raw["onboarding_done"] = bool(raw.get("priority")) or (
            "priority_mode" in raw and raw["priority_mode"] is not PriorityMode.PRIORITY_ONLY
        )
    return raw


class Settings:
    # from args
    log: bool
    tray: bool
    dump: bool
    # args properties
    debug_ws: int
    debug_gql: int
    logging_level: int
    # from settings file
    proxy: URL
    language: str
    dark_mode: bool
    exclude: set[str]
    priority: list[str]
    autostart_tray: bool
    connection_quality: int
    tray_notifications: bool
    enable_badges_emotes: bool
    available_drops_check: bool
    priority_mode: PriorityMode
    theme: Literal["system", "light", "dark"]
    onboarding_done: bool

    PASSTHROUGH = ("_settings", "_args", "_altered")

    def __init__(self, args: ParsedArgs):
        raw: dict[str, Any] = migrate(json_load(SETTINGS_PATH, {}, merge=False))
        merge_json(raw, dict(default_settings))
        self._settings: SettingsFile = raw  # type: ignore[assignment]
        self._args: ParsedArgs = args
        self._altered: bool = False

    # default logic of reading settings is to check args first, then the settings file
    def __getattr__(self, name: str, /) -> Any:
        if name in self.PASSTHROUGH:
            # passthrough
            return getattr(super(), name)
        elif hasattr(self._args, name):
            return getattr(self._args, name)
        elif name in self._settings:
            return self._settings[name]  # type: ignore[literal-required]
        return getattr(super(), name)

    def __setattr__(self, name: str, value: Any, /) -> None:
        if name in self.PASSTHROUGH:
            # passthrough
            return super().__setattr__(name, value)
        elif name in self._settings:
            self._settings[name] = value  # type: ignore[literal-required]
            self._altered = True
            return
        raise TypeError(f"{name} is missing a custom setter")

    def __delattr__(self, name: str, /) -> None:
        raise RuntimeError("settings can't be deleted")

    def alter(self) -> None:
        self._altered = True

    def save(self, *, force: bool = False) -> None:
        if self._altered or force:
            json_save(SETTINGS_PATH, self._settings, sort=True)
