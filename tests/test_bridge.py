import asyncio
import json
import re
import threading
import time

from webgui.bridge import Api, Bridge

CALL = re.compile(r"^window\.tdm\.on\((.*?), (.*)\)$", re.S)


class FakeWindow:
    def __init__(self):
        self.calls: list[str] = []

    def run_js(self, script: str) -> None:
        self.calls.append(script)

    def decoded(self) -> list[tuple[str, object]]:
        self.bridge.wait_idle()
        out = []
        for script in self.calls:
            match = CALL.match(script)
            assert match, script
            out.append((json.loads(match.group(1)), json.loads(match.group(2))))
        return out


def make_bridge():
    loop = asyncio.new_event_loop()
    bridge = Bridge(loop)
    window = FakeWindow()
    window.bridge = bridge
    bridge.attach(window)
    return loop, bridge, window


def test_emit_never_blocks_on_gui():
    loop = asyncio.new_event_loop()
    bridge = Bridge(loop)
    release = threading.Event()
    delivered = []

    class StuckWindow:
        def run_js(self, script):
            release.wait()
            delivered.append(script)

    bridge.attach(StuckWindow())
    bridge.mark_ready()
    started = time.monotonic()
    bridge.emit("status", "a")
    bridge.emit("status", "b")
    assert time.monotonic() - started < 0.5
    release.set()
    bridge.wait_idle()
    assert len(delivered) == 2


def test_events_before_ready_are_flushed():
    _, bridge, window = make_bridge()
    bridge.emit("status", "Idle")
    bridge.emit("log", "hello")
    assert window.calls == []
    bridge.mark_ready()
    assert window.decoded() == [("status", "Idle"), ("log", "hello")]


def test_events_after_ready_go_straight_through():
    _, bridge, window = make_bridge()
    bridge.mark_ready()
    bridge.emit("status", "Mining")
    assert window.decoded() == [("status", "Mining")]


def test_payload_is_json_escaped():
    _, bridge, window = make_bridge()
    bridge.mark_ready()
    nasty = '"); alert(1); ("</script>😀 '
    bridge.emit("drop", {"name": nasty})
    assert window.decoded() == [("drop", {"name": nasty})]
    assert "</script>" not in window.calls[0]


def test_emit_from_other_thread():
    _, bridge, window = make_bridge()
    bridge.mark_ready()
    thread = threading.Thread(target=bridge.emit, args=("status", "from thread"))
    thread.start()
    thread.join()
    assert window.decoded() == [("status", "from thread")]


def test_snapshot_keeps_last_state():
    _, bridge, _ = make_bridge()
    bridge.emit("status", "a")
    bridge.emit("status", "b")
    bridge.emit("log", "not state")
    assert bridge.snapshot["status"] == "b"
    assert "log" not in bridge.snapshot


def test_log_queue_capped():
    _, bridge, window = make_bridge()
    bridge.emit("status", "keep me")
    for i in range(600):
        bridge.emit("log", f"line {i}")
    bridge.mark_ready()
    events = window.decoded()
    logs = [p for e, p in events if e == "log"]
    assert len(logs) == 500
    assert logs[0] == "line 100" and logs[-1] == "line 599"
    assert ("status", "keep me") in events


def test_get_snapshot_returns_copy():
    _, bridge, _ = make_bridge()
    api = Api(bridge, {})
    bridge.emit("status", "Idle")
    snap = api.get_snapshot()
    snap["status"] = "changed"
    assert bridge.snapshot["status"] == "Idle"


def test_close_from_js_sets_close_requested():
    loop, bridge, _ = make_bridge()
    closed = asyncio.Event()
    api = Api(bridge, {"close": closed.set})
    threading.Thread(target=api.close).start()
    loop.run_until_complete(asyncio.wait_for(closed.wait(), 2))
    assert closed.is_set()


def test_api_handler_gets_arguments_and_coroutines_run():
    loop, bridge, _ = make_bridge()
    got = []

    async def switch(channel_id):
        got.append(channel_id)

    api = Api(bridge, {"switch_channel": switch})
    api.switch_channel(42)
    loop.run_until_complete(asyncio.sleep(0.05))
    assert got == [42]


def test_api_missing_handler_is_ignored():
    loop, bridge, _ = make_bridge()
    api = Api(bridge, {})
    api.refresh_inventory()  # must not raise
    loop.run_until_complete(asyncio.sleep(0))
