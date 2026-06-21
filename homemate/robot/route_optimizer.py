"""Multi-goal route optimization for sequential device visits.

Builds a cost matrix using costmap A* distances, then applies nearest-neighbor
greedy ordering with optional 2-opt improvement — a lightweight TSP heuristic
for mobile manipulation tours.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..planning.costmap import PlannerConfig, PlanResult, astar_costmap
from ..planning.navigator import Coord
from ..world.apartment import Apartment
from ..world.iot import IoTDevice, IoTNetwork
from .kinematics import nearest_dock


@dataclass
class RouteStop:
    device_id: str
    dock: Coord
    room: str


@dataclass
class RoutePlan:
    stops: list[RouteStop] = field(default_factory=list)
    total_cost: int = 0
    method: str = "nearest_neighbor"

    def device_order(self) -> list[str]:
        return [s.device_id for s in self.stops]

    def to_json(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "total_cost": self.total_cost,
            "device_order": self.device_order(),
            "stops": [
                {"device_id": s.device_id, "dock": list(s.dock), "room": s.room}
                for s in self.stops
            ],
        }


class RouteOptimizer:
    """Optimize visit order for multiple IoT device docks."""

    def __init__(self, apt: Apartment, *, config: PlannerConfig | None = None) -> None:
        self.apt = apt
        self.config = config or PlannerConfig()

    def _path_cost(self, start: Coord, goal: Coord,
                   *, owner_pos: Coord | None) -> int:
        plan = astar_costmap(self.apt, start, goal, owner_pos=owner_pos,
                             config=self.config)
        if not plan.path:
            return 1 << 29
        return plan.total_cost

    def _resolve_stops(self, device_ids: list[str], iot: IoTNetwork,
                       start: Coord, *, owner_pos: Coord | None) -> list[RouteStop]:
        stops: list[RouteStop] = []
        for did in device_ids:
            dev = iot.get(did)
            if dev is None:
                continue
            dock = nearest_dock(self.apt, start, self._device_goal(dev),
                                owner_pos=owner_pos)
            if dock is None:
                continue
            stops.append(RouteStop(device_id=did, dock=dock, room=dev.room))
        return stops

    def _device_goal(self, dev: IoTDevice) -> Coord:
        from .kinematics import device_tile
        return device_tile(self.apt, dev)

    def plan(self, device_ids: list[str], iot: IoTNetwork, start: Coord,
             *, owner_pos: Coord | None = None) -> RoutePlan:
        """Return an optimized visit order for ``device_ids`` from ``start``."""
        stops = self._resolve_stops(device_ids, iot, start, owner_pos=owner_pos)
        if not stops:
            return RoutePlan()
        if len(stops) == 1:
            return RoutePlan(stops=stops, total_cost=0, method="single")

        n = len(stops)
        docks = [s.dock for s in stops]
        cost: list[list[int]] = [[0] * n for _ in range(n)]
        for i in range(n):
            cost[i][i] = 0
            for j in range(i + 1, n):
                c = self._path_cost(docks[i], docks[j], owner_pos=owner_pos)
                cost[i][j] = c
                cost[j][i] = c

        order = self._nearest_neighbor(start, docks, cost, owner_pos=owner_pos)
        order = self._two_opt(order, docks, cost, start, owner_pos=owner_pos)
        ordered_stops = [stops[i] for i in order]
        total = self._tour_cost(start, [docks[i] for i in order], owner_pos=owner_pos)
        return RoutePlan(stops=ordered_stops, total_cost=total, method="nn_2opt")

    def _nearest_neighbor(self, start: Coord, docks: list[Coord],
                          cost: list[list[int]], *,
                          owner_pos: Coord | None) -> list[int]:
        n = len(docks)
        remaining = set(range(n))
        order: list[int] = []
        cur = start
        while remaining:
            best_i = -1
            best_c = 1 << 30
            for i in remaining:
                c = self._path_cost(cur, docks[i], owner_pos=owner_pos)
                if c < best_c:
                    best_c = c
                    best_i = i
            order.append(best_i)
            remaining.remove(best_i)
            cur = docks[best_i]
        return order

    def _tour_cost(self, start: Coord, docks: list[Coord],
                   *, owner_pos: Coord | None) -> int:
        if not docks:
            return 0
        total = self._path_cost(start, docks[0], owner_pos=owner_pos)
        for i in range(len(docks) - 1):
            total += self._path_cost(docks[i], docks[i + 1], owner_pos=owner_pos)
        return total

    def _two_opt(self, order: list[int], docks: list[Coord],
                 cost: list[list[int]], start: Coord,
                 *, owner_pos: Coord | None) -> list[int]:
        """2-opt swap on stop indices using precomputed pairwise costs."""
        n = len(order)
        if n < 3:
            return order

        def tour_len(ord_: list[int]) -> int:
            if not ord_:
                return 0
            total = self._path_cost(start, docks[ord_[0]], owner_pos=owner_pos)
            for i in range(len(ord_) - 1):
                total += cost[ord_[i]][ord_[i + 1]]
            return total

        best = list(order)
        best_len = tour_len(best)
        improved = True
        while improved:
            improved = False
            for i in range(n - 1):
                for j in range(i + 2, n):
                    candidate = best[:i + 1] + list(reversed(best[i + 1:j + 1])) + best[j + 1:]
                    cand_len = tour_len(candidate)
                    if cand_len < best_len:
                        best = candidate
                        best_len = cand_len
                        improved = True
        return best

    def execute_segment(self, start: Coord, stop: RouteStop,
                        *, owner_pos: Coord | None) -> PlanResult:
        return astar_costmap(self.apt, start, stop.dock,
                             owner_pos=owner_pos, config=self.config)
