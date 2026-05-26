"""Apartment layout — grid, rooms, walls, doors.

The apartment is a 24x16 tile grid divided into four rooms:

    cols 0-11           cols 12-23
   +-----------+-------+----------+
   | living    |       | kitchen  |   rows 0-7
   | room      |       |          |
   +-----------+--+----+----------+
   |           |  |               |
   | bedroom   |  |   bathroom    |   rows 8-15
   |           |  |               |
   +-----------+--+---------------+

Doors are walkable openings in the wall tiles that separate rooms.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..config import GRID_COLS, GRID_ROWS


@dataclass(frozen=True)
class Room:
    name: str
    x0: int          # inclusive
    y0: int
    x1: int          # inclusive
    y1: int

    def contains(self, x: int, y: int) -> bool:
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1

    @property
    def center(self) -> tuple[int, int]:
        return ((self.x0 + self.x1) // 2, (self.y0 + self.y1) // 2)


# Walls (between rooms) are inserted at fixed columns/rows; doors are explicit
# (col, row) tiles within those walls that are walkable.

VERTICAL_WALL_COL = 12     # separates left/right halves
HORIZONTAL_WALL_ROW = 8    # separates top/bottom halves

# Doors — (col, row). Two per wall keeps navigation interesting.
DOORS: tuple[tuple[int, int], ...] = (
    (VERTICAL_WALL_COL, 3),                 # living_room <-> kitchen
    (VERTICAL_WALL_COL, 11),                # bedroom <-> bathroom
    (5,  HORIZONTAL_WALL_ROW),              # living_room <-> bedroom
    (18, HORIZONTAL_WALL_ROW),              # kitchen <-> bathroom
)


class Apartment:
    """A walkable grid with rooms, walls, and doors."""

    def __init__(self) -> None:
        self.cols = GRID_COLS
        self.rows = GRID_ROWS
        self.rooms: list[Room] = [
            Room("living_room", 0, 0, VERTICAL_WALL_COL - 1, HORIZONTAL_WALL_ROW - 1),
            Room("kitchen",     VERTICAL_WALL_COL + 1, 0, GRID_COLS - 1, HORIZONTAL_WALL_ROW - 1),
            Room("bedroom",     0, HORIZONTAL_WALL_ROW + 1, VERTICAL_WALL_COL - 1, GRID_ROWS - 1),
            Room("bathroom",    VERTICAL_WALL_COL + 1, HORIZONTAL_WALL_ROW + 1, GRID_COLS - 1, GRID_ROWS - 1),
        ]
        self._room_by_name = {r.name: r for r in self.rooms}
        self._doors = set(DOORS)
        self._walls = self._build_walls()

    # ---- queries ----

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.cols and 0 <= y < self.rows

    def is_wall(self, x: int, y: int) -> bool:
        return (x, y) in self._walls and (x, y) not in self._doors

    def is_door(self, x: int, y: int) -> bool:
        return (x, y) in self._doors

    def is_walkable(self, x: int, y: int) -> bool:
        return self.in_bounds(x, y) and not self.is_wall(x, y)

    def room_at(self, x: int, y: int) -> Room | None:
        for r in self.rooms:
            if r.contains(x, y):
                return r
        return None

    def room_name_at(self, x: int, y: int) -> str | None:
        r = self.room_at(x, y)
        return r.name if r else None

    def room(self, name: str) -> Room:
        return self._room_by_name[name]

    def room_names(self) -> list[str]:
        return [r.name for r in self.rooms]

    def walls(self) -> Iterable[tuple[int, int]]:
        return iter(self._walls)

    def doors(self) -> Iterable[tuple[int, int]]:
        return iter(self._doors)

    # ---- internals ----

    def _build_walls(self) -> set[tuple[int, int]]:
        walls: set[tuple[int, int]] = set()
        # Outer border
        for x in range(self.cols):
            walls.add((x, 0))
            walls.add((x, self.rows - 1))
        for y in range(self.rows):
            walls.add((0, y))
            walls.add((self.cols - 1, y))
        # Vertical inner wall
        for y in range(self.rows):
            walls.add((VERTICAL_WALL_COL, y))
        # Horizontal inner wall
        for x in range(self.cols):
            walls.add((x, HORIZONTAL_WALL_ROW))
        return walls
