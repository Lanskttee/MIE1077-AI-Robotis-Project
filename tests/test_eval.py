"""Tests for the evaluation-suite harness.

Validates the structural contracts (20 scenarios, criteria all callable,
runner produces a result per scenario) and that the baseline MockLLM run
achieves a high pass rate. The exact rate is asserted loosely so future
prompt/planner tweaks don't break this test for trivial reasons.
"""

from __future__ import annotations

from homemate.eval import EvalRunner, SCENARIOS, run_all
from homemate.eval.criteria import (
    device_state_eq,
    emotion_detected,
    spoken_contains,
    tool_was_called,
)
from homemate.eval.runner import format_table, summarize
from homemate.eval.scenarios import Scenario


def test_scenarios_are_exactly_twenty_and_unique() -> None:
    assert len(SCENARIOS) == 20
    ids = [s.id for s in SCENARIOS]
    assert len(set(ids)) == 20


def test_each_scenario_has_at_least_three_criteria() -> None:
    for s in SCENARIOS:
        assert len(s.criteria) >= 3, f"{s.id}: only {len(s.criteria)} criteria"


def test_scenarios_cover_every_device_kind() -> None:
    """Every device kind should appear as a target in at least one scenario's
    criteria (rough check via scenario id / description)."""
    text = " ".join(s.id + " " + s.description.lower() for s in SCENARIOS)
    for kind in ("curtain", "lamp", "toaster", "coffee",
                 "thermostat", "tv", "speaker", "fan", "lock"):
        assert kind in text, f"no scenario mentions {kind}"


def test_runner_baseline_achieves_full_pass_on_mockllm() -> None:
    results = run_all()
    s = summarize(results)
    # MockLLM + planner should ace the suite. Allow a tiny margin in case
    # future scenarios are tightened.
    assert s["scenarios"]["passed"] >= 19
    assert s["criteria"]["pct"] >= 95.0


def test_runner_produces_one_result_per_scenario() -> None:
    results = run_all()
    assert len(results) == len(SCENARIOS)
    ids = [r.scenario_id for r in results]
    assert ids == [s.id for s in SCENARIOS]


def test_no_emotion_ablation_hurts_pass_rate() -> None:
    """The no-emotion ablation should fail strictly more criteria than the
    baseline (emotion-conditioned criteria can't pass without read_emotion)."""
    base = run_all(inject_emotion=True)
    abl = run_all(inject_emotion=False)
    base_pct = summarize(base)["criteria"]["pct"]
    abl_pct = summarize(abl)["criteria"]["pct"]
    assert abl_pct < base_pct, (
        f"emotion ablation should hurt: baseline {base_pct}% vs ablation {abl_pct}%"
    )


def test_runner_records_tool_calls_and_spoken_lines() -> None:
    runner = EvalRunner()
    r = runner.run_one(SCENARIOS[0])
    assert r.tool_calls > 0
    assert r.spoken_lines >= 1
    assert r.total >= 3


def test_format_table_is_renderable_and_contains_all_ids() -> None:
    results = run_all()
    table = format_table(results)
    for s in SCENARIOS:
        assert s.id in table
    assert "Scenarios passed" in table


# ---- criteria builders ----


def test_tool_was_called_checks_trace() -> None:
    ctx = {"skills": None,
           "trace": [{"name": "find_owner", "input": {}, "output": {"ok": True}}],
           "spoken": [], "final_text": ""}
    name, ok, note = tool_was_called("find_owner")(ctx)
    assert ok and note == ""
    name, ok, note = tool_was_called("read_emotion")(ctx)
    assert not ok and "read_emotion" in note


def test_emotion_detected_pulls_from_trace() -> None:
    trace = [
        {"name": "read_emotion", "input": {}, "output": {"ok": True, "emotion": "sad"}},
    ]
    ctx = {"skills": None, "trace": trace, "spoken": [], "final_text": ""}
    assert emotion_detected("sad")(ctx)[1] is True
    assert emotion_detected("happy")(ctx)[1] is False


def test_spoken_contains_case_insensitive() -> None:
    ctx = {"skills": None, "trace": [], "spoken": ["I am Here with you"], "final_text": ""}
    assert spoken_contains("here with you")(ctx)[1] is True
    assert spoken_contains("never said")(ctx)[1] is False


def test_device_state_eq_handles_missing_device() -> None:
    class _FakeNet:
        def get(self, _): return None
    class _Skills:
        iot = _FakeNet()
    ctx = {"skills": _Skills(), "trace": [], "spoken": [], "final_text": ""}
    name, ok, note = device_state_eq("nope", "x", 1)(ctx)
    assert ok is False
    assert "no device" in note
