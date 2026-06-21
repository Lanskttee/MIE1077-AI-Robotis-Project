"""Tests for multi-goal route optimization."""

from __future__ import annotations

from homemate.action.skills import Skills
from homemate.perception.emotion import MockEmotionDetector
from homemate.robot.route_optimizer import RouteOptimizer
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


def test_route_optimizer_orders_devices() -> None:
    apt = Apartment()
    iot = IoTNetwork.default()
    ro = RouteOptimizer(apt)
    route = ro.plan(
        ["coffee.kitchen", "lamp.bedroom", "thermostat.living_room"],
        iot, (6, 6),
    )
    assert len(route.stops) == 3
    assert len(route.device_order()) == 3
    assert route.total_cost >= 0


def test_plan_device_route_tool() -> None:
    skills = _skills()
    from homemate.cognition.tools import dispatch_tool
    out = dispatch_tool(skills, "plan_device_route", {
        "device_ids": ["coffee.kitchen", "lamp.living_room"],
    })
    assert out["ok"]
    assert "route" in out
    assert len(out["route"]["device_order"]) == 2


def test_visit_devices_navigates() -> None:
    skills = _skills()
    from homemate.cognition.tools import dispatch_tool
    out = dispatch_tool(skills, "visit_devices", {
        "device_ids": ["thermostat.living_room", "lamp.living_room"],
    })
    assert out["ok"]
    assert len(out["visited_order"]) == 2
    assert skills.robot_ctrl.metrics.total_tiles > 0
