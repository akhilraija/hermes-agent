"""Regression for the Unicode reply budget inflation in #152837."""

import json

import pytest

from tools import bot_live_delivery, bot_mode_dm
from tools.process_registry_notifications import format_process_notification


@pytest.mark.parametrize("reply", ["คำตอบภาษาไทย" * 100, "Kết quả đã kiểm tra. " * 100, "answer " * 100],
                         ids=["thai", "vietnamese", "ascii"])
def test_settled_reply_survives_completion_budget(tmp_path, monkeypatch, capsys, reply):
    delivery_id = "a" * 32
    monkeypatch.setattr(bot_live_delivery, "await_delivery", lambda *_args: {
        "status": "settled", "delivery_id": delivery_id, "reply": reply,
    })

    assert bot_mode_dm._wait_live_dm(str(tmp_path), delivery_id) == 0
    output = capsys.readouterr().out
    assert json.loads(output)["reply"] == reply
    # The completion channel budgets characters, not decoded JSON: a reply that fits
    # must not be expanded into six-character escapes before the budget is applied.
    assert len(output) <= len(reply) + 200
    text = format_process_notification({
        "type": "completion", "session_id": "proc_unicode", "exit_code": 0,
        "output": output, "completion_output_chars": len(reply) + 200,
    })
    assert reply in text
