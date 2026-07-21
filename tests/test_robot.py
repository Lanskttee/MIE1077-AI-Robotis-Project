"""Tests for the robot motion / belief / coverage layer."""

from __future__ import annotations

from homemate.action.skills import Skills
from homemate.cognition.tools import dispatch_tool
from homemate.perception.emotion import MockEmotionDetector
from homemate.robot.belief import OwnerBelief
from homemate.robot.controller import RobotController
from homemate.robot.coverage import CoveragePlanner
from homemate.robot.kinematics import can_interact, device_tile, nearest_dock
from homemate.world.apartment import Apartment
from homemate.world.entities import Owner, Robot, place_in_room
from homemate.world.iot import IoTNetwork


def _setup(owner_room: str = "bedroom") -> Skills:
    apt = Apartment()
    robot = Robot(0, 0)
    owner = Owner(0, 0)
    place_in_room(robot, apt, "living_room", None)
    place_in_room(owner, apt, owner_room, None)
    emo = MockEmotionDetector()
    emo.start()
    return Skills(apt, robot, owner, IoTNetwork.default(), emo)


def test_belief_updates_on_observation() -> None:
    belief = OwnerBelief(["living_room", "bedroom", "kitchen", "bathroom"])
    belief.observe("bedroom", True)
    assert belief.rank_rooms()[0] == "bedroom"
    belief.observe("kitchen", False)
    assert belief.probs["kitchen"] < belief.probs["bedroom"]


def test_coverage_waypoints_cover_room() -> None:
    apt = Apartment()
    cp = CoveragePlanner(apt, stride=2)
    wps = cp.waypoints("kitchen")
    assert len(wps) >= 4
    room = apt.room("kitchen")
    for x, y in wps:
        assert room.contains(x, y)


def test_navigate_to_device_reaches_interaction_range() -> None:
    skills = _setup()
    out = dispatch_tool(skills, "navigate_to_device", {"device_id": "coffee.kitchen"})
    assert out["ok"]
    assert out.get("in_interaction_range") is True
    dev = skills.iot.get("coffee.kitchen")
    assert dev is not None
    tile = device_tile(skills.apt, dev)
    assert can_interact(skills.robot.pos, tile)


def test_set_device_auto_navigates_when_out_of_range() -> None:
    skills = _setup()
    out = dispatch_tool(skills, "set_device",
                        {"device_id": "coffee.kitchen", "action": "brew"})
    assert out["ok"] is True
    dev = skills.iot.get("coffee.kitchen")
    assert dev is not None
    tile = device_tile(skills.apt, dev)
    assert can_interact(skills.robot.pos, tile)


def test_find_owner_uses_belief_metadata() -> None:
    skills = _setup(owner_room="bedroom")
    skills.emotion.inject("sad")
    out = dispatch_tool(skills, "find_owner", {})
    assert out["ok"]
    assert out["owner_room"] == "bedroom"
    assert "belief" in out
    assert out.get("method") in ("already_here", "belief_sweep", "coverage_scan")


def test_scan_room_and_robot_state_tools() -> None:
    skills = _setup()
    state = dispatch_tool(skills, "get_robot_state", {})
    assert state["ok"]
    assert "pose" in state
    assert "motion" in state
    scan = dispatch_tool(skills, "scan_room", {"room": "living_room"})
    assert scan["ok"]
    assert scan["tiles_scanned"] >= 0


def test_robot_controller_odometry() -> None:
    apt = Apartment()
    robot = Robot(0, 0)
    owner = Owner(0, 0)
    place_in_room(robot, apt, "living_room", None)
    ctrl = RobotController(apt, robot, owner, IoTNetwork.default())
    pending: list[tuple[int, int]] = []
    out = ctrl.navigate_to_room_center("kitchen", pending)
    assert out["ok"]
    assert ctrl.metrics.total_tiles > 0
    assert len(pending) > 0


def test_nearest_dock_prefers_reachable_tile() -> None:
    apt = Apartment()
    robot = Robot(0, 0)
    place_in_room(robot, apt, "living_room", None)
    iot = IoTNetwork.default()
    dev = iot.get("coffee.kitchen")
    assert dev is not None
    tile = device_tile(apt, dev)
    dock = nearest_dock(apt, robot.pos, tile)
    assert dock is not None
    assert apt.is_walkable(*dock)
