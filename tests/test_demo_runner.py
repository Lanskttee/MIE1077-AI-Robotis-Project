"""Tests for the batch demo script runner."""

from __future__ import annotations

from homemate.demo_runner.runner import DemoBatchRunner, format_table, run_script
from homemate.demo_scripts import DEMO_SCRIPTS, script_ids


def test_all_scripts_pass_offline() -> None:
    runner = DemoBatchRunner()
    results = runner.run_many()
    assert len(results) == len(script_ids())
    assert all(r.ok for r in results), [
        (r.script_id, r.error, [c for c in r.checks if not c.ok]) for r in results if not r.ok
    ]


def test_run_single_script() -> None:
    r = run_script(DEMO_SCRIPTS["sad_talk"])
    assert r.ok
    assert "find_owner" in r.tools_used
    assert "read_emotion" in r.tools_used
    assert "speak" in r.tools_used


def test_format_table_nonempty() -> None:
    runner = DemoBatchRunner()
    text = format_table(runner.run_many(["tired_coffee"]))
    assert "tired_coffee" in text
    assert "OK" in text
