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
