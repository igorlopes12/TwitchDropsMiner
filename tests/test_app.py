import pytest

from webgui import app


def test_missing_webview_raises_friendly_error(monkeypatch):
    monkeypatch.setenv("TDM_FORCE_NO_WEBVIEW", "1")

    async def main():
        raise AssertionError("the core must not start without a WebView")

    with pytest.raises(app.WebViewUnavailable):
        app.run(main)


def test_page_url_points_at_packaged_index():
    url = app.page_url()
    assert url.startswith("file://")
    assert url.endswith("/webgui/web/index.html")


import asyncio
import threading
import time
from types import SimpleNamespace as NS


class FakeEvent:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def fire(self):
        for handler in self.handlers:
            handler()


class FakeWindow:
    def __init__(self):
        self.events = NS(loaded=FakeEvent(), closing=FakeEvent(), closed=FakeEvent(),
                         minimized=FakeEvent())

    def run_js(self, script):
        pass

    def destroy(self):
        pass

    def hide(self):
        pass

    def show(self):
        pass

    def restore(self):
        pass


class FakeWebview:
    """start() returns without firing `closing` - what Cmd+Q does on macOS."""

    def __init__(self, after_start=None):
        self.window = None
        self._after_start = after_start

    def create_window(self, *args, **kwargs):
        self.window = FakeWindow()
        return self.window

    def start(self, func):
        func()
        if self._after_start is not None:
            self._after_start(self.window)


def wait_for(condition, timeout=3):
    end = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < end, "timed out"
        time.sleep(0.01)


def test_window_gone_without_closing_event_still_closes_core(monkeypatch):
    monkeypatch.setattr(app, "_import_webview", lambda: FakeWebview())

    async def main():
        closed = asyncio.Event()
        app.get_runtime().set_close_handler(closed.set)
        await closed.wait()
        raise SystemExit(7)

    started = time.monotonic()
    assert app.run(main) == 7
    assert time.monotonic() - started < 5


def test_core_thread_does_not_keep_process_alive(monkeypatch):
    monkeypatch.setattr(app, "_import_webview", lambda: FakeWebview())
    monkeypatch.setattr(app, "CORE_SHUTDOWN_TIMEOUT", 0.2)
    threads = []

    async def main():
        threads.append(threading.current_thread())
        await asyncio.Event().wait()  # never finishes, ignores close requests

    app.run(main)
    assert threads and threads[0].daemon


def test_minimize_is_forwarded_to_the_core(monkeypatch):
    minimized = threading.Event()

    def after_start(window):
        wait_for(lambda: app.get_runtime().on_minimize is not None)
        window.events.minimized.fire()
        wait_for(minimized.is_set)

    monkeypatch.setattr(app, "_import_webview", lambda: FakeWebview(after_start))

    async def main():
        closed = asyncio.Event()
        runtime = app.get_runtime()
        runtime.on_minimize = minimized.set
        runtime.set_close_handler(closed.set)
        await closed.wait()

    app.run(main)
    assert minimized.is_set()


@pytest.mark.parametrize("platform, renderer, ok", [
    ("win32", "edgechromium", True),
    ("win32", "mshtml", False),
    ("win32", "cef", True),
    ("darwin", None, True),
])
def test_old_windows_renderer_is_rejected(platform, renderer, ok):
    if ok:
        app.require_modern_renderer(platform, renderer)
    else:
        with pytest.raises(app.WebViewUnavailable):
            app.require_modern_renderer(platform, renderer)
