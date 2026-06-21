"""Motion metrics and path cost accounting."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..planning.navigator import Coord


@dataclass
class MotionMetrics:
    """Cumulative odometry-style counters for the robot."""

    total_tiles: int = 0
    navigation_count: int = 0
    scan_tiles: int = 0
    replan_count: int = 0
    turn_count: int = 0
    last_path_cost: int = 0
    last_goal: Coord | None = None
    last_planner: str = "costmap_astar"

    def record_path(self, path: list[Coord], *, cost: int | None = None,
                    turns: int = 0, planner: str = "costmap_astar") -> int:
        steps = cost if cost is not None else max(0, len(path) - 1)
        self.last_path_cost = steps
        self.total_tiles += steps
        self.navigation_count += 1
        self.turn_count += turns
        self.last_planner = planner
        if path:
            self.last_goal = path[-1]
        return steps

    def record_replan(self) -> None:
        self.replan_count += 1

    def record_scan(self, tiles: int) -> None:
        self.scan_tiles += max(0, tiles)

    def to_json(self) -> dict[str, int | str | list[int] | None]:
        goal = None
        if self.last_goal is not None:
            goal = [self.last_goal[0], self.last_goal[1]]
        return {
            "total_tiles_traveled": self.total_tiles,
            "navigation_count": self.navigation_count,
            "scan_tiles": self.scan_tiles,
            "replan_count": self.replan_count,
            "turn_count": self.turn_count,
            "last_path_cost": self.last_path_cost,
            "last_goal": goal,
            "planner": self.last_planner,
        }
