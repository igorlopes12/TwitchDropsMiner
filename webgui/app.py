"""
Process wiring for the web GUI.

pywebview needs the main thread (a hard requirement on macOS), so the asyncio core runs in a
background thread started by `webview.start`. The window, bridge and JS API are created here,
on the main thread, before the core starts; `GUIManager` picks them up via `get_runtime()`.
"""
from __future__ import annotations

import os
import sys
import asyncio
import threading
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Callable, Coroutine

from constants import WINDOW_TITLE
from utils import resource_path
from webgui.bridge import Api, Bridge


# how long the main thread waits for the core to shut down after the window is gone;
# the core runs in a daemon thread, so a core stuck past this can't keep the process alive
CORE_SHUTDOWN_TIMEOUT: float = 30


@dataclass
class Runtime:
    loop: asyncio.AbstractEventLoop
    bridge: Bridge
    handlers: dict[str, Callable[..., Any]]
    window: Any = None
    # called on the core's loop when the window is closed or gone
    on_close: Callable[[], None] | None = None
    # called on the core's loop when the window gets minimized
    on_minimize: Callable[[], None] | None = None
    window_gone: bool = False

    def __post_init__(self) -> None:
        self._lock = threading.Lock()

    def set_close_handler(self, handler: Callable[[], None]) -> None:
        """Called on the core's loop. If the window is already gone, the handler runs right away."""
        with self._lock:
            self.on_close = handler
            gone = self.window_gone
        if gone:
            self.loop.call_soon(handler)

    def request_close(self, *, window_gone: bool = False) -> None:
        """Called from GUI threads. Asks the core to shut down."""
        with self._lock:
            if window_gone:
                self.window_gone = True
            handler = self.on_close
        if handler is not None:
            try:
                self.loop.call_soon_threadsafe(handler)
            except RuntimeError:
                # the loop is already closed: the core has finished
                pass


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


def require_modern_renderer(platform: str, renderer: str | None) -> None:
    """
    On Windows without the WebView2 runtime, pywebview silently falls back to MSHTML (IE11),
    which can't run the page - fail with the friendly "no WebView" message instead.
    """
    if platform == "win32" and renderer not in ("edgechromium", "cef"):
        raise WebViewUnavailable(f"unsupported renderer: {renderer}")


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
    if sys.platform == "win32":
        try:
            from webview.platforms import winforms
        except Exception as exc:
            raise WebViewUnavailable(str(exc)) from exc
        require_modern_renderer(sys.platform, getattr(winforms, "renderer", None))

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
        runtime.request_close()

    def on_closed() -> None:
        # nothing can be delivered to a destroyed window
        bridge.attach(None)

    def on_minimized() -> None:
        handler = runtime.on_minimize
        if handler is not None:
            try:
                loop.call_soon_threadsafe(handler)
            except RuntimeError:
                pass

    window.events.closing += on_closing
    window.events.closed += on_closed
    window.events.minimized += on_minimized

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

    # a daemon thread: if the core ever hangs on shutdown, it can't keep the process alive
    core_thread = threading.Thread(target=core, name="TDM core", daemon=True)
    try:
        webview.start(core_thread.start)
    except Exception as exc:
        if not core_done.is_set() and not loop.is_running():
            # the GUI never came up, so the core never started
            raise WebViewUnavailable(str(exc)) from exc
        raise
    # the window is gone. It may have closed without a `closing` event (Cmd+Q on macOS),
    # so make sure the core is asked to shut down, then give it time to save and exit.
    runtime.request_close(window_gone=True)
    core_done.wait(timeout=CORE_SHUTDOWN_TIMEOUT)
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
