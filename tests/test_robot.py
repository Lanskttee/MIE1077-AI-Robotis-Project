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


def test_deliver_keeps_inventory_if_owner_unreachable() -> None:
    skills = _setup(owner_room="bedroom")
    skills.inventory = ["coffee"]
    # Force find_owner to fail by clearing apartment rooms from belief path —
    # simplest: put owner in an invalid state via monkeying room check.
    skills.owner.x, skills.owner.y = -10, -10  # off-map → never visible / no path
    out = dispatch_tool(skills, "deliver_item", {})
    assert out["ok"] is False
    assert skills.inventory == ["coffee"]


def test_follow_owner_step_chases_moving_owner() -> None:
    apt = Apartment()
    robot = Robot(0, 0)
    owner = Owner(0, 0)
    place_in_room(robot, apt, "living_room", None)
    place_in_room(owner, apt, "living_room", None)
    ctrl = RobotController(apt, robot, owner, IoTNetwork.default())
    pending: list[tuple[int, int]] = []

    # Not following yet -> no-op.
    assert ctrl.follow_owner_step(pending) is None

    # Enable follow (as find_owner would) and move the owner far away.
    ctrl.tracker.enable_owner_tracking(owner_pos=owner.pos)
    place_in_room(owner, apt, "bedroom", None)
    res = ctrl.follow_owner_step(pending)
    assert res is not None and res["ok"] and res["replanned"]
    assert len(pending) > 0
    assert ctrl.metrics.replan_count > 0

    # Walk the queued path; robot should end within interaction range.
    for tile in list(pending):
        robot.x, robot.y = tile
    pending.clear()
    assert can_interact(robot.pos, owner.pos)
    # Already adjacent -> no further movement queued.
    assert ctrl.follow_owner_step(pending) is None
    assert pending == []


def test_follow_owner_step_never_targets_owner_tile() -> None:
    apt = Apartment()
    robot = Robot(0, 0)
    owner = Owner(0, 0)
    place_in_room(robot, apt, "living_room", None)
    place_in_room(owner, apt, "kitchen", None)
    ctrl = RobotController(apt, robot, owner, IoTNetwork.default())
    ctrl.tracker.enable_owner_tracking(owner_pos=owner.pos)
    pending: list[tuple[int, int]] = []
    res = ctrl.follow_owner_step(pending)
    assert res is not None and res["ok"]
    assert owner.pos not in pending


def test_pickup_and_deliver_coffee() -> None:
    skills = _setup(owner_room="bedroom")
    skills.emotion.inject("tired")
    dispatch_tool(skills, "navigate_to_device", {"device_id": "coffee.kitchen"})
    dispatch_tool(skills, "set_device", {"device_id": "coffee.kitchen", "action": "brew"})
    coffee = skills.iot.get("coffee.kitchen")
    assert coffee is not None
    # Skip brew animation: mark ready cups for pickup.
    coffee.state["brewing"] = False
    coffee.state["cups"] = 1
    coffee.state["progress"] = 1.0
    pick = dispatch_tool(skills, "pickup_item", {"device_id": "coffee.kitchen"})
    assert pick["ok"] is True
    assert "coffee" in skills.inventory or pick.get("picked_up")
    deliver = dispatch_tool(skills, "deliver_item", {})
    assert deliver["ok"] is True
    assert skills.inventory == []
