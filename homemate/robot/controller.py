"""High-level robot controller integrating motion, belief, and coverage."""

from __future__ import annotations

from typing import Any, Callable

from ..planning.costmap import PlannerConfig, PlanResult, astar_costmap
from ..planning.navigator import Coord
from ..planning.search import OwnerSearchPolicy
from ..world.apartment import Apartment
from ..world.entities import Owner, Robot
from ..world.iot import IoTDevice, IoTNetwork
from .belief import OwnerBelief
from .coverage import CoveragePlanner
from .kinematics import can_interact, device_tile, nearest_dock
from .motion import MotionMetrics
from .occupancy import OccupancyGrid
from .path_tracker import GoalKind, PathTracker
from .route_optimizer import RouteOptimizer


class RobotController:
    """Robotics substrate used by :class:`homemate.action.skills.Skills`."""

    def __init__(self, apt: Apartment, robot: Robot, owner: Owner,
                 iot: IoTNetwork,
                 *, planner_config: PlannerConfig | None = None) -> None:
        self.apt = apt
        self.robot = robot
        self.owner = owner
        self.iot = iot
        self.belief = OwnerBelief(apt.room_names())
        self.coverage = CoveragePlanner(apt)
        self.map = OccupancyGrid(apt)
        self.route_opt = RouteOptimizer(apt, config=planner_config)
        self.metrics = MotionMetrics()
        self.tracker = PathTracker()
        self.search = OwnerSearchPolicy(apt.room_names())
        self.planner_config = planner_config or PlannerConfig()
        self.mode: str = "idle"

    # --- pose / room helpers ---

    def robot_room(self) -> str | None:
        return self.apt.room_name_at(*self.robot.pos)

    def owner_room(self) -> str | None:
        return self.apt.room_name_at(*self.owner.pos)

    def owner_visible(self) -> bool:
        rr, orr = self.robot_room(), self.owner_room()
        return rr is not None and rr == orr

    def update_map(self) -> int:
        """Refresh occupancy from current pose; return newly revealed cells."""
        return self.map.reveal_from_pose(
            self.robot.pos,
            owner_pos=self.owner.pos if self.owner_visible() else None,
        )

    # --- navigation ---

    def plan_to(self, goal: Coord) -> PlanResult:
        return astar_costmap(
            self.apt, self.robot.pos, goal,
            owner_pos=self.owner.pos,
            config=self.planner_config,
        )

    def commit_path(self, plan: PlanResult, pending: list[Coord],
                    *, goal: Coord, kind: GoalKind = "tile",
                    label: str = "") -> dict[str, Any]:
        """Apply path: teleport for agent logic, queue tiles for UI animation."""
        path = plan.path
        if not path:
            return {"ok": False, "error": "empty path"}
        cost = self.metrics.record_path(
            path, cost=plan.total_cost, turns=plan.turn_count, planner=plan.planner,
        )
        pending.extend(path[1:])
        self.robot.x, self.robot.y = path[-1]
        self.mode = "navigating"
        self.tracker.register(goal, kind=kind, label=label)
        self.tracker.last_plan_turns = plan.turn_count
        self.tracker.last_plan_cost = plan.total_cost
        self.tracker.planner_used = plan.planner
        self.update_map()
        return {
            "ok": True,
            "path_cost": cost,
            "tile_steps": plan.tile_steps,
            "turn_count": plan.turn_count,
            "planner": plan.planner,
            "goal": list(path[-1]),
        }

    def navigate_to_tile(self, goal: Coord, pending: list[Coord],
                         *, kind: GoalKind = "tile", label: str = "") -> dict[str, Any]:
        plan = self.plan_to(goal)
        if not plan.path:
            return {"ok": False, "error": f"no path to {goal}"}
        out = self.commit_path(plan, pending, goal=goal, kind=kind, label=label)
        out["tiles_traveled"] = plan.tile_steps
        return out

    def navigate_to_room_center(self, room: str,
                                pending: list[Coord]) -> dict[str, Any]:
        if room not in self.apt.room_names():
            return {"ok": False, "error": f"unknown room {room!r}",
                    "rooms": self.apt.room_names()}
        cx, cy = self.apt.room(room).center
        goal = self._closest_walkable(cx, cy)
        out = self.navigate_to_tile(goal, pending, kind="room", label=room)
        if out.get("ok"):
            out["arrived_at_room"] = room
            out["owner_visible_here"] = self.owner_room() == room
        return out

    def navigate_to_device(self, dev: IoTDevice,
                           pending: list[Coord]) -> dict[str, Any]:
        tile = device_tile(self.apt, dev)
        dock = nearest_dock(self.apt, self.robot.pos, tile, owner_pos=self.owner.pos)
        if dock is None:
            return {"ok": False, "error": f"no dock reachable for {dev.device_id}"}
        out = self.navigate_to_tile(
            dock, pending, kind="device", label=dev.device_id,
        )
        if out.get("ok"):
            out["device_id"] = dev.device_id
            out["dock_tile"] = list(dock)
            out["device_tile"] = list(tile)
            out["in_interaction_range"] = can_interact(self.robot.pos, tile)
        return out

    # --- dynamic replanning ---

    def check_replan_reason(self, pending: list[Coord]) -> str | None:
        owner_pos = self.owner.pos
        moved = self.tracker.observe_owner(owner_pos)
        if moved:
            return moved
        blocked = self.tracker.check_path_blocked(owner_pos, pending)
        if blocked:
            return blocked
        return None

    def try_replan(self, pending: list[Coord], *, reason: str,
                   teleport: bool = False) -> dict[str, Any]:
        """Recompute path to active goal from the robot's *current* tile."""
        if self.tracker.active is None:
            return {"ok": False, "error": "no active goal"}
        goal = self.tracker.active.goal
        if self.tracker.follow_owner and reason == "owner_moved":
            # Keep device / room goals fixed; only chase the owner tile when that
            # *is* the navigation target (find_owner follow mode).
            if self.tracker.active.kind == "owner":
                goal = self.owner.pos
                self.tracker.register(goal, kind="owner", label="follow_owner")
        plan = self.plan_to(goal)
        if not plan.path:
            return {"ok": False, "error": "replan failed", "reason": reason}
        pending.clear()
        pending.extend(plan.path[1:])
        if teleport:
            self.robot.x, self.robot.y = plan.path[-1]
        self.metrics.record_replan()
        self.tracker.record_replan(
            reason, new_cost=plan.total_cost, turns=plan.turn_count, planner=plan.planner,
        )
        self.mode = "replanning"
        return {
            "ok": True,
            "replanned": True,
            "reason": reason,
            "tile_steps": plan.tile_steps,
            "turn_count": plan.turn_count,
            "planner": plan.planner,
            "goal": list(goal),
        }

    # --- search ---

    def observe_current_room(self) -> dict[str, Any]:
        room = self.robot_room()
        visible = self.owner_visible()
        if room:
            self.belief.observe(room, visible)
        self.update_map()
        return {"room": room, "owner_visible": visible}

    def scan_room(self, room: str, pending: list[Coord],
                  *, owner_check: Callable[[], bool]) -> dict[str, Any]:
        if room not in self.apt.room_names():
            return {"ok": False, "error": f"unknown room {room!r}"}
        self.mode = "scanning"
        sweep = self.coverage.plan_sweep(
            room, self.robot.pos, owner_pos=self.owner.pos,
        )
        tiles_visited = 0
        owner_found = False
        for tile in sweep[1:]:
            plan = self.plan_to(tile)
            if not plan.path:
                continue
            self.commit_path(plan, pending, goal=tile, kind="tile", label=f"scan:{room}")
            tiles_visited += plan.tile_steps
            visible = owner_check()
            self.belief.observe(room, visible)
            if visible:
                owner_found = True
                self.tracker.enable_owner_tracking(owner_pos=self.owner.pos)
                break
        self.metrics.record_scan(tiles_visited)
        self.mode = "idle"
        return {
            "ok": True,
            "room": room,
            "tiles_scanned": tiles_visited,
            "owner_found": owner_found,
            "owner_room": self.owner_room() if owner_found else None,
            "belief": self.belief.snapshot(),
            "map": self.map.snapshot(),
        }

    def explore_frontier(self, pending: list[Coord], *,
                         owner_check: Callable[[], bool],
                         max_hops: int = 3) -> dict[str, Any]:
        """Navigate toward map frontiers to expand known free space."""
        self.mode = "exploring"
        hops = 0
        tiles = 0
        owner_found = False
        for _ in range(max_hops):
            frontier = self.map.nearest_frontier(
                self.robot.pos, owner_pos=self.owner.pos,
            )
            if frontier is None:
                break
            plan = self.plan_to(frontier)
            if not plan.path:
                break
            self.commit_path(plan, pending, goal=frontier, kind="tile", label="frontier")
            self.map.frontiers_visited += 1
            tiles += plan.tile_steps
            hops += 1
            self.update_map()
            if owner_check():
                owner_found = True
                room = self.owner_room()
                if room:
                    self.belief.observe(room, True)
                self.tracker.enable_owner_tracking(owner_pos=self.owner.pos)
                break
        self.mode = "idle"
        return {
            "ok": True,
            "hops": hops,
            "tiles_explored": tiles,
            "owner_found": owner_found,
            "owner_room": self.owner_room() if owner_found else None,
            "map": self.map.snapshot(),
        }

    def find_owner_plan(self, pending: list[Coord],
                        owner_check: Callable[[], bool]) -> dict[str, Any]:
        self.mode = "searching"
        self.update_map()
        if owner_check():
            room = self.owner_room()
            if room:
                self.belief.observe(room, True)
            self.tracker.enable_owner_tracking(owner_pos=self.owner.pos)
            self.mode = "idle"
            return {"ok": True, "owner_room": room, "method": "already_here",
                    "belief": self.belief.snapshot()}

        rooms = self.belief.merge_search_order(self.search, self.robot_room())
        for room in rooms:
            nav = self.navigate_to_room_center(room, pending)
            if not nav.get("ok"):
                continue
            visible = owner_check()
            self.belief.observe(room, visible)
            if visible:
                self.tracker.enable_owner_tracking(owner_pos=self.owner.pos)
                self.mode = "idle"
                return {"ok": True, "owner_room": room, "method": "belief_sweep",
                        "rooms_checked": rooms.index(room) + 1,
                        "belief": self.belief.snapshot(),
                        "planner": nav.get("planner")}
            scan = self.scan_room(room, pending, owner_check=owner_check)
            if scan.get("owner_found"):
                self.mode = "idle"
                return {"ok": True, "owner_room": room, "method": "coverage_scan",
                        "tiles_scanned": scan.get("tiles_scanned", 0),
                        "belief": self.belief.snapshot()}

        explore = self.explore_frontier(pending, owner_check=owner_check, max_hops=2)
        if explore.get("owner_found"):
            self.mode = "idle"
            return {"ok": True, "owner_room": self.owner_room(), "method": "frontier_explore",
                    "belief": self.belief.snapshot(), "map": explore.get("map")}

        self.mode = "idle"
        return {"ok": False, "error": "owner not found in any room",
                "rooms_checked": len(rooms), "belief": self.belief.snapshot(),
                "map": self.map.snapshot()}

    def plan_device_route(self, device_ids: list[str]) -> dict[str, Any]:
        """Optimize multi-device visit order (TSP heuristic)."""
        route = self.route_opt.plan(
            device_ids, self.iot, self.robot.pos, owner_pos=self.owner.pos,
        )
        return {"ok": True, "route": route.to_json()}

    def execute_device_route(self, device_ids: list[str],
                             pending: list[Coord]) -> dict[str, Any]:
        """Navigate along an optimized multi-device tour."""
        route = self.route_opt.plan(
            device_ids, self.iot, self.robot.pos, owner_pos=self.owner.pos,
        )
        if not route.stops:
            return {"ok": False, "error": "no reachable devices",
                    "requested": device_ids}
        total_tiles = 0
        visited: list[str] = []
        for stop in route.stops:
            plan = self.route_opt.execute_segment(
                self.robot.pos, stop, owner_pos=self.owner.pos,
            )
            if not plan.path:
                continue
            self.commit_path(plan, pending, goal=stop.dock, kind="device",
                             label=stop.device_id)
            total_tiles += plan.tile_steps
            visited.append(stop.device_id)
        self.mode = "idle"
        return {
            "ok": True,
            "visited_order": visited,
            "total_tiles": total_tiles,
            "estimated_cost": route.total_cost,
            "route": route.to_json(),
        }

    # --- manipulation ---

    def check_device_reach(self, dev: IoTDevice) -> dict[str, Any]:
        tile = device_tile(self.apt, dev)
        ok = can_interact(self.robot.pos, tile)
        return {
            "ok": ok,
            "device_id": dev.device_id,
            "device_tile": list(tile),
            "robot_tile": list(self.robot.pos),
            "interaction_range": 2,
            "manhattan_distance": abs(self.robot.x - tile[0]) + abs(self.robot.y - tile[1]),
        }

    def telemetry(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "pose": {"x": self.robot.x, "y": self.robot.y, "room": self.robot_room()},
            "owner_visible": self.owner_visible(),
            "owner_tile": list(self.owner.pos),
            "belief": self.belief.snapshot(),
            "motion": self.metrics.to_json(),
            "path_tracker": self.tracker.snapshot(),
            "map": self.map.snapshot(),
        }

    def _closest_walkable(self, x: int, y: int) -> Coord:
        if self.apt.is_walkable(x, y):
            return (x, y)
        for r in range(1, max(self.apt.cols, self.apt.rows)):
            for dx in range(-r, r + 1):
                for dy in (-r, r):
                    nx, ny = x + dx, y + dy
                    if self.apt.is_walkable(nx, ny):
                        return (nx, ny)
            for dy in range(-r + 1, r):
                for dx in (-r, r):
                    nx, ny = x + dx, y + dy
                    if self.apt.is_walkable(nx, ny):
                        return (nx, ny)
        return (x, y)
