"""Tests for the ReAct planner and PlanExecutor.

No webcam, no Pygame, no Anthropic — pure stdlib.
"""

from __future__ import annotations

import random

from homemate.action.skills import Skills
from homemate.cognition.llm_agent import MockLLM
from homemate.cognition.tools import TOOL_SCHEMAS, dispatch_tool
from homemate.perception.emotion import MockEmotionDetector
from homemate.planning.react import (
    EMPATHY,
    KIND_KEYWORDS,
    PlanExecutor,
    PlanStep,
    ReActPlanner,
    action_for,
)
from homemate.world.apartment import Apartment
from homemate.world.entities import Owner, Robot, place_in_room
from homemate.world.iot import IoTNetwork


def _make_skills(seed: int = 1, emotion: str = "sad") -> Skills:
    rng = random.Random(seed)
    apt = Apartment()
    robot = Robot(0, 0)
    owner = Owner(0, 0)
    place_in_room(robot, apt, "living_room", rng)
    place_in_room(owner, apt, "bedroom", rng)
    iot = IoTNetwork.default()
    emo = MockEmotionDetector()
    emo.start()
    emo.inject(emotion)
    return Skills(apt, robot, owner, iot, emo)


# ---- action_for: keyword-to-action mapping ----


def test_action_for_handles_off_inside_coffee_correctly() -> None:
    # Regression: bare 'off' must not match inside 'coffee'.
    action, kwargs = action_for("thermostat",
                                "Set the thermostat to 24 degrees, brew coffee")
    assert action == "set_target"
    assert kwargs == {"target_c": 24.0}


def test_action_for_curtain_open_close() -> None:
    assert action_for("curtain", "open the curtains")    == ("open", {})
    assert action_for("curtain", "close the curtains")   == ("close", {})
    assert action_for("curtain", "shut the curtains")    == ("close", {})
    assert action_for("curtain", "the curtains")         == ("toggle", {})


def test_action_for_lamp_dim_and_brightness() -> None:
    action, kwargs = action_for("lamp", "dim the bedroom lamp")
    assert action == "set_brightness" and kwargs == {"brightness": 0.3}
    action, kwargs = action_for("lamp", "brighten the lamp")
    assert action == "set_brightness" and kwargs == {"brightness": 1.0}
    assert action_for("lamp", "turn off the lamp")[0] == "off"
    assert action_for("lamp", "lamp on")[0] == "on"


def test_action_for_speaker_playlist_match() -> None:
    assert action_for("speaker", "play rain on the speaker") == \
        ("play", {"playlist": "rain"})
    assert action_for("speaker", "play calm music") == \
        ("play", {"playlist": "calm"})
    assert action_for("speaker", "stop the music") == ("stop", {})


def test_action_for_thermostat_modes() -> None:
    assert action_for("thermostat", "warm it up")[0] == "set_mode"
    assert action_for("thermostat", "warm it up")[1] == {"mode": "heat"}
    assert action_for("thermostat", "turn on the AC")[1] == {"mode": "cool"}
    assert action_for("thermostat", "turn off the thermostat")[0] == "off"


def test_action_for_unknown_kind() -> None:
    assert action_for("dishwasher", "wash the dishes") == (None, {})


# ---- planner: decomposition ----


def test_plan_always_starts_with_find_owner_and_sense_emotion() -> None:
    sk = _make_skills()
    plan = ReActPlanner().plan("hello", skills=sk)
    kinds = [s.kind for s in plan.steps]
    assert kinds[0] == "find_owner"
    assert "sense_emotion" in kinds
    assert "speak" in kinds


def test_plan_skips_find_owner_when_already_with_owner() -> None:
    sk = _make_skills()
    # Teleport robot to the owner's room.
    sk.robot.x, sk.robot.y = sk.owner.pos
    sk.owner_found = True
    plan = ReActPlanner().plan("hello", skills=sk)
    kinds = [s.kind for s in plan.steps]
    assert "find_owner" not in kinds


