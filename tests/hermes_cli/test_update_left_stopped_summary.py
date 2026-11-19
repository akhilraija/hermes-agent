"""A committed update that leaves its paused gateways stopped ends with a final summary (#145470).

The dependency follow-up fails after the code swap: C3 keeps exit 0 and the success receipt, and
the tree gate defers the paused set's resume. The deferral warning is mid-log; these tests pin the
run's final operational summary (and the operator's terminal notification) that names the outage
and its recovery command, without touching the exit contract. Seams are machine boundaries only:
the completion child's answer, the receipt store, and the tree gate's verdict.
"""
from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from hermes_cli import terminal_notify, update_cmd, update_cmd_windows, update_pause_record

UPDATE_ID = "f" * 32
DEPS_REASON = "dependencies are not current for the updated code yet"


def _token():
    return {"resume_needed": True, "pause_id": "p1", "platform": "posix",
            "posix_units": [{"kind": "systemd", "scope": "user", "unit": "hermes-gateway", "pid": 4242}],
            "unmapped": []}


def _request(token):
    return {"branch": "main", "source": "/nonexistent/source", "home": "/nonexistent/home",
            "desktop": False, "gateway_mode": False, "expected_sha": "abc123",
            "receipt": {"update_id": UPDATE_ID}, "windows_resume": token}


def _deps_owed_result():
    """What the bootstrap answers when dependency preparation fails after the swap (A6)."""
    return {"schema": 1, "update_id": UPDATE_ID, "exit_code": 0,
            "receipt": {"update_id": UPDATE_ID, "outcome": "success", "exit_code": 0,
                        "finished_at": "now",
                        "followups": [{"step": "dependencies", "reason": "venv: uv sync exited 1"}]},
            "windows_resume": None, "pm_receipt": None}


@pytest.fixture
def notifications(monkeypatch):
    monkeypatch.setattr(update_cmd, "_unrestored_autostash_notice", lambda: None, raising=False)
    monkeypatch.setattr(update_cmd, "_completion_receipt", SimpleNamespace(
        record_stage=Mock(), adopt_terminal_receipt=Mock(),
        _current=SimpleNamespace(get=lambda: None)))
    from hermes_cli import update_stage
    monkeypatch.setattr(update_stage, "publish_stage", lambda *a, **k: None)
    monkeypatch.setattr(update_cmd, "_write_fleet_restart_pending_marker", lambda **kw: None)
    monkeypatch.setattr(update_cmd, "_accept_completion_pm_receipt", lambda *a, **k: None)
    monkeypatch.setattr(update_cmd, "adopt_retired_channel", lambda request: False)
    monkeypatch.setattr(update_pause_record, "sync", lambda token: None)
    monkeypatch.setattr(update_pause_record, "tree_is_whole",
                        lambda token, root=None: (False, DEPS_REASON))
    monkeypatch.setattr(update_cmd, "_m", lambda: SimpleNamespace(
        _is_windows=lambda: False,
        _resume_windows_gateways_after_update=update_cmd_windows._resume_windows_gateways_after_update))
    sent = []
    monkeypatch.setattr(terminal_notify, "write_tty", sent.append)
    return sent


def test_deps_owed_deferral_ends_with_a_final_summary(notifications, monkeypatch, capsys):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    token = _token()
    monkeypatch.setattr(update_cmd, "run_completion", lambda request: _deps_owed_result())

    update_cmd._complete_source_update(_request(token))  # must not raise: C3 keeps the exit 0

    out = capsys.readouterr().out
    assert "Paused gateway(s) left stopped" in out  # the mid-log deferral warning still prints
    assert "Gateway(s) left stopped after the update" in out
    assert DEPS_REASON in out
    assert "Still stopped: hermes-gateway" in out
    # The summary is the run's LAST word, after the mid-log warning — not another mid-log line.
    lines = [line for line in out.splitlines() if line.strip()]
    assert lines[-1].strip().startswith("Recover: run `hermes update` again")
    assert out.index("Gateway(s) left stopped after the update") > out.index("Paused gateway(s) left stopped")
    assert token["resume_deferred"] == DEPS_REASON
    assert len(notifications) == 1
    assert "\x1b]9;" in notifications[0] and "stopped" in notifications[0]


def test_a_resumed_set_gets_no_left_stopped_summary(notifications, monkeypatch, capsys):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    token = _token()

    def resumed(tok):
        tok["resume_needed"] = False  # every paused runtime came back

    monkeypatch.setattr(update_cmd, "_m", lambda: SimpleNamespace(
        _is_windows=lambda: False, _resume_windows_gateways_after_update=resumed))
    monkeypatch.setattr(update_cmd, "run_completion", lambda request: _deps_owed_result())

    update_cmd._complete_source_update(_request(token))

    out = capsys.readouterr().out
    assert "left stopped after the update" not in out
    assert notifications == []


def test_child_deferred_resume_also_gets_the_summary(notifications, monkeypatch, capsys):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    token = _token()
    result = _deps_owed_result()
    # The completion child attempted the resume itself and handed back a deferred token.
    result["windows_resume"] = {**token, "resume_needed": False, "resume_deferred": DEPS_REASON}
    monkeypatch.setattr(update_cmd, "run_completion", lambda request: result)

    update_cmd._complete_source_update(_request(token))

    out = capsys.readouterr().out
    assert "Gateway(s) left stopped after the update" in out
    assert "Still stopped: hermes-gateway" in out
    assert len(notifications) == 1


def test_gateway_mode_reports_without_a_terminal_notification(notifications, monkeypatch, capsys):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    token = _token()
    monkeypatch.setattr(update_cmd, "run_completion", lambda request: _deps_owed_result())
    request = _request(token)
    request["gateway_mode"] = True  # the /update watcher reads the receipt, not a terminal

    update_cmd._complete_source_update(request)

    out = capsys.readouterr().out
    assert "Gateway(s) left stopped after the update" in out
    assert notifications == []


def test_no_paused_set_means_no_summary(notifications, monkeypatch, capsys):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(update_cmd, "run_completion", lambda request: _deps_owed_result())
    request = _request(None)  # nothing was paused for this update

    update_cmd._complete_source_update(request)

    out = capsys.readouterr().out
    assert "left stopped after the update" not in out
    assert notifications == []
