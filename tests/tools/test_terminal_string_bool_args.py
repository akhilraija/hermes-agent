"""Regression tests for #157759: terminal tool must accept stringified
boolean args ("True"/"False") that some models emit instead of JSON
true/false, and must not treat the string "False" as enabled.

Before the fix:
  - notify="True" was rejected ("notify must be true/false ..."), so the
    job never started and agents re-launched it 2-3 times.
  - background="False" / persist_on_release="False" were truthy strings,
    silently enabling background mode / persistence.
"""

import json
from unittest.mock import patch

from tools.terminal_tool import _coerce_string_bool, _handle_terminal


def _dispatch(args):
    """Run the handler with the executor mocked; return (result, mock)."""
    with patch("tools.terminal_tool.terminal_tool") as mock:
        mock.return_value = json.dumps({"output": "ok"})
        result = _handle_terminal(args, task_id="t1")
    return json.loads(result), mock


class TestCoerceStringBool:
    def test_python_spellings(self):
        assert _coerce_string_bool("True") is True
        assert _coerce_string_bool("False") is False

    def test_case_and_whitespace(self):
        assert _coerce_string_bool(" true ") is True
        assert _coerce_string_bool("FALSE") is False

    def test_non_boolean_values_unchanged(self):
        assert _coerce_string_bool("yes") == "yes"
        assert _coerce_string_bool("") == ""
        assert _coerce_string_bool(True) is True
        assert _coerce_string_bool(False) is False
        assert _coerce_string_bool(None) is None
        assert _coerce_string_bool(["ERR"]) == ["ERR"]
        assert _coerce_string_bool(1) == 1


class TestStringBoolArgs:
    def test_notify_string_true_accepted(self):
        result, mock = _dispatch(
            {"command": "make", "background": True, "notify": "True"}
        )
        assert "error" not in result
        kwargs = mock.call_args.kwargs
        assert kwargs["notify_on_complete"] is True
        assert kwargs["watch_patterns"] is None

    def test_notify_string_false_accepted(self):
        result, mock = _dispatch(
            {"command": "make", "background": True, "notify": "False"}
        )
        assert "error" not in result
        assert mock.call_args.kwargs["notify_on_complete"] is False

    def test_background_string_false_runs_foreground(self):
        result, mock = _dispatch({"command": "echo hi", "background": "False"})
        assert "error" not in result
        assert mock.call_args.kwargs["background"] is False

    def test_background_and_pty_string_true(self):
        result, mock = _dispatch(
            {"command": "python", "background": "True", "pty": "True"}
        )
        assert "error" not in result
        kwargs = mock.call_args.kwargs
        assert kwargs["background"] is True
        assert kwargs["pty"] is True

    def test_persist_on_release_string_false(self):
        result, mock = _dispatch(
            {"command": "sleep 1", "background": True, "persist_on_release": "False"}
        )
        assert "error" not in result
        assert mock.call_args.kwargs["persist_on_release"] is False

    def test_legacy_notify_on_complete_string(self):
        result, mock = _dispatch(
            {"command": "make", "background": True, "notify_on_complete": "True"}
        )
        assert "error" not in result
        assert mock.call_args.kwargs["notify_on_complete"] is True

    def test_invalid_notify_string_still_rejected(self):
        result, mock = _dispatch(
            {"command": "make", "background": True, "notify": "yes"}
        )
        assert "error" in result
        assert "notify must be true/false" in result["error"]
        mock.assert_not_called()

    def test_real_bools_and_lists_unchanged(self):
        result, mock = _dispatch(
            {"command": "tail -f log", "background": True, "notify": ["ERR"]}
        )
        assert "error" not in result
        kwargs = mock.call_args.kwargs
        assert kwargs["watch_patterns"] == ["ERR"]
        assert kwargs["notify_on_complete"] is False

    def test_original_args_dict_not_mutated(self):
        """The prepared-approval consent guard compares the caller's args
        dict; coercion must rebind a copy, not mutate the original."""
        args = {"command": "make", "background": "True", "notify": "True"}
        with patch("tools.terminal_tool.terminal_tool") as mock:
            mock.return_value = json.dumps({"output": "ok"})
            _handle_terminal(args, task_id="t1")
        assert args["background"] == "True"
        assert args["notify"] == "True"
