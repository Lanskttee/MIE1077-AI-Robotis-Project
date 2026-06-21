"""Grid cost map and A* with turn penalties and dynamic obstacles.

Extends plain grid A* with:

* **Turn penalty** — state-space search over (x, y, incoming direction)
* **Dynamic obstacles** — owner tile blocked; adjacent tiles incur proximity cost
* **Room boundary cost** — small penalty crossing doors (encourages straight motion)

Used by :mod:`homemate.robot.controller` and benchmarked in
``python -m homemate.robot``.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass

from ..world.apartment import Apartment
from .navigator import Coord, _manhattan, astar

# 4-connected directions: E, W, S, N
_DIRS: tuple[Coord, ...] = ((1, 0), (-1, 0), (0, 1), (0, -1))
_NO_DIR = -1


@dataclass(frozen=True)
class PlannerConfig:
    turn_penalty: int = 2
    owner_proximity_cost: int = 4
    block_owner_tile: bool = True
    door_crossing_cost: int = 1


@dataclass
class PlanResult:
    path: list[Coord]
    tile_steps: int = 0
    turn_count: int = 0
    total_cost: int = 0
    planner: str = "costmap_astar"

    def to_json(self) -> dict[str, int | str | list[list[int]]]:
        return {
            "planner": self.planner,
            "tile_steps": self.tile_steps,
            "turn_count": self.turn_count,
            "total_cost": self.total_cost,
            "path_length": len(self.path),
            "path": [[x, y] for x, y in self.path],
        }


def _is_door_tile(apt: Apartment, x: int, y: int) -> bool:
    return apt.is_door(x, y)


def tile_cost(
    apt: Apartment,
    x: int,
    y: int,
    *,
    owner_pos: Coord | None,
    config: PlannerConfig,
) -> int | None:
    """Return step cost for tile, or ``None`` if impassable."""
    if not apt.is_walkable(x, y):
        return None
    if owner_pos is not None and (x, y) == owner_pos and config.block_owner_tile:
        return None
    cost = 1
    if owner_pos is not None:
        ox, oy = owner_pos
        if abs(x - ox) + abs(y - oy) == 1:
            cost += config.owner_proximity_cost
    if _is_door_tile(apt, x, y):
        cost += config.door_crossing_cost
    return cost


def astar_costmap(
    apt: Apartment,
    start: Coord,
    goal: Coord,
    *,
    owner_pos: Coord | None = None,
    config: PlannerConfig | None = None,
) -> PlanResult:
    """A* on (x, y, direction) with turn penalties and dynamic costs."""
    cfg = config or PlannerConfig()
    if start == goal:
        return PlanResult(path=[start], tile_steps=0, turn_count=0, total_cost=0)
    if tile_cost(apt, goal[0], goal[1], owner_pos=owner_pos, config=cfg) is None:
        return PlanResult(path=[])

    start_state = (start[0], start[1], _NO_DIR)
    open_heap: list[tuple[int, int, tuple[int, int, int]]] = []
    counter = 0
    heapq.heappush(open_heap, (0, counter, start_state))
    came_from: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    g_score: dict[tuple[int, int, int], int] = {start_state: 0}

    while open_heap:
        f, _, state = heapq.heappop(open_heap)
        x, y, in_dir = state
        if f > g_score[state] + _manhattan((x, y), goal):
            continue
        if (x, y) == goal:
            path: list[Coord] = []
            turns = 0
            cur = state
            while cur in came_from:
                cx, cy, cdir = cur
                path.append((cx, cy))
                prev = came_from[cur]
                if prev[2] not in (_NO_DIR, cdir):
                    turns += 1
                cur = prev
            path.append((cur[0], cur[1]))
            path.reverse()
            tile_steps = max(0, len(path) - 1)
            return PlanResult(
                path=path,
                tile_steps=tile_steps,
                turn_count=turns,
                total_cost=g_score[state],
            )
        for out_dir, (dx, dy) in enumerate(_DIRS):
            nx, ny = x + dx, y + dy
            step = tile_cost(apt, nx, ny, owner_pos=owner_pos, config=cfg)
            if step is None:
                continue
            turn = cfg.turn_penalty if in_dir not in (_NO_DIR, out_dir) else 0
            tentative = g_score[state] + step + turn
            nstate = (nx, ny, out_dir)
            if tentative < g_score.get(nstate, 1 << 30):
                came_from[nstate] = state
                g_score[nstate] = tentative
                f = tentative + _manhattan((nx, ny), goal)
                counter += 1
                heapq.heappush(open_heap, (f, counter, nstate))

    if owner_pos is not None and cfg.block_owner_tile:
        fallback = _astar_avoid(apt, start, goal, {owner_pos})
    else:
        fallback = astar(apt, start, goal)
    if not fallback:
        return PlanResult(path=[])
    return PlanResult(
        path=fallback,
        tile_steps=max(0, len(fallback) - 1),
        turn_count=_count_turns(fallback),
        total_cost=max(0, len(fallback) - 1),
        planner="astar_fallback",
    )


def _neighbors(pos: Coord) -> list[Coord]:
    x, y = pos
    return [(x + dx, y + dy) for dx, dy in _DIRS]


def _astar_avoid(apt: Apartment, start: Coord, goal: Coord,
                 blocked: set[Coord]) -> list[Coord]:
    """Plain A* treating ``blocked`` tiles as unwalkable."""
    if start == goal:
        return [start]
    if not apt.is_walkable(*goal) or goal in blocked:
        return []

    open_heap: list[tuple[int, int, Coord]] = []
    counter = 0
    heapq.heappush(open_heap, (0, counter, start))
    came_from: dict[Coord, Coord] = {}
    g_score: dict[Coord, int] = {start: 0}

    while open_heap:
        f, _, current = heapq.heappop(open_heap)
        if f > g_score[current] + _manhattan(current, goal):
            continue
        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path
        for nb in _neighbors(current):
            if not apt.is_walkable(*nb) or nb in blocked:
                continue
            tentative = g_score[current] + 1
            if tentative < g_score.get(nb, 1 << 30):
                came_from[nb] = current
                g_score[nb] = tentative
                counter += 1
                heapq.heappush(open_heap, (tentative + _manhattan(nb, goal), counter, nb))
    return []


def compare_planners(
    apt: Apartment,
    start: Coord,
    goal: Coord,
    *,
    owner_pos: Coord | None = None,
    config: PlannerConfig | None = None,
) -> dict[str, object]:
    """Benchmark plain vs costmap planner (for reports / CLI)."""
    plain = astar(apt, start, goal)
    rich = astar_costmap(apt, start, goal, owner_pos=owner_pos, config=config)
    return {
        "start": list(start),
        "goal": list(goal),
        "owner": list(owner_pos) if owner_pos else None,
        "plain_steps": max(0, len(plain) - 1),
        "plain_turns": _count_turns(plain),
        "costmap": rich.to_json(),
    }


def _count_turns(path: list[Coord]) -> int:
    if len(path) < 3:
        return 0
    turns = 0
    prev_dir: Coord | None = None
    for i in range(1, len(path)):
        dx = path[i][0] - path[i - 1][0]
        dy = path[i][1] - path[i - 1][1]
        d = (dx, dy)
        if prev_dir is not None and d != prev_dir:
            turns += 1
        prev_dir = d
    return turns
