"""Occupancy grid map and frontier-based exploration.

Maintains a partial map of the apartment: unknown / free / occupied cells.
The robot reveals walkable tiles in rooms it enters (range-limited sensor model)
and selects **frontier** cells (unknown adjacent to known free) for exploration.

Classic mobile-robotics active mapping used to augment owner search.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..planning.costmap import PlannerConfig, astar_costmap
from ..planning.navigator import Coord, _manhattan
from ..world.apartment import Apartment

UNKNOWN = -1
FREE = 0
OCCUPIED = 1


@dataclass
class OccupancyGrid:
    """Partial grid map over the apartment walkable cells."""

    apt: Apartment
    cells: dict[Coord, int] = field(default_factory=dict)
    reveal_radius: int = 4
    frontiers_visited: int = 0

    def get(self, x: int, y: int) -> int:
        if not self.apt.in_bounds(x, y):
            return OCCUPIED
        if not self.apt.is_walkable(x, y):
            return OCCUPIED
        return self.cells.get((x, y), UNKNOWN)

    def reveal_from_pose(self, robot_pos: Coord, *, owner_pos: Coord | None = None) -> int:
        """Mark nearby walkable tiles as free; owner tile as occupied if visible."""
        rx, ry = robot_pos
        room = self.apt.room_at(rx, ry)
        revealed = 0
        for dx in range(-self.reveal_radius, self.reveal_radius + 1):
            for dy in range(-self.reveal_radius, self.reveal_radius + 1):
                if abs(dx) + abs(dy) > self.reveal_radius:
                    continue
                x, y = rx + dx, ry + dy
                if not self.apt.is_walkable(x, y):
                    self.cells[(x, y)] = OCCUPIED
                    continue
                if room is not None and not room.contains(x, y):
                    continue
                if self.cells.get((x, y), UNKNOWN) == UNKNOWN:
                    revealed += 1
                self.cells[(x, y)] = FREE
        if owner_pos is not None:
            ox, oy = owner_pos
            oroom = self.apt.room_at(ox, oy)
            if room is not None and oroom == room:
                self.cells[(ox, oy)] = OCCUPIED
        return revealed

    def frontiers(self) -> list[Coord]:
        """Unknown cells 4-adjacent to a known-free cell."""
        out: list[Coord] = []
        seen: set[Coord] = set()
        for (fx, fy), state in list(self.cells.items()):
            if state != FREE:
                continue
            for nx, ny in ((fx + 1, fy), (fx - 1, fy), (fx, fy + 1), (fx, fy - 1)):
                if (nx, ny) in seen:
                    continue
                if self.get(nx, ny) == UNKNOWN:
                    seen.add((nx, ny))
                    out.append((nx, ny))
        return out

    def nearest_frontier(self, from_pos: Coord,
                         *, owner_pos: Coord | None = None) -> Coord | None:
        """Pick the reachable frontier with minimum costmap path cost."""
        cfg = PlannerConfig()
        best: Coord | None = None
        best_cost = 1 << 30
        for frontier in self.frontiers():
            plan = astar_costmap(self.apt, from_pos, frontier,
                                 owner_pos=owner_pos, config=cfg)
            if plan.path and plan.total_cost < best_cost:
                best_cost = plan.total_cost
                best = frontier
        return best

    def coverage_ratio(self) -> float:
        """Fraction of walkable tiles marked free."""
        walkable = sum(
            1 for x in range(self.apt.cols) for y in range(self.apt.rows)
            if self.apt.is_walkable(x, y)
        )
        if walkable == 0:
            return 0.0
        known_free = sum(1 for v in self.cells.values() if v == FREE)
        return round(known_free / walkable, 3)

    def snapshot(self) -> dict[str, Any]:
        return {
            "known_cells": len(self.cells),
            "free_cells": sum(1 for v in self.cells.values() if v == FREE),
            "occupied_cells": sum(1 for v in self.cells.values() if v == OCCUPIED),
            "frontier_count": len(self.frontiers()),
            "coverage_ratio": self.coverage_ratio(),
            "frontiers_visited": self.frontiers_visited,
        }

    def manhattan_to_nearest_unknown(self, from_pos: Coord) -> int | None:
        unknowns = [c for c, v in self.cells.items() if v == UNKNOWN]
        unknowns.extend(self.frontiers())
        if not unknowns:
            return None
        return min(_manhattan(from_pos, u) for u in unknowns)
