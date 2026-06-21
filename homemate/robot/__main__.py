"""CLI benchmark for robot navigation and coverage planning.

Prints per-room coverage costs and a sample belief update trace — useful
for the robotics write-up (motion planning + localization sections).

Run::

    python -m homemate.robot
"""

from __future__ import annotations

import sys

from ..planning.search import OwnerSearchPolicy
from ..world.apartment import Apartment
from ..world.entities import Robot, place_in_room
from .belief import OwnerBelief
from .coverage import CoveragePlanner


def main() -> int:
    apt = Apartment()
    robot = Robot(0, 0)
    place_in_room(robot, apt, "living_room", None)
    cp = CoveragePlanner(apt, stride=2)
    belief = OwnerBelief(apt.room_names())
    policy = OwnerSearchPolicy(apt.room_names())

    print("HomeMate robot bench — coverage + belief\n")
    print(f"Start pose: {robot.pos}  room={apt.room_name_at(*robot.pos)}\n")
    print(f"{'Room':<14} {'Walkable':>8} {'Waypoints':>10} {'SweepCost':>10}")
    print("-" * 46)
    for room in apt.room_names():
        tiles = cp.walkable_tiles(room)
        wps = cp.waypoints(room)
        cost = cp.estimate_scan_cost(room, robot.pos)
        print(f"{room:<14} {len(tiles):>8} {len(wps):>10} {cost:>10}")

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
