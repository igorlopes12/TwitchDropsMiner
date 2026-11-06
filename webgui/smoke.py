from __future__ import annotations

import sys
import threading


def run_smoke() -> int:
    """
    Opens a tiny pywebview window, evaluates JS in it and prints the result.
    Used by CI to prove the WebView backend works inside the packaged app.
    """
    try:
        import webview
    except Exception as exc:
        _report(f"WEBVIEW_FAIL {exc!r}")
        return 3

    result: dict[str, object] = {}

    def probe(window) -> None:
        try:
            # proves the packaged page loaded and its script ran
            result["value"] = window.evaluate_js("typeof window.tdm.on")
        except Exception as exc:
            result["error"] = exc
        finally:
            window.destroy()

    # failsafe: never hang CI if the window never loads
    timer = threading.Timer(15, lambda: result.setdefault("error", "timeout") and _destroy_all())
    timer.daemon = True
    try:
        from webgui.app import page_url

        window = webview.create_window("TDM smoke", url=page_url(), width=400, height=300)
        timer.start()
        webview.start(probe, window)
    except Exception as exc:
        result["error"] = exc
    finally:
        timer.cancel()

    if "error" in result or result.get("value") != "function":
        _report(f"WEBVIEW_FAIL {result.get('error', result.get('value'))!r}")
        return 3
    _report(f"WEBVIEW_OK {result['value']}")
    return 0


def _report(line: str) -> None:
    # windowed builds have no stdout, so CI reads the file instead
    if sys.stdout is not None:
        print(line, flush=True)
    with open("webview-smoke.txt", "w", encoding="utf8") as file:
        file.write(line + "\n")


def _destroy_all() -> None:
    import webview

    for window in list(webview.windows):
        window.destroy()


if __name__ == "__main__":
    sys.exit(run_smoke())
