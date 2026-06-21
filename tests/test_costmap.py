"""Tests for costmap A* and dynamic replanning."""

from __future__ import annotations

from homemate.action.skills import Skills
from homemate.perception.emotion import MockEmotionDetector
from homemate.planning.costmap import PlannerConfig, astar_costmap, compare_planners
from homemate.planning.navigator import astar
from homemate.robot.path_tracker import PathTracker
from homemate.world.apartment import Apartment
from homemate.world.entities import Owner, Robot, place_in_room
from homemate.world.iot import IoTNetwork


def _skills(owner_room: str = "bedroom") -> Skills:
    apt = Apartment()
    robot = Robot(0, 0)
    owner = Owner(0, 0)
    place_in_room(robot, apt, "living_room", None)
    place_in_room(owner, apt, owner_room, None)
    emo = MockEmotionDetector()
    emo.start()
    return Skills(apt, robot, owner, IoTNetwork.default(), emo)


def test_costmap_finds_path() -> None:
    apt = Apartment()
    start = (6, 6)
    goal = (18, 4)
    plan = astar_costmap(apt, start, goal)
    assert plan.path
    assert plan.path[0] == start
    assert plan.path[-1] == goal


def test_turn_penalty_can_change_path() -> None:
    apt = Apartment()
    start = (6, 6)
    goal = (10, 6)
    plain = astar(apt, start, goal)
    with_turns = astar_costmap(apt, start, goal, config=PlannerConfig(turn_penalty=5))
    assert plain
    assert with_turns.path
    assert with_turns.turn_count >= 0


def test_owner_tile_blocked() -> None:
    apt = Apartment()
    start = (6, 6)
    goal = (8, 6)
    owner = (7, 6)
    plan = astar_costmap(apt, start, goal, owner_pos=owner)
    assert plan.path
    assert plan.path[-1] == goal
    assert owner not in plan.path


def test_compare_planners_json() -> None:
    apt = Apartment()
    cmp = compare_planners(apt, (6, 6), (12, 10))
    assert "plain_steps" in cmp
    assert "costmap" in cmp


def test_path_tracker_owner_move() -> None:
    tr = PathTracker()
    tr.enable_owner_tracking()
    tr.observe_owner((5, 5))
    reason = tr.observe_owner((8, 8))
    assert reason == "owner_moved"


def test_replan_when_owner_blocks_next_tile() -> None:
    skills = _skills()
    goal = (10, 6)
    skills.robot_ctrl.tracker.register(goal, kind="tile", label="test")
    skills.pending_path = [(7, 6), (8, 6), (9, 6), (10, 6)]
    skills.owner.x, skills.owner.y = 7, 6
    reason = skills.robot_ctrl.check_replan_reason(skills.pending_path)
    assert reason == "owner_on_next_tile"
    res = skills.replan_if_needed(teleport=False)
    assert res is not None
    assert res.get("ok") is True
    assert res.get("replanned") is True
    assert skills.robot_ctrl.metrics.replan_count >= 1


def test_find_owner_enables_owner_tracking() -> None:
    skills = _skills(owner_room="bedroom")
    skills.emotion.inject("sad")
    from homemate.cognition.tools import dispatch_tool
    out = dispatch_tool(skills, "find_owner", {})
    assert out["ok"]
    assert skills.robot_ctrl.tracker.follow_owner is True


def test_telemetry_includes_path_tracker() -> None:
    skills = _skills()
    tel = skills.robot_ctrl.telemetry()
    assert "path_tracker" in tel
    assert "motion" in tel
    assert "map" in tel
    assert tel["motion"]["planner"] == "costmap_astar"
