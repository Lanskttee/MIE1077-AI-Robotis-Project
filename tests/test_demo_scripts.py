"""Tests for built-in demo scripts."""

from __future__ import annotations

import pytest

from homemate.demo_scripts import apply_script, get_script, script_ids
from homemate.ui_options import MainOptions, parse_main_args


def test_script_catalog_non_empty() -> None:
    ids = script_ids()
    assert "tired_coffee" in ids
    assert len(ids) >= 3


def test_apply_script_forces_offline() -> None:
    base = MainOptions(seed=1, auto_run=True)
    opts = apply_script(base, "tired_coffee")
    assert opts.mock_llm is True
    assert opts.mock_emotion is True
    assert opts.freeze_owner is True
    assert opts.owner_room == "bedroom"
    assert opts.emotion == "tired"
    assert opts.auto_message == "I'm tired. Brew some coffee."


def test_get_script_unknown_raises() -> None:
    with pytest.raises(ValueError, match="unknown script"):
        get_script("not_a_script")


def test_cli_script_auto_run() -> None:
    opts = parse_main_args(["--script", "sad_talk", "--auto-run"])
    assert opts.script == "sad_talk"
    assert opts.auto_run is True
    assert opts.auto_message == "I feel low today. Can we just talk?"
