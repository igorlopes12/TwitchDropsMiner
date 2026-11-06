import asyncio
import re
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from yarl import URL

from constants import PriorityMode, State

ROOT = Path(__file__).resolve().parent.parent
CORE = ["twitch.py", "inventory.py", "channel.py", "websocket.py", "main.py", "cache.py"]
CHAIN = re.compile(r"\.gui\.([A-Za-z_]+(?:\.[A-Za-z_]+)*)")
# objects the core keeps references to and calls methods on
ALIASED = {
    "login": ["update", "clear", "wait_for_login_press", "ask_login", "ask_enter_code"],
    "channels": ["display", "remove", "clear", "set_watching", "clear_watching", "get_selection"],
    "websockets": ["update", "remove"],
}


def core_gui_paths() -> set[tuple[str, ...]]:
    paths: set[tuple[str, ...]] = set()
    for name in CORE:
        for match in CHAIN.finditer((ROOT / name).read_text(encoding="utf8")):
            paths.add(tuple(match.group(1).split(".")))
    for attr, methods in ALIASED.items():
        for method in methods:
            paths.add((attr, method))
    return paths


def make_twitch(**settings):
    calls = []
    defaults = dict(
        priority=[], exclude=set(), priority_mode=PriorityMode.PRIORITY_ONLY, theme="system",
        onboarding_done=False, tray=False, tray_notifications=True, autostart_tray=False,
        enable_badges_emotes=False, available_drops_check=False, connection_quality=1,
        language="English", proxy=URL(), dark_mode=False,
    )
    defaults.update(settings)
    altered = []
    twitch = NS(
        settings=NS(**defaults, alter=lambda: altered.append(True), save=lambda **kw: None),
        inventory=[],
        change_state=lambda state: calls.append(state),
        close=lambda: calls.append("close"),
        state_change=lambda state: (lambda: calls.append(state)),
    )
    return twitch, calls, altered


def run(coro_fn):
    return asyncio.run(coro_fn())


def test_every_core_gui_call_exists_on_webgui():
    from webgui import GUIManager

    async def check():
        twitch, _, _ = make_twitch()
        gui = GUIManager(twitch)
        missing = []
        for path in sorted(core_gui_paths()):
            obj = gui
            try:
                for part in path:
                    obj = getattr(obj, part)
            except AttributeError:
                missing.append(".".join(path))
        gui.close_window()
        return missing

    assert run(check) == []


def test_close_sets_close_requested_and_notifies_core():
    from webgui import GUIManager

    async def check():
        twitch, calls, _ = make_twitch()
        gui = GUIManager(twitch)
        assert gui.close() == 0
        result = gui.close_requested, calls
        gui.close_window()
        return result

    closed, calls = run(check)
    assert closed is True
    assert "close" in calls


def test_switch_channel_selects_and_requests_switch():
    from webgui import GUIManager

    async def check():
        twitch, calls, _ = make_twitch()
        gui = GUIManager(twitch)
        channel = NS(id=5, name="huntshowdown", online=True, pending_online=False,
                     viewers=10, game=None)
        gui.channels.display(channel, add=True)
        gui._handlers["switch_channel"](5)
        selected = gui.channels.get_selection()
        gui.close_window()
        return selected, calls

    selected, calls = run(check)
    assert selected.name == "huntshowdown"
    assert State.CHANNEL_SWITCH in calls


def test_login_press_releases_wait():
    from webgui import GUIManager

    async def check():
        twitch, _, _ = make_twitch()
        gui = GUIManager(twitch)
        waiter = asyncio.create_task(gui.login.wait_for_login_press())
        await asyncio.sleep(0)
        gui._handlers["login_press"]()
        await asyncio.wait_for(waiter, 1)
        gui.close_window()

    run(check)


def test_minute_almost_done_without_timer():
    from webgui import GUIManager

    async def check():
        twitch, _, _ = make_twitch()
        gui = GUIManager(twitch)
        result = gui.progress.minute_almost_done()
        gui.close_window()
        return result

    assert run(check) is True


def test_initial_snapshot_has_strings_theme_and_settings():
    from webgui import GUIManager

    async def check():
        twitch, _, _ = make_twitch(priority=["Rust"], theme="dark")
        gui = GUIManager(twitch)
        snap = dict(gui._bridge.snapshot)
        gui.close_window()
        return snap

    snap = run(check)
    assert snap["strings"]["mining"]["title"]
    assert snap["theme"] == "dark"
    assert snap["settings"]["priority"] == ["Rust"]
    assert snap["settings"]["mode"] == "only"
    assert snap["settings"]["onboarding_done"] is False


