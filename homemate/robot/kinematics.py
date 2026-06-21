"""Robot kinematics: device poses and manipulation reach."""

from __future__ import annotations

from ..planning.navigator import Coord, astar
from ..world.apartment import Apartment
from ..world.iot import IoTDevice

# Manhattan distance within which the robot can actuate a device.
INTERACTION_RANGE = 2

# Relative tile offsets inside a room — mirrors the Pygame renderer slots.
DEVICE_SLOTS: dict[str, tuple[int, int]] = {
    "curtain":      (1, 1),
    "lamp":         (-1, 1),
    "thermostat":   (1, 2),
    "tv":           (-2, 2),
    "toaster":      (-1, -1),
    "coffee_maker": (1, -1),
    "speaker":      (-1, -2),
    "fan":          (1, -2),
    "door_lock":    (-1, 1),
}


def _manhattan(a: Coord, b: Coord) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def device_tile(apt: Apartment, dev: IoTDevice) -> Coord:
    """Grid coordinate of the device widget inside its room."""
    room = apt.room(dev.room)
    dx, dy = DEVICE_SLOTS.get(dev.kind, (1, 1))
    x = room.x1 + dx if dx < 0 else room.x0 + dx
    y = room.y1 + dy if dy < 0 else room.y0 + dy
    x = max(room.x0, min(room.x1, x))
    y = max(room.y0, min(room.y1, y))
    return (x, y)


def dock_candidates(apt: Apartment, device_pos: Coord) -> list[Coord]:
    """Walkable tiles from which the robot can manipulate the device."""
    dx, dy = device_pos
    candidates: list[Coord] = []
    for nx, ny in ((dx + 1, dy), (dx - 1, dy), (dx, dy + 1), (dx, dy - 1),
                   (dx + 2, dy), (dx - 2, dy), (dx, dy + 2), (dx, dy - 2)):
        if apt.is_walkable(nx, ny) and _manhattan((nx, ny), device_pos) <= INTERACTION_RANGE:
            candidates.append((nx, ny))
    # fallback: any walkable tile in interaction range inside apartment
    if not candidates:
        for nx in range(dx - INTERACTION_RANGE, dx + INTERACTION_RANGE + 1):
            for ny in range(dy - INTERACTION_RANGE, dy + INTERACTION_RANGE + 1):
                if apt.is_walkable(nx, ny) and _manhattan((nx, ny), device_pos) <= INTERACTION_RANGE:
                    candidates.append((nx, ny))
    return candidates


def nearest_dock(apt: Apartment, robot_pos: Coord, device_pos: Coord) -> Coord | None:
    """Pick the reachable dock tile with minimum A* path cost."""
    best: Coord | None = None
    best_cost = 1 << 30
    for dock in dock_candidates(apt, device_pos):
        path = astar(apt, robot_pos, dock)
        if not path:
            continue
        cost = len(path) - 1
        if cost < best_cost:
            best_cost = cost
            best = dock
    return best


def can_interact(robot_pos: Coord, device_pos: Coord) -> bool:
    return _manhattan(robot_pos, device_pos) <= INTERACTION_RANGE
