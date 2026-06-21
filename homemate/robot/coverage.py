"""Coverage planning — boustrophedon sweep waypoints inside a room."""

from __future__ import annotations

from ..planning.costmap import astar_costmap
from ..planning.navigator import Coord
from ..world.apartment import Apartment


class CoveragePlanner:
    """Generate systematic search waypoints for room exploration."""

    def __init__(self, apt: Apartment, *, stride: int = 2) -> None:
        self.apt = apt
        self.stride = max(1, stride)

    def walkable_tiles(self, room_name: str) -> list[Coord]:
        room = self.apt.room(room_name)
        return [
            (x, y)
            for x in range(room.x0, room.x1 + 1)
            for y in range(room.y0, room.y1 + 1)
            if self.apt.is_walkable(x, y)
        ]

    def waypoints(self, room_name: str) -> list[Coord]:
        """Boustrophedon ordering of room tiles (snake pattern by row)."""
        tiles = self.walkable_tiles(room_name)
        by_row: dict[int, list[int]] = {}
        for x, y in tiles:
            by_row.setdefault(y, []).append(x)
        out: list[Coord] = []
        for i, y in enumerate(sorted(by_row)):
            xs = sorted(by_row[y])[:: self.stride]
            if i % 2 == 1:
                xs = list(reversed(xs))
            out.extend((x, y) for x in xs)
        return out

    def plan_sweep(self, room_name: str, start: Coord,
                   *, owner_pos: Coord | None = None) -> list[Coord]:
        """Full path visiting coverage waypoints, starting from ``start``."""
        wps = self.waypoints(room_name)
        if not wps:
            return [start]
        path: list[Coord] = [start]
        cur = start
        for wp in wps:
            if wp == cur:
                continue
            plan = astar_costmap(self.apt, cur, wp, owner_pos=owner_pos)
            segment = plan.path
            if segment and len(segment) > 1:
                path.extend(segment[1:])
                cur = wp
        return path

    def estimate_scan_cost(self, room_name: str, start: Coord,
                           *, owner_pos: Coord | None = None) -> int:
        return max(0, len(self.plan_sweep(room_name, start, owner_pos=owner_pos)) - 1)
