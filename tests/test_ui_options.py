"""Unit tests for Pygame demo CLI parsing (no pygame import)."""

from __future__ import annotations

from homemate.ui_options import MainOptions, parse_main_args


def test_defaults() -> None:
    opts = parse_main_args([])
    assert opts == MainOptions()


def test_offline_shorthand() -> None:
    opts = parse_main_args(["--offline", "--seed", "42", "--owner-room", "bedroom"])
    assert opts.seed == 42
    assert opts.owner_room == "bedroom"
    assert opts.mock_llm is True
    assert opts.mock_emotion is True
    assert opts.freeze_owner is True


def test_emotion_injection_flag() -> None:
    opts = parse_main_args(["--mock-emotion", "--emotion", "tired"])
    assert opts.mock_emotion is True
    assert opts.emotion == "tired"


def test_replan_demo_flag() -> None:
    opts = parse_main_args(["--replan-demo"])
    assert opts.replan_demo is True
    assert opts.mock_llm is True
    assert opts.freeze_owner is False
    assert opts.auto_run is True
    assert opts.auto_message is not None


def test_tool_step_formatting() -> None:
    from homemate.ui_trace import format_tool_step

    label, ok = format_tool_step({
        "name": "set_device",
        "input": {"device_id": "coffee.kitchen", "action": "brew"},
        "output": {"ok": True},
    })
    assert ok is True
    assert "coffee.kitchen" in label

    label, ok = format_tool_step({
        "name": "read_emotion",
        "input": {},
        "output": {"ok": False, "error": "owner/item not in the same room"},
    })
    assert ok is False
    assert "read_emotion" in label
