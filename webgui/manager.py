"""
GUIManager for the web GUI.

Implements the same surface the core (twitch.py, inventory.py, channel.py, websocket.py,
main.py, cache.py) calls on gui.GUIManager, translating each call into a bridge event.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from collections import abc
from typing import Any, NoReturn, TypeVar, TYPE_CHECKING

from yarl import URL

from translate import _
from exceptions import ExitRequest, MinerException
from utils import task_wrapper, webopen
from constants import MAX_WEBSOCKETS, OUTPUT_FORMATTER, WS_TOPICS_LIMIT, PriorityMode, State
from webgui import app
from webgui.bridge import Bridge
from webgui.tray import TrayIcon
from webgui.views import campaign_view, channel_view, drop_view, game_option

if TYPE_CHECKING:
    from twitch import Twitch
    from channel import Channel
    from utils import Game
    from inventory import DropsCampaign, TimedDrop


_T = TypeVar("_T")
MODE_NAMES: dict[PriorityMode, str] = {
    PriorityMode.PRIORITY_ONLY: "only",
    PriorityMode.ENDING_SOONEST: "all",
    PriorityMode.LOW_AVBL_FIRST: "low",
}
MODES_BY_NAME: dict[str, PriorityMode] = {name: mode for mode, name in MODE_NAMES.items()}
logger = logging.getLogger("TwitchDrops")


class _OutputHandler(logging.Handler):
    def __init__(self, manager: GUIManager):
        super().__init__()
        self._manager = manager

    def emit(self, record: logging.LogRecord) -> None:
        self._manager.print(self.format(record))


class StatusBar:
    def __init__(self, manager: GUIManager):
        self._manager = manager

    def update(self, text: str) -> None:
        self._manager._bridge.emit("status", text)

    def clear(self) -> None:
        self._manager._bridge.emit("status", "")


class WebsocketStatus:
    def __init__(self, manager: GUIManager):
        self._manager = manager
        self._items: dict[int, dict[str, Any]] = {}

    def update(self, idx: int, status: str | None = None, topics: int | None = None) -> None:
        if status is None and topics is None:
            raise TypeError("You need to provide at least one of: status, topics")
        entry = self._items.setdefault(
            idx, {"status": _("gui", "websocket", "disconnected"), "topics": 0}
        )
        if status is not None:
            entry["status"] = status
        if topics is not None:
            entry["topics"] = topics
        self._emit()

    def remove(self, idx: int) -> None:
        if self._items.pop(idx, None) is not None:
            self._emit()

    def _emit(self) -> None:
        self._manager._bridge.emit("websockets", {
            "limit": WS_TOPICS_LIMIT,
            "max": MAX_WEBSOCKETS,
            "items": [
                {"idx": idx, **entry} for idx, entry in sorted(self._items.items())
            ],
        })


class LoginForm:
    def __init__(self, manager: GUIManager):
        self._manager = manager
        self._confirm = asyncio.Event()
        self._state: dict[str, Any] = {
            "status": _("gui", "login", "logged_out"), "user_id": None, "waiting": False,
            "code": None,
        }
        self._emit()

    def _emit(self) -> None:
        self._manager._bridge.emit("login", dict(self._state))

    def press(self) -> None:
        self._confirm.set()

    def clear(self, login: bool = False, password: bool = False, token: bool = False) -> None:
        # the web GUI has no credential fields; kept for interface compatibility
        pass

    async def wait_for_login_press(self) -> None:
        self._confirm.clear()
        self._state["waiting"] = True
        self._emit()
        try:
            await self._manager.coro_unless_closed(self._confirm.wait())
        finally:
            self._state["waiting"] = False
            self._emit()

    async def ask_login(self) -> NoReturn:
        # only reachable from the legacy username/password flow, which the core no longer uses
        raise MinerException("Username/password login isn't supported by this GUI")

    async def ask_enter_code(self, page_url: URL, user_code: str) -> None:
        self.update(_("gui", "login", "required"), None)
        self._manager.grab_attention(sound=False)
        self._manager.print(_("gui", "login", "request"))
        self._state["code"] = user_code
        try:
            await self.wait_for_login_press()
        finally:
            self._state["code"] = None
        self._manager.print(
            f"Enter this code on the Twitch's device activation page: {user_code}"
        )
        await asyncio.sleep(4)
        webopen(page_url)

    def update(self, status: str, user_id: int | None) -> None:
        self._state["status"] = status
        self._state["user_id"] = user_id
        self._emit()


class CampaignProgress:
    ALMOST_DONE_SECONDS = 10

    def __init__(self, manager: GUIManager):
        self._manager = manager
        self._drop: TimedDrop | None = None
        self._seconds: int = 0
        self._timer_task: asyncio.Task[None] | None = None

    async def _timer_loop(self) -> None:
        self._seconds = 60
        while self._seconds > 0:
            await asyncio.sleep(1)
            self._seconds -= 1
        self._timer_task = None

    def start_timer(self) -> None:
        if self._timer_task is None:
            if self._drop is None or self._drop.remaining_minutes <= 0:
                self._seconds = 60
            else:
                self._timer_task = asyncio.create_task(self._timer_loop())

    def stop_timer(self) -> None:
        if self._timer_task is not None:
            self._timer_task.cancel()
            self._timer_task = None

    def minute_almost_done(self) -> bool:
        return self._timer_task is None or self._seconds <= self.ALMOST_DONE_SECONDS

    def display(
        self, drop: TimedDrop | None, *, countdown: bool = True, subone: bool = False
    ) -> None:
        self._drop = drop
        self.stop_timer()
        self._manager._bridge.emit("drop", drop_view(drop) if drop is not None else None)
        if drop is None:
            self._seconds = 0
        elif countdown:
            self.start_timer()
        elif subone:
            self._seconds = 0


class ChannelList:
    def __init__(self, manager: GUIManager):
        self._manager = manager
        self._channels: dict[int, Channel] = {}
        self._watching: int | None = None
        self._selected: int | None = None
        self._emit_handle: asyncio.Handle | None = None

    def _schedule_emit(self) -> None:
        # channels update in bursts; send one snapshot per burst
        if self._emit_handle is None:
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                self._emit()
                return
            self._emit_handle = running.call_later(0.2, self._emit)

    def _emit(self) -> None:
        self._emit_handle = None
        self._manager._bridge.emit("channels", [
            channel_view(channel, watching=(cid == self._watching))
            for cid, channel in self._channels.items()
        ])

    def select(self, channel_id: int) -> None:
        if channel_id in self._channels:
            self._selected = channel_id

    def clear_selection(self) -> None:
        self._selected = None

    def get_selection(self) -> Channel | None:
        if self._selected is None:
            return None
        return self._channels.get(self._selected)

    def clear_watching(self) -> None:
        self._watching = None
        self._schedule_emit()

    def set_watching(self, channel: Channel) -> None:
        self._watching = channel.id
        self._schedule_emit()

    def clear(self) -> None:
        # the watched channel survives: the core refills the list and keeps watching it
        # without calling set_watching again; only clear_watching() resets it
        self._channels.clear()
        self._selected = None
        self._schedule_emit()

    def display(self, channel: Channel, *, add: bool = False) -> None:
        if not add and channel.id not in self._channels:
            return
        self._channels[channel.id] = channel
        self._schedule_emit()

    def remove(self, channel: Channel) -> None:
        self._channels.pop(channel.id, None)
        if self._selected == channel.id:
            self._selected = None
        self._schedule_emit()


class InventoryOverview:
    def __init__(self, manager: GUIManager):
        self._manager = manager
        self._campaigns: dict[str, DropsCampaign] = {}
        self._emit_handle: asyncio.Handle | None = None

    def _wanted(self, campaign: DropsCampaign) -> bool:
        settings = self._manager._twitch.settings
        name = campaign.game.name
        if name in settings.exclude:
            return False
        return settings.priority_mode is not PriorityMode.PRIORITY_ONLY or name in settings.priority

    def _schedule_emit(self) -> None:
        if self._emit_handle is None:
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                self._emit()
                return
            self._emit_handle = running.call_later(0.3, self._emit)

    def _emit(self) -> None:
        self._emit_handle = None
        self._manager._bridge.emit("inventory", [
            campaign_view(campaign, self._wanted(campaign))
            for campaign in self._campaigns.values()
        ])

    def clear(self) -> None:
        self._campaigns.clear()
        self._schedule_emit()

    async def add_campaign(self, campaign: DropsCampaign) -> None:
        self._campaigns[campaign.id] = campaign
        self._schedule_emit()

    def update_drop(self, drop: TimedDrop) -> None:
        if drop.campaign.id in self._campaigns:
            self._schedule_emit()

    def refresh(self) -> None:
        self._schedule_emit()


class _InvalidateButton:
    """Stands in for HelpTab._invalidate_button, which the core toggles directly."""

    def __init__(self, manager: GUIManager):
        self._manager = manager

    def config(self, *, state: str) -> None:
        self._manager._bridge.emit("auth_invalidatable", state == "normal")


class HelpTab:
    def __init__(self, manager: GUIManager):
        self._invalidate_button = _InvalidateButton(manager)
        self._invalidate_button.config(state="disabled")


class GUIManager:
    def __init__(self, twitch: Twitch):
        self._twitch: Twitch = twitch
        self._running = False
        self._close_requested = asyncio.Event()
        runtime = app.get_runtime()
        if runtime is not None:
            self._bridge: Bridge = runtime.bridge
            self._handlers = runtime.handlers
            runtime.on_close = self.close
        else:
            # no window (tests): events are only kept in the bridge snapshot
            self._bridge = Bridge(asyncio.get_event_loop())
            self._handlers = {}
        self._handlers.update({
            "close": self.close,
            "login_press": self._on_login_press,
            "switch_channel": self._on_switch_channel,
            "refresh_inventory": self._on_refresh_inventory,
            "invalidate_auth": self._on_invalidate_auth,
        })
        self.status = StatusBar(self)
        self.websockets = WebsocketStatus(self)
        self.login = LoginForm(self)
        self.progress = CampaignProgress(self)
        self.channels = ChannelList(self)
        self.inv = InventoryOverview(self)
        self.help = HelpTab(self)
        self.tray = TrayIcon(self)
        self._games: set[str] = set()
        self._bridge.emit("strings", {
            **_._translation["gui"]["web"], "help": _._translation["gui"]["help"],
        })
        self._bridge.emit("theme", twitch.settings.theme)
        self._emit_settings()
        # logging into the GUI's log view
        self._handler = _OutputHandler(self)
        self._handler.setFormatter(OUTPUT_FORMATTER)
        logger.addHandler(self._handler)
        if (logging_level := logger.getEffectiveLevel()) < logging.ERROR:
            self.print(f"Logging level: {logging.getLevelName(logging_level)}")
        if twitch.settings.tray:
            self.tray.minimize()

    def _emit_settings(self) -> None:
        settings = self._twitch.settings
        self._bridge.emit("settings", {
            "priority": list(settings.priority),
            "exclude": sorted(settings.exclude),
            "mode": MODE_NAMES[settings.priority_mode],
            "theme": settings.theme,
            "onboarding_done": settings.onboarding_done,
            "tray_notifications": settings.tray_notifications,
            "autostart_tray": settings.autostart_tray,
            "enable_badges_emotes": settings.enable_badges_emotes,
            "available_drops_check": settings.available_drops_check,
            "connection_quality": settings.connection_quality,
            "language": settings.language,
            "languages": list(_.languages),
            "proxy": str(settings.proxy),
        })

    # handlers called from the page (always on the asyncio loop thread)
    def _on_login_press(self) -> None:
        self.login.press()

    def _on_switch_channel(self, channel_id: int) -> None:
        self.channels.select(int(channel_id))
        self._twitch.change_state(State.CHANNEL_SWITCH)

    def _on_refresh_inventory(self) -> None:
        self._twitch.change_state(State.INVENTORY_FETCH)

    def _on_invalidate_auth(self) -> None:
        asyncio.create_task(task_wrapper(self._invalidate_token)())

    async def _invalidate_token(self) -> None:
        auth_state = await self._twitch.get_auth()
        async with self._twitch.request(
            "POST",
            "https://id.twitch.tv/oauth2/revoke",
            data={
                "client_id": self._twitch._client_type.CLIENT_ID,
                "token": auth_state.access_token,
            }
        ) as response:
            if response.status == 200:
                auth_state.invalidate(delete_cookies=True)
            else:
                logger.error(f"Failed to invalidate the auth token: {response.status}")
        self._twitch.change_state(State.RESTART)

    # lifecycle
    @property
    def running(self) -> bool:
        return self._running

    @property
    def close_requested(self) -> bool:
        return self._close_requested.is_set()

    async def wait_until_closed(self) -> None:
        await self._close_requested.wait()

    async def coro_unless_closed(self, coro: abc.Awaitable[_T]) -> _T:
        tasks = [asyncio.ensure_future(coro), asyncio.ensure_future(self._close_requested.wait())]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        if self._close_requested.is_set():
            raise ExitRequest()
        return await next(iter(done))

    def prevent_close(self) -> None:
        self._close_requested.clear()

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self.progress.stop_timer()
        self._running = False

    def close(self, *args: Any) -> int:
        self._close_requested.set()
        self._twitch.close()
        return 0

    def close_window(self) -> None:
        self.tray.stop()
        logger.removeHandler(self._handler)
        app.destroy_window()

    # interface used by the core
    def save(self, *, force: bool = False) -> None:
        # the Tk GUI saved its image cache here; the web page loads images itself
        pass

    def grab_attention(self, *, sound: bool = True) -> None:
        self.tray.restore()

    def set_games(self, games: set[Game]) -> None:
        self._games.update(game.name for game in games)
        by_game: dict[str, list[DropsCampaign]] = {}
        for campaign in self._twitch.inventory:
            if not (campaign.finished or campaign.expired):
                by_game.setdefault(campaign.game.name, []).append(campaign)
        self._bridge.emit("game_options", [
            game_option(campaigns[0].game, campaigns) for campaigns in by_game.values()
        ])

    def display_drop(
        self, drop: TimedDrop, *, countdown: bool = True, subone: bool = False
    ) -> None:
        self.progress.display(drop, countdown=countdown, subone=subone)
        self.tray.update_title(drop)

    def clear_drop(self) -> None:
        self.progress.display(None)
        self.tray.update_title(None)

    def print(self, message: str) -> None:
        stamp = datetime.now().strftime("%X")
        if '\n' in message:
            message = message.replace('\n', f"\n{stamp}: ")
        self._bridge.emit("log", f"{stamp}: {message}")
