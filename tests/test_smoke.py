"""End-to-end smoke test that doesn't need Pygame, Anthropic, or a webcam.

Run with::

    python -m pytest tests/ -q
"""

from __future__ import annotations

import random

from homemate.action.skills import Skills
from homemate.cognition.llm_agent import MockLLM
from homemate.cognition.tools import TOOL_SCHEMAS, dispatch_tool
from homemate.perception.emotion import MockEmotionDetector
from homemate.planning.navigator import astar
from homemate.planning.search import OwnerSearchPolicy, time_of_day
from homemate.world.apartment import Apartment
from homemate.world.entities import Owner, Robot, place_in_room
from homemate.world.iot import IoTNetwork


# ---- world ----

def test_apartment_geometry() -> None:
    apt = Apartment()
    assert set(apt.room_names()) == {"living_room", "kitchen", "bedroom", "bathroom"}
    # walls are not walkable, doors are
    for (x, y) in apt.doors():
        assert apt.is_walkable(x, y), f"door {(x, y)} should be walkable"
    # each room center is inside the right room
    for name in apt.room_names():
        cx, cy = apt.room(name).center
        assert apt.room_name_at(cx, cy) == name


def test_iot_actions() -> None:
    net = IoTNetwork.default()
    res = net.act("curtain.bedroom", "open")
    assert res["ok"] and res["state"]["open"] is True
    res = net.act("toaster.kitchen", "start", level=4)
    assert res["ok"] and res["state"]["running"]
    # ticking advances cook progress
    net.tick(2.0)
    assert net.get("toaster.kitchen").state["progress"] > 0


# ---- planning ----

def test_astar_reaches_every_room() -> None:
    apt = Apartment()
    start = apt.room("living_room").center
    for room in apt.room_names():
        goal = apt.room(room).center
        path = astar(apt, start, goal)
        assert path, f"unreachable: {room}"
        assert path[0] == start and path[-1] == goal


def test_search_policy_excludes_current_room() -> None:
    apt = Apartment()
    p = OwnerSearchPolicy(apt.room_names())
    order = p.ordering(current_room="kitchen")
    assert "kitchen" not in order
    assert set(order) == set(apt.room_names()) - {"kitchen"}
    assert time_of_day() in {"morning", "afternoon", "evening", "night"}


# ---- tools dispatch ----

def _make_skills(seed: int = 1) -> Skills:
    rng = random.Random(seed)
    apt = Apartment()
    robot = Robot(0, 0)
    owner = Owner(0, 0)
    place_in_room(robot, apt, "living_room", rng)
    place_in_room(owner, apt, "bedroom", rng)
    iot = IoTNetwork.default()
    emotion = MockEmotionDetector()
    emotion.start()
    emotion.inject("sad")
    return Skills(apt, robot, owner, iot, emotion)


def test_tool_dispatch_full_loop() -> None:
    skills = _make_skills()
    # look_around: starts in living_room, owner is not here
    out = dispatch_tool(skills, "look_around", {})
    assert out["ok"] and out["robot_room"] == "living_room"
    assert out["owner_in_this_room"] is False

    # find_owner: should locate them in the bedroom
    out = dispatch_tool(skills, "find_owner", {})
    assert out["ok"] and out["owner_room"] == "bedroom"
    assert skills.robot_room() == "bedroom"

    # read_emotion should report sad
    out = dispatch_tool(skills, "read_emotion", {})
    assert out["ok"] and out["emotion"] == "sad"

    # speak
    out = dispatch_tool(skills, "speak", {"text": "Hi, I'm here."})
    assert out["ok"]
    assert skills.dialogue[-1] == ("robot", "Hi, I'm here.")

    # set_device
    out = dispatch_tool(skills, "set_device",
                        {"device_id": "curtain.bedroom", "action": "open"})
    assert out["ok"] and out["state"]["open"] is True


def test_mockllm_runs_scenario() -> None:
    skills = _make_skills()
    skills.emotion.inject("tired")
    agent = MockLLM(skills)
    res = agent.run_turn("I'm tired, can you start the coffee maker?")
    # MockLLM should have found the owner, spoken something, and brewed coffee
    assert any(t["name"] == "find_owner" for t in res.tool_trace)
    assert any(t["name"] == "speak" for t in res.tool_trace)
    coffee_calls = [t for t in res.tool_trace
                    if t["name"] == "set_device" and t["input"].get("device_id") == "coffee.kitchen"]
    assert coffee_calls, "expected the agent to brew coffee"
    assert skills.iot.get("coffee.kitchen").state["brewing"] is True


def test_tool_schemas_well_formed() -> None:
    names = [t["name"] for t in TOOL_SCHEMAS]
    assert len(names) == len(set(names))
    for t in TOOL_SCHEMAS:
        assert "input_schema" in t and t["input_schema"]["type"] == "object"