def test_watching_survives_channel_list_refresh():
    from webgui import GUIManager

    async def check():
        twitch, _, _ = make_twitch()
        gui = GUIManager(twitch)
        channel = NS(id=9, name="RachtaZ", online=True, pending_online=False, viewers=4495, game=None)
        gui.channels.display(channel, add=True)
        gui.channels.set_watching(channel)
        # the core clears and refills the list while it keeps watching the same channel
        gui.channels.clear()
        gui.channels.display(channel, add=True)
        await asyncio.sleep(0.3)
        channels = gui._bridge.snapshot["channels"]
        gui.close_window()
        return channels

    channels = run(check)
    assert channels == [{"id": 9, "name": "RachtaZ", "status": "online", "viewers": 4495,
                         "game": None, "watching": True}]


def run_handler(name, *args, **settings):
    from webgui import GUIManager

    async def check():
        twitch, calls, altered = make_twitch(**settings)
        gui = GUIManager(twitch)
        gui._handlers[name](*args)
        snap = dict(gui._bridge.snapshot)
        gui.close_window()
        return twitch.settings, calls, altered, snap

    return run(check)


def test_finish_onboarding_only():
    settings, calls, altered, snap = run_handler(
        "finish_onboarding", ["Hunt: Showdown 1896", "Marvel Rivals"], "only")
    assert settings.priority == ["Hunt: Showdown 1896", "Marvel Rivals"]
    assert settings.priority_mode is PriorityMode.PRIORITY_ONLY
    assert settings.onboarding_done is True
    assert State.INVENTORY_FETCH in calls
    assert altered
    assert snap["settings"]["onboarding_done"] is True


def test_finish_onboarding_all():
    settings, calls, _, _ = run_handler("finish_onboarding", [], "all")
    assert settings.priority == []
    assert settings.priority_mode is PriorityMode.ENDING_SOONEST
    assert settings.onboarding_done is True
    assert State.INVENTORY_FETCH in calls


def test_set_games_reorders_without_finishing_onboarding():
    settings, calls, _, snap = run_handler(
        "set_games", ["B", "A"], "only", priority=["A", "B"])
    assert settings.priority == ["B", "A"]
    assert settings.onboarding_done is False
    assert snap["settings"]["priority"] == ["B", "A"]
    assert State.INVENTORY_FETCH in calls


def test_set_games_ignores_unknown_mode():
    settings, calls, _, _ = run_handler("set_games", ["A"], "bogus")
    assert settings.priority_mode is PriorityMode.PRIORITY_ONLY
    assert calls == []


def test_set_theme_persists():
    settings, _, altered, snap = run_handler("set_setting", "theme", "dark")
    assert settings.theme == "dark"
    assert snap["theme"] == "dark"
    assert altered


def test_set_invalid_theme_ignored():
    settings, _, altered, _ = run_handler("set_setting", "theme", "purple")
    assert settings.theme == "system"
    assert not altered


def test_set_mode_low_availability_reloads():
    settings, calls, _, _ = run_handler("set_setting", "mode", "low")
    assert settings.priority_mode is PriorityMode.LOW_AVBL_FIRST
    assert State.INVENTORY_FETCH in calls


def test_set_exclude_becomes_set_and_reloads():
    settings, calls, _, snap = run_handler("set_setting", "exclude", ["Rust", "Rust"])
    assert settings.exclude == {"Rust"}
    assert snap["settings"]["exclude"] == ["Rust"]
    assert State.INVENTORY_FETCH in calls


def test_set_invalid_proxy_clears_it():
    settings, _, _, _ = run_handler("set_setting", "proxy", "not a proxy")
    assert settings.proxy == URL()


def test_set_valid_proxy():
    settings, _, _, _ = run_handler("set_setting", "proxy", "http://user:pw@127.0.0.1:8080")
    assert settings.proxy == URL("http://user:pw@127.0.0.1:8080")


def test_set_unknown_setting_ignored():
    _, _, altered, _ = run_handler("set_setting", "access_token", "x")
    assert not altered


def test_set_boolean_setting():
    settings, _, _, _ = run_handler("set_setting", "tray_notifications", False)
    assert settings.tray_notifications is False
