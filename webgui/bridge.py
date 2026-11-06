"""
Python <-> JS bridge for the web GUI.

Python -> JS: `Bridge.emit(event, payload)` calls `window.tdm.on(event, payload)` in the page.
JS -> Python: the page calls `window.pywebview.api.<method>(...)` on an `Api` instance;
each call is handed over to the asyncio loop thread, where the core lives.
"""
from __future__ import annotations

import json
import asyncio
import inspect
import logging
import threading
from collections import deque
from typing import Any, Callable


logger = logging.getLogger("TwitchDrops")

# events whose latest payload describes the current state, re-sent when the page reloads
STATE_EVENTS = frozenset({
    "status", "drop", "channels", "inventory", "login", "websockets",
    "settings", "theme", "strings", "game_options", "auth_invalidatable",
})
MAX_QUEUED_LOGS = 500


def _to_js(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False)
    # keep the literal safe inside any JS context
    return text.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


class Bridge:
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.snapshot: dict[str, Any] = {}
        self._window: Any = None
        self._ready = False
        self._queue: deque[tuple[str, str]] = deque()
        self._queued_logs = 0
        self._lock = threading.Lock()

    def attach(self, window: Any) -> None:
        self._window = window

    def mark_ready(self) -> None:
        with self._lock:
            self._ready = True
            pending = list(self._queue)
            self._queue.clear()
            self._queued_logs = 0
            for _, script in pending:
                self._send(script)

    def emit(self, event: str, payload: Any = None) -> None:
        script = f"window.tdm.on({_to_js(event)}, {_to_js(payload)})"
        with self._lock:
            if event in STATE_EVENTS:
                self.snapshot[event] = payload
            if not self._ready:
                self._enqueue(event, script)
                return
            self._send(script)

    def _enqueue(self, event: str, script: str) -> None:
        self._queue.append((event, script))
        if event != "log":
            return
        self._queued_logs += 1
        if self._queued_logs > MAX_QUEUED_LOGS:
            for i, (queued_event, _) in enumerate(self._queue):
                if queued_event == "log":
                    del self._queue[i]
                    break
            self._queued_logs -= 1

    def _send(self, script: str) -> None:
        if self._window is None:
            return
        try:
            # run_js doesn't wait for a result, so the core thread never blocks on the GUI
            self._window.run_js(script)
        except Exception:
            # the window may already be gone during shutdown
            logger.debug("Failed to deliver an event to the web GUI", exc_info=True)


class Api:
    """
    Exposed to the page as `window.pywebview.api`. Public methods only.
    """

    def __init__(self, bridge: Bridge, handlers: dict[str, Callable[..., Any]]):
        self._bridge = bridge
        self._handlers = handlers

    def _call(self, name: str, *args: Any) -> None:
        handler = self._handlers.get(name)
        if handler is None:
            return

        def run() -> None:
            result = handler(*args)
            if inspect.isawaitable(result):
                asyncio.ensure_future(result)

        self._bridge.loop.call_soon_threadsafe(run)

    def get_snapshot(self) -> dict[str, Any]:
        with self._bridge._lock:
            return dict(self._bridge.snapshot)

    def login_press(self) -> None:
        self._call("login_press")

    def submit_code(self, code: str) -> None:
        self._call("submit_code", code)

    def switch_channel(self, channel_id: int) -> None:
        self._call("switch_channel", channel_id)

    def set_games(self, names: list[str], mode: str) -> None:
        self._call("set_games", names, mode)

    def finish_onboarding(self, names: list[str], mode: str) -> None:
        self._call("finish_onboarding", names, mode)

    def set_setting(self, key: str, value: Any) -> None:
        self._call("set_setting", key, value)

    def refresh_inventory(self) -> None:
        self._call("refresh_inventory")

    def invalidate_auth(self) -> None:
        self._call("invalidate_auth")

    def close(self) -> None:
        self._call("close")
