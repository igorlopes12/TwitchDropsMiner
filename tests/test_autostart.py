import sys

import pytest

from webgui import autostart

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="uses the registry on Windows")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    (tmp_path / ".config" / "autostart").mkdir(parents=True)
    return tmp_path


def test_autostart_roundtrip(home):
    assert autostart.query() is False
    autostart.update(True, tray=True, logging_level=0)
    assert autostart.query() is True
    autostart.update(False, tray=False, logging_level=0)
    assert autostart.query() is False


def test_autostart_tray_flag_written(home):
    autostart.update(True, tray=True, logging_level=0)
    written = autostart.entry_file().read_text(encoding="utf8", errors="replace")
    assert "--tray" in written
    autostart.update(False, tray=False, logging_level=0)