def test_plan_decomposes_multi_action_request() -> None:
    sk = _make_skills()
    plan = ReActPlanner().plan(
        "Brew coffee and open the bedroom curtains",
        skills=sk,
    )
    kinds = [s.kind for s in plan.steps]
    actuate_steps = [s for s in plan.steps if s.kind == "actuate"]
    assert len(actuate_steps) == 2
    device_ids = {s.args["device_id"] for s in actuate_steps}
    assert device_ids == {"coffee.kitchen", "curtain.bedroom"}
    # Every actuate is preceded by a goto_device for the same device.
    for i, step in enumerate(plan.steps):
        if step.kind == "actuate":
            prev = plan.steps[i - 1]
            assert prev.kind == "goto_device"
            assert prev.args["device_id"] == step.args["device_id"]


def test_plan_deduplicates_by_kind() -> None:
    sk = _make_skills()
    # Both 'coffee' and 'brew' map to coffee_maker — should fire only once.
    plan = ReActPlanner().plan("brew the coffee", skills=sk)
    actuates = [s for s in plan.steps if s.kind == "actuate"
                and s.args.get("device_id") == "coffee.kitchen"]
    assert len(actuates) == 1


def test_plan_prefers_device_in_named_room() -> None:
    sk = _make_skills()
    plan = ReActPlanner().plan("open the living room curtains", skills=sk)
    actuates = [s for s in plan.steps if s.kind == "actuate"]
    assert len(actuates) == 1
    assert actuates[0].args["device_id"] == "curtain.living_room"


def test_plan_to_json_round_trip_shape() -> None:
    sk = _make_skills()
    plan = ReActPlanner().plan("turn on the TV", skills=sk)
    blob = plan.to_json()
    assert blob["user_message"] == "turn on the TV"
    assert all(set(step.keys()) == {"kind", "args", "rationale"}
               for step in blob["steps"])


# ---- executor ----


def test_executor_executes_plan_against_real_skills() -> None:
    sk = _make_skills(emotion="sad")
    plan = ReActPlanner().plan("dim the bedroom lamp", skills=sk)
    res = PlanExecutor(sk).execute(plan)
    assert res.detected_emotion == "sad"
    assert any(t["name"] == "set_device" for t in res.tool_trace)
    assert sk.iot.get("lamp.bedroom").state["brightness"] == 0.3
    # spoke an empathy line
    assert any(EMPATHY["sad"].lower() in line.lower() for line in res.spoken)


# ---- MockLLM integration ----


def test_mockllm_with_planner_handles_three_actions() -> None:
    sk = _make_skills(emotion="sad")
    agent = MockLLM(sk)
    res = agent.run_turn(
        "Set the thermostat to 24, brew coffee, and dim the bedroom lamp"
    )
    set_calls = [t for t in res.tool_trace if t["name"] == "set_device"]
    targets = {t["input"]["device_id"] for t in set_calls}
    assert "thermostat.living_room" in targets
    assert "coffee.kitchen" in targets
    assert "lamp.bedroom" in targets
    assert sk.iot.get("thermostat.living_room").state["target_c"] == 24.0
    assert sk.iot.get("coffee.kitchen").state["brewing"] is True


def test_mockllm_no_planner_ablation_still_works() -> None:
    sk = _make_skills(emotion="tired")
    agent = MockLLM(sk, use_planner=False)
    res = agent.run_turn("brew coffee")
    assert any(t["name"] == "find_owner" for t in res.tool_trace)
    assert any(t["name"] == "read_emotion" for t in res.tool_trace)
    assert sk.iot.get("coffee.kitchen").state["brewing"] is True


# ---- make_plan tool dispatch ----


def test_make_plan_tool_schema_present_and_dispatched() -> None:
    assert any(t["name"] == "make_plan" for t in TOOL_SCHEMAS)
    sk = _make_skills()
    out = dispatch_tool(sk, "make_plan",
                        {"user_message": "open the bedroom curtains"})
    assert out["ok"] is True
    assert out["plan"]["user_message"] == "open the bedroom curtains"
    assert isinstance(out["plan"]["steps"], list)
    assert all("kind" in s for s in out["plan"]["steps"])


# ---- vocabulary completeness sanity ----


def test_every_iot_kind_has_at_least_one_keyword() -> None:
    """Every device kind in IoTNetwork.default() should be reachable by the
    planner from at least one keyword. Otherwise an entire device category
    would be inert to natural-language requests."""
    sk = _make_skills()
    reachable = set(KIND_KEYWORDS.values())
    for d in sk.iot.list():
        assert d.kind in reachable, f"no keyword maps to {d.kind!r}"
