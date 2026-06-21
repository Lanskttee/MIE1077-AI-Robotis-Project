"""CLI benchmark for robot navigation and coverage planning.

Prints per-room coverage costs, belief demo, planner comparison, and
multi-device route optimization.

Run::

    python -m homemate.robot
"""

from __future__ import annotations

import sys

from ..planning.costmap import compare_planners
from ..planning.search import OwnerSearchPolicy
from ..world.apartment import Apartment
from ..world.entities import Owner, Robot, place_in_room
from ..world.iot import IoTNetwork
from .belief import OwnerBelief
from .coverage import CoveragePlanner
from .route_optimizer import RouteOptimizer


def main() -> int:
    apt = Apartment()
    robot = Robot(0, 0)
    owner = Owner(0, 0)
    iot = IoTNetwork.default()
    place_in_room(robot, apt, "living_room", None)
    place_in_room(owner, apt, "bedroom", None)
    cp = CoveragePlanner(apt, stride=2)
    belief = OwnerBelief(apt.room_names())
    policy = OwnerSearchPolicy(apt.room_names())

    print("HomeMate robot bench — coverage + belief + costmap + routing\n")
    print(f"Robot: {robot.pos}  Owner: {owner.pos}\n")

    print(f"{'Room':<14} {'Walkable':>8} {'Waypoints':>10} {'SweepCost':>10}")
    print("-" * 46)
    for room in apt.room_names():
        tiles = cp.walkable_tiles(room)
        wps = cp.waypoints(room)
        cost = cp.estimate_scan_cost(room, robot.pos, owner_pos=owner.pos)
        print(f"{room:<14} {len(tiles):>8} {len(wps):>10} {cost:>10}")

    print("\nPlanner comparison living_room -> kitchen:")
    kitchen_center = apt.room("kitchen").center
    cmp = compare_planners(apt, robot.pos, kitchen_center, owner_pos=owner.pos)
    print(f"  plain A* steps:    {cmp['plain_steps']}")
    print(f"  plain turns:       {cmp['plain_turns']}")
    cm = cmp["costmap"]
    assert isinstance(cm, dict)
    print(f"  costmap steps:     {cm.get('tile_steps')}")
    print(f"  costmap turns:     {cm.get('turn_count')}")
    print(f"  costmap total:     {cm.get('total_cost')}")
    print(f"  planner:           {cm.get('planner')}")

    print("\nMulti-device route (coffee + lamp + thermostat):")
    ro = RouteOptimizer(apt)
    route = ro.plan(
        ["coffee.kitchen", "lamp.bedroom", "thermostat.living_room"],
        iot, robot.pos, owner_pos=owner.pos,
    )
    print(f"  order: {' -> '.join(route.device_order())}")
    print(f"  est. cost: {route.total_cost}  method: {route.method}")

    print("\nBelief demo (observe bedroom: owner seen):")
    belief.observe("bedroom", True)
    for room in belief.rank_rooms():
        print(f"  P({room}) = {belief.probs[room]:.3f}")

    print("\nMerged search order from living_room:")
    order = belief.merge_search_order(policy, "living_room")
    print("  " + " -> ".join(order))
    return 0


if __name__ == "__main__":
    sys.exit(main())
