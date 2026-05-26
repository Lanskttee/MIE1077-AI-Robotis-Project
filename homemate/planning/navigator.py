"""A* navigation over the apartment grid + path-following helper."""

from __future__ import annotations

import heapq
from typing import Optional

from ..world.apartment import Apartment


Coord = tuple[int, int]


def _manhattan(a: Coord, b: Coord) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _neighbors(pos: Coord) -> list[Coord]:
    x, y = pos
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]


def astar(apt: Apartment, start: Coord, goal: Coord) -> list[Coord]:
    """4-connected A* on walkable tiles. Returns [] if unreachable.

    The returned path *includes* both start and goal.
    """
    if start == goal:
        return [start]
    if not apt.is_walkable(*goal):
        return []

    open_heap: list[tuple[int, int, Coord]] = []
    counter = 0
    heapq.heappush(open_heap, (0, counter, start))
    came_from: dict[Coord, Coord] = {}
    g_score: dict[Coord, int] = {start: 0}

    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        if current == goal:
            # reconstruct
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path
        for nb in _neighbors(current):
            if not apt.is_walkable(*nb):
                continue
            tentative = g_score[current] + 1
            if tentative < g_score.get(nb, 1 << 30):
                came_from[nb] = current
                g_score[nb] = tentative
                f = tentative + _manhattan(nb, goal)
                counter += 1
                heapq.heappush(open_heap, (f, counter, nb))
    return []


class Navigator:
    """Holds a current path for the robot and advances one tile per ``step``."""

    def __init__(self, apt: Apartment) -> None:
        self.apt = apt
        self._path: list[Coord] = []
        self._idx = 0
        self.goal: Optional[Coord] = None

    def set_goal(self, start: Coord, goal: Coord) -> bool:
        path = astar(self.apt, start, goal)
        if not path:
            self._path = []
            self.goal = None
            return False
        self._path = path
        self._idx = 0
        self.goal = goal
        return True

    def has_path(self) -> bool:
        return self._idx + 1 < len(self._path)

    def peek_next(self) -> Optional[Coord]:
        if not self.has_path():
            return None
        return self._path[self._idx + 1]

    def step(self) -> Optional[Coord]:
        """Return the next tile to move to (and advance), or None if done."""
        nxt = self.peek_next()
        if nxt is None:
            return None
        self._idx += 1
        return nxt

    def remaining_path(self) -> list[Coord]:
        return list(self._path[self._idx:])

    def clear(self) -> None:
        self._path = []
        self._idx = 0
        self.goal = None
