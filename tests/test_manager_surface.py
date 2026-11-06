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
        settings=NS(**defaults, alter=lambda: altered.append(True)),
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
