"""Tests for occupancy grid and frontier exploration."""

from __future__ import annotations

from homemate.action.skills import Skills
from homemate.perception.emotion import MockEmotionDetector
from homemate.robot.occupancy import FREE, OccupancyGrid, UNKNOWN
from homemate.world.apartment import Apartment
from homemate.world.entities import Owner, Robot, place_in_room
from homemate.world.iot import IoTNetwork


def _skills() -> Skills:
    apt = Apartment()
    robot = Robot(0, 0)
    owner = Owner(0, 0)
    place_in_room(robot, apt, "living_room", None)
    place_in_room(owner, apt, "bedroom", None)
    emo = MockEmotionDetector()
    emo.start()
    return Skills(apt, robot, owner, IoTNetwork.default(), emo)


def test_reveal_from_pose_marks_free_tiles() -> None:
    apt = Apartment()
    og = OccupancyGrid(apt, reveal_radius=5)
    n = og.reveal_from_pose((6, 6))
    assert n > 0
    assert og.get(6, 6) == FREE
    assert og.coverage_ratio() > 0


def test_frontiers_after_partial_reveal() -> None:
    apt = Apartment()
    og = OccupancyGrid(apt, reveal_radius=2)
    og.reveal_from_pose((6, 6))
    frontiers = og.frontiers()
    assert isinstance(frontiers, list)
    for fx, fy in frontiers:
        assert og.get(fx, fy) == UNKNOWN


def test_explore_frontier_tool() -> None:
    skills = _skills()
    from homemate.cognition.tools import dispatch_tool
    out = dispatch_tool(skills, "explore_frontier", {"max_hops": 1})
    assert out["ok"]
    assert "map" in out


def test_map_in_robot_state() -> None:
    skills = _skills()
    skills.robot_ctrl.update_map()
    snap = skills.robot_ctrl.map.snapshot()
    assert snap["known_cells"] > 0
    assert "coverage_ratio" in snap
