"""High-level robot controller integrating motion, belief, and coverage."""

from __future__ import annotations

from typing import Any, Callable

from ..planning.navigator import Coord, astar
from ..planning.search import OwnerSearchPolicy
from ..world.apartment import Apartment
from ..world.entities import Owner, Robot
from ..world.iot import IoTDevice, IoTNetwork
from .belief import OwnerBelief
from .coverage import CoveragePlanner
from .kinematics import can_interact, device_tile, nearest_dock
from .motion import MotionMetrics


class RobotController:
    """Robotics substrate used by :class:`homemate.action.skills.Skills`."""

    def __init__(self, apt: Apartment, robot: Robot, owner: Owner,
                 iot: IoTNetwork) -> None:
        self.apt = apt
        self.robot = robot
        self.owner = owner
        self.iot = iot
        self.belief = OwnerBelief(apt.room_names())
        self.coverage = CoveragePlanner(apt)
        self.metrics = MotionMetrics()
        self.search = OwnerSearchPolicy(apt.room_names())
        self.mode: str = "idle"

    # --- pose / room helpers ---

    def robot_room(self) -> str | None:
        return self.apt.room_name_at(*self.robot.pos)

    def owner_room(self) -> str | None:
        return self.apt.room_name_at(*self.owner.pos)

    def owner_visible(self) -> bool:
        rr, orr = self.robot_room(), self.owner_room()
        return rr is not None and rr == orr

    # --- navigation ---

    def plan_to(self, goal: Coord) -> list[Coord]:
        return astar(self.apt, self.robot.pos, goal)

    def commit_path(self, path: list[Coord],
                    pending: list[Coord]) -> dict[str, Any]:
        """Apply path: teleport for agent logic, queue tiles for UI animation."""
        if not path:
            return {"ok": False, "error": "empty path"}
        cost = self.metrics.record_path(path)
        pending.extend(path[1:])
        self.robot.x, self.robot.y = path[-1]
        self.mode = "navigating"
        return {"ok": True, "path_cost": cost, "goal": list(path[-1])}

    def navigate_to_tile(self, goal: Coord,
                         pending: list[Coord]) -> dict[str, Any]:
        path = self.plan_to(goal)
        if not path:
            return {"ok": False, "error": f"no path to {goal}"}
        out = self.commit_path(path, pending)
        out["tiles_traveled"] = out.get("path_cost", 0)
        return out

    def navigate_to_room_center(self, room: str,
                              pending: list[Coord]) -> dict[str, Any]:
        if room not in self.apt.room_names():
            return {"ok": False, "error": f"unknown room {room!r}",
                    "rooms": self.apt.room_names()}
        cx, cy = self.apt.room(room).center
        goal = self._closest_walkable(cx, cy)
        out = self.navigate_to_tile(goal, pending)
        if out.get("ok"):
            out["arrived_at_room"] = room
            out["owner_visible_here"] = self.owner_room() == room
        return out

    def navigate_to_device(self, dev: IoTDevice,
                           pending: list[Coord]) -> dict[str, Any]:
        tile = device_tile(self.apt, dev)
        dock = nearest_dock(self.apt, self.robot.pos, tile)
        if dock is None:
            return {"ok": False, "error": f"no dock reachable for {dev.device_id}"}
        out = self.navigate_to_tile(dock, pending)
        if out.get("ok"):
            out["device_id"] = dev.device_id
            out["dock_tile"] = list(dock)
            out["device_tile"] = list(tile)
            out["in_interaction_range"] = can_interact(self.robot.pos, tile)
        return out

    # --- search ---

    def observe_current_room(self) -> dict[str, Any]:
        room = self.robot_room()
        visible = self.owner_visible()
        if room:
            self.belief.observe(room, visible)
        return {"room": room, "owner_visible": visible}

    def scan_room(self, room: str, pending: list[Coord],
                  *, owner_check: Callable[[], bool]) -> dict[str, Any]:
        """Execute a boustrophedon sweep; stop early if owner is spotted."""
        if room not in self.apt.room_names():
            return {"ok": False, "error": f"unknown room {room!r}"}
        self.mode = "scanning"
        sweep = self.coverage.plan_sweep(room, self.robot.pos)
        tiles_visited = 0
        owner_found = False
        for tile in sweep[1:]:
            segment = astar(self.apt, self.robot.pos, tile)
            if not segment:
                continue
            self.commit_path(segment, pending)
            tiles_visited += max(0, len(segment) - 1)
            visible = owner_check()
            self.belief.observe(room, visible)
            if visible:
                owner_found = True
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
        }

    def find_owner_plan(self, pending: list[Coord],
                        owner_check: Callable[[], bool]) -> dict[str, Any]:
        """Belief-guided room sweep with optional intra-room scan."""
        self.mode = "searching"
        if owner_check():
            room = self.owner_room()
            if room:
                self.belief.observe(room, True)
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
                self.mode = "idle"
                return {"ok": True, "owner_room": room, "method": "belief_sweep",
                        "rooms_checked": rooms.index(room) + 1,
                        "belief": self.belief.snapshot()}
            # Secondary: quick partial scan if center observation negative
            scan = self.scan_room(room, pending, owner_check=owner_check)
            if scan.get("owner_found"):
                self.mode = "idle"
                return {"ok": True, "owner_room": room, "method": "coverage_scan",
                        "tiles_scanned": scan.get("tiles_scanned", 0),
                        "belief": self.belief.snapshot()}

        self.mode = "idle"
        return {"ok": False, "error": "owner not found in any room",
                "rooms_checked": len(rooms), "belief": self.belief.snapshot()}

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
            "belief": self.belief.snapshot(),
            "motion": self.metrics.to_json(),
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
