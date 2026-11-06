"""
Process wiring for the web GUI.

pywebview needs the main thread (a hard requirement on macOS), so the asyncio core runs in a
background thread started by `webview.start`. The window, bridge and JS API are created here,
on the main thread, before the core starts; `GUIManager` picks them up via `get_runtime()`.
"""
from __future__ import annotations

import os
import asyncio
import threading
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Callable, Coroutine

from constants import WINDOW_TITLE
from utils import resource_path
from webgui.bridge import Api, Bridge


@dataclass
class Runtime:
    loop: asyncio.AbstractEventLoop
    bridge: Bridge
    handlers: dict[str, Callable[..., Any]]
    window: Any = None
    # set by GUIManager, called from the GUI thread when the user closes the window
    on_close: Callable[[], None] | None = None


_runtime: Runtime | None = None


class WebViewUnavailable(RuntimeError):
    """No usable WebView backend (Linux without WebKitGTK, Windows without WebView2...)."""


def _import_webview():
    # TDM_FORCE_NO_WEBVIEW lets the failure path be exercised on a machine that has a WebView
    if os.environ.get("TDM_FORCE_NO_WEBVIEW"):
        raise WebViewUnavailable("forced by TDM_FORCE_NO_WEBVIEW")
    try:
        import webview
    except Exception as exc:
        raise WebViewUnavailable(str(exc)) from exc
    return webview


def get_runtime() -> Runtime | None:
    return _runtime


def page_url() -> str:
    # loaded straight from disk: no local HTTP server is started
    return Path(resource_path("webgui/web/index.html")).resolve().as_uri()


def run(main: Callable[[], Coroutine[Any, Any, None]], *, hidden: bool = False) -> int:
    """
    Runs the `main` coroutine in a background thread while the GUI owns the main thread.
    Returns the exit code `main` ended with (via SystemExit), or 0.
    """
    webview = _import_webview()

    global _runtime
    loop = asyncio.new_event_loop()
    bridge = Bridge(loop)
    handlers: dict[str, Callable[..., Any]] = {}
    _runtime = runtime = Runtime(loop, bridge, handlers)

    window = webview.create_window(
        WINDOW_TITLE,
        url=page_url(),
        js_api=Api(bridge, handlers),
        width=1000,
        height=720,
        min_size=(760, 560),
        hidden=hidden,
        background_color="#f6f6f8",
    )
    runtime.window = window
    bridge.attach(window)
    window.events.loaded += bridge.mark_ready

    def on_closing() -> None:
        if runtime.on_close is not None:
            loop.call_soon_threadsafe(runtime.on_close)

    def on_closed() -> None:
        # nothing can be delivered to a destroyed window
        bridge.attach(None)

    window.events.closing += on_closing
    window.events.closed += on_closed

    exit_code: list[int] = [0]
    core_done = threading.Event()

    def core() -> None:
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(main())
        except SystemExit as exc:
            exit_code[0] = exc.code if isinstance(exc.code, int) else 0
        finally:
            core_done.set()
            destroy_window()

    try:
        webview.start(core)
    except Exception as exc:
        if not core_done.is_set() and not loop.is_running():
            # the GUI never came up, so the core never started
            raise WebViewUnavailable(str(exc)) from exc
        raise
    # the window can be gone before the core finished shutting down - let it finish
    core_done.wait(timeout=30)
    return exit_code[0]


def destroy_window() -> None:
    runtime = _runtime
    if runtime is None or runtime.window is None:
        return
    window, runtime.window = runtime.window, None
    runtime.bridge.attach(None)
    try:
        window.destroy()
    except Exception:
        pass


def show_window() -> None:
    if _runtime is not None and _runtime.window is not None:
        _runtime.window.show()
        _runtime.window.restore()


def hide_window() -> None:
    if _runtime is not None and _runtime.window is not None:
        _runtime.window.hide()
