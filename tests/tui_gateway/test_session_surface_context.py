"""Legacy chat turns expose their client surface to plugins (regression for #159591)."""

from types import SimpleNamespace

import pytest

from gateway.session_context import get_session_env
from hermes_cli.plugin_session import session_surface
from tui_gateway import server


@pytest.mark.parametrize("source", ["desktop", "tui", "cli"])
def test_legacy_turn_binds_its_surface_and_clears_it(monkeypatch, source):
    monkeypatch.setitem(server._sessions, "surface-ui", {
        "session_key": "surface-conversation", "source": source,
        "agent": SimpleNamespace(session_id="surface-agent"), "cwd": "",
    })
    tokens = server._set_session_context("surface-conversation", ui_session_id="surface-ui")
    try:
        assert session_surface() == source
        assert get_session_env("HERMES_SESSION_PLATFORM") == source
        assert get_session_env("HERMES_SESSION_CHAT_TYPE") == "dm"
        assert get_session_env("HERMES_SESSION_SOURCE") == source
        assert get_session_env("HERMES_SESSION_ID") == "surface-agent"
    finally:
        server._clear_session_context(tokens)
    assert session_surface() == ""
    assert get_session_env("HERMES_SESSION_PLATFORM") == ""
    assert get_session_env("HERMES_SESSION_CHAT_TYPE") == ""


def test_legacy_custom_source_does_not_replace_the_client_surface(monkeypatch):
    monkeypatch.setattr(server, "_resolve_session_platform", lambda: "tui")
    monkeypatch.setitem(server._sessions, "tagged-ui", {
        "session_key": "tagged-conversation", "source": "plugin-task", "cwd": "",
    })
    tokens = server._set_session_context("tagged-conversation")
    try:
        assert session_surface() == "tui"
        assert get_session_env("HERMES_SESSION_SOURCE") == "plugin-task"
        assert get_session_env("HERMES_SESSION_CHAT_TYPE") == "dm"
    finally:
        server._clear_session_context(tokens)
