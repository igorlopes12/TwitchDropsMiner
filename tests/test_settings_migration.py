from settings import migrate
from constants import PriorityMode


def test_dark_mode_true_becomes_dark():
    assert migrate({"dark_mode": True})["theme"] == "dark"


def test_dark_mode_false_becomes_system():
    assert migrate({"dark_mode": False})["theme"] == "system"


def test_existing_theme_kept():
    assert migrate({"dark_mode": True, "theme": "light"})["theme"] == "light"


def test_fresh_install_needs_onboarding():
    assert migrate({})["onboarding_done"] is False


def test_fresh_install_theme_is_system():
    assert migrate({})["theme"] == "system"


def test_user_with_priority_skips_onboarding():
    raw = {"priority": ["Rust"], "priority_mode": PriorityMode.PRIORITY_ONLY}
    assert migrate(raw)["onboarding_done"] is True


def test_user_with_non_priority_mode_skips_onboarding():
    raw = {"priority": [], "priority_mode": PriorityMode.ENDING_SOONEST}
    assert migrate(raw)["onboarding_done"] is True


def test_empty_priority_only_needs_onboarding():
    raw = {"priority": [], "priority_mode": PriorityMode.PRIORITY_ONLY}
    assert migrate(raw)["onboarding_done"] is False


def test_explicit_onboarding_flag_kept():
    assert migrate({"onboarding_done": False, "priority": ["Rust"]})["onboarding_done"] is False
