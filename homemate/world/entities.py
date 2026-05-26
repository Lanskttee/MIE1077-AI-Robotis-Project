"""Robot and Owner entities."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .apartment import Apartment


@dataclass
class Entity:
    x: int
    y: int
    name: str = "entity"

    @property
    def pos(self) -> tuple[int, int]:
        return (self.x, self.y)

    def teleport(self, x: int, y: int) -> None:
        self.x = x
        self.y = y


@dataclass
class Robot(Entity):
    name: str = "homemate"
    facing: str = "S"     # N/S/E/W — for rendering only


@dataclass
class Owner(Entity):
    name: str = "owner"
    # The simulated owner cycles through rooms on a schedule.
    schedule: list[str] = field(default_factory=lambda: ["bedroom", "living_room", "kitchen", "bathroom"])


def place_in_room(entity: Entity, apt: Apartment, room_name: str,
                  rng: random.Random | None = None) -> None:
    """Place an entity at a random walkable tile inside ``room_name``."""
    rng = rng or random.Random()
    room = apt.room(room_name)
    candidates = [(x, y)
                  for x in range(room.x0, room.x1 + 1)
                  for y in range(room.y0, room.y1 + 1)
                  if apt.is_walkable(x, y)]
    if not candidates:
        raise RuntimeError(f"No walkable tiles in room {room_name}")
    entity.x, entity.y = rng.choice(candidates)


def random_room(apt: Apartment, exclude: str | None = None,
                rng: random.Random | None = None) -> str:
    rng = rng or random.Random()
    names = [n for n in apt.room_names() if n != exclude]
    return rng.choice(names)
