"""
System tray icon for the web GUI. Same behavior as the Tk GUI's TrayIcon,
but it shows/hides the pywebview window instead of a Tk root.
"""
from __future__ import annotations

import sys
import asyncio
from typing import TYPE_CHECKING

import pystray
from PIL import Image as Image_module

from translate import _
from utils import resource_path
from exceptions import MinerException
from webgui import app

if TYPE_CHECKING:
    from inventory import TimedDrop
    from webgui.manager import GUIManager


class TrayIcon:
    TITLE = "Twitch Drops Miner"

    def __init__(self, manager: GUIManager):
        self._manager = manager
        self.icon: pystray.Icon | None = None  # type: ignore[unused-ignore]
        self._icon_images: dict[str, Image_module.Image] = {
            name: Image_module.open(resource_path(f"icons/{name}.ico"))
            for name in ("pickaxe", "active", "idle", "error", "maint")
        }
        self._icon_state: str = "pickaxe"
        self._drop: TimedDrop | None = None

    def _shorten(self, text: str, by_len: int, min_len: int) -> str:
        if (text_len := len(text)) <= min_len + 3 or by_len <= 0:
            return text
        return text[:-min(by_len + 3, text_len - min_len)] + "..."

    def get_title(self, drop: TimedDrop | None) -> str:
        if drop is None:
            return self.TITLE
        campaign = drop.campaign
        title_parts: list[str] = [
            f"{self.TITLE}\n",
            f"{campaign.game.name}\n",
            drop.rewards_text(),
            f" {drop.progress:.1%} ({campaign.claimed_drops}/{campaign.total_drops})"
        ]
        min_len: int = 30
        max_len: int = 127
        missing_len = len(''.join(title_parts)) - max_len
        if missing_len > 0:
            title_parts[2] = self._shorten(title_parts[2], missing_len, min_len)
            missing_len = len(''.join(title_parts)) - max_len
        if missing_len > 0:
            title_parts[1] = self._shorten(title_parts[1], missing_len, min_len)
            missing_len = len(''.join(title_parts)) - max_len
        if missing_len > 0:
            raise MinerException(f"Title couldn't be shortened: {''.join(title_parts)}")
        return ''.join(title_parts)

    def _start(self) -> None:
        loop = asyncio.get_running_loop()

        # the tray icon lives in a separate thread
        def bridge(func):
            return lambda: loop.call_soon_threadsafe(func)

        menu = pystray.Menu(
            pystray.MenuItem(_("gui", "tray", "show"), bridge(self.restore), default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(_("gui", "tray", "quit"), bridge(self.quit)),
        )
        self.icon = pystray.Icon(
            "twitch_miner", self._icon_images[self._icon_state], self.get_title(self._drop), menu
        )
        loop.run_in_executor(None, self.icon.run)

    def stop(self) -> None:
        if self.icon is not None:
            self.icon.stop()
            self.icon = None

    def quit(self) -> None:
        self._manager.close()

    def minimize(self) -> None:
        # pystray and pywebview both want the macOS main thread - no tray there (same as before)
        if sys.platform == "darwin":
            return
        if self.icon is None:
            self._start()
        else:
            self.icon.visible = True
        app.hide_window()

    def restore(self) -> None:
        if self.icon is not None:
            self.icon.visible = False
        app.show_window()

    def notify(
        self, message: str, title: str | None = None, duration: float = 10
    ) -> asyncio.Task[None] | None:
        if not self._manager._twitch.settings.tray_notifications:
            return None
        if self.icon is not None:
            icon = self.icon

            async def notifier():
                icon.notify(message, title)
                await asyncio.sleep(duration)
                icon.remove_notification()

            return asyncio.create_task(notifier())
        return None

    def update_title(self, drop: TimedDrop | None) -> None:
        self._drop = drop
        if self.icon is not None:
            self.icon.title = self.get_title(drop)

    def change_icon(self, state: str) -> None:
        if state not in self._icon_images:
            raise ValueError("Invalid icon state")
        self._icon_state = state
        if self.icon is not None:
            self.icon.icon = self._icon_images[state]
