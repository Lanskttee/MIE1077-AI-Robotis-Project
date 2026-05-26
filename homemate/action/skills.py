"""Primitive skills the LLM can call.

Each method returns a JSON-serialisable dict that goes back to the LLM as a
``tool_result``. Skills are intentionally small — the LLM composes them into
behaviors.

Navigation is *planned* (path computed via A*) but the actual tile-by-tile
movement is animated by the main loop using ``pending_path``. The skill
returns immediately so the LLM loop stays simple.
"""

from __future__ import annotations

from typing import Any

from ..perception.emotion import EmotionDetector
from ..planning.navigator import Navigator, astar
from ..planning.search import OwnerSearchPolicy
from ..world.apartment import Apartment
from ..world.entities import Owner, Robot
from ..world.iot import IoTNetwork


class Skills:
    def __init__(
        self,
        apt: Apartment,
        robot: Robot,
        owner: Owner,
        iot: IoTNetwork,
        emotion: EmotionDetector,
    ) -> None:
        self.apt = apt
        self.robot = robot
        self.owner = owner
        self.iot = iot
        self.emotion = emotion
        self.navigator = Navigator(apt)
        self.search = OwnerSearchPolicy(apt.room_names())
        # path queued for the main loop to animate; the LLM treats nav as instantaneous
        self.pending_path: list[tuple[int, int]] = []
        # dialogue log (list of (speaker, text)); UI consumes this
        self.dialogue: list[tuple[str, str]] = []
        # has the robot established line-of-sight with the owner this episode?
        self.owner_found = False

    # ---------------------------------------------------------------- navigation

    def navigate_to_room(self, room: str) -> dict[str, Any]:
        """Move to the center of ``room`` (or nearest walkable tile)."""
        if room not in self.apt.room_names():
            return {"ok": False, "error": f"unknown room {room!r}",
                    "rooms": self.apt.room_names()}
        target = self._closest_walkable(*self.apt.room(room).center)
        path = astar(self.apt, self.robot.pos, target)
        if not path:
            return {"ok": False, "error": f"no path to {room}"}
        self._commit_path(path)
        return {
            "ok": True,
            "arrived_at_room": room,
            "tiles_traveled": max(0, len(path) - 1),
            "owner_visible_here": self._owner_visible_in_room(room),
        }

    def navigate_to_device(self, device_id: str) -> dict[str, Any]:
        dev = self.iot.get(device_id)
        if dev is None:
            return {"ok": False, "error": f"unknown device {device_id}"}
        return self.navigate_to_room(dev.room)

    # ---------------------------------------------------------------- search

    def find_owner(self) -> dict[str, Any]:
        """Sweep rooms in time-of-day priority order until the owner is seen."""
        if self._owner_in_current_room():
            self.owner_found = True
            return {"ok": True, "owner_room": self.owner_room(), "method": "already_here"}

        for room in self.search.ordering(current_room=self.robot_room()):
            self.navigate_to_room(room)
            if self._owner_in_current_room():
                self.owner_found = True
                return {"ok": True, "owner_room": room, "method": "room_sweep"}
        self.owner_found = False
        return {"ok": False, "error": "owner not found in any room"}

    # ---------------------------------------------------------------- sensors

    def look_around(self) -> dict[str, Any]:
        room = self.robot_room()
        return {
            "ok": True,
            "robot_room": room,
            "owner_in_this_room": self._owner_in_current_room(),
            "devices_here": [d.snapshot() for d in self.iot.find(room=room)],
        }

    def read_emotion(self) -> dict[str, Any]:
        if not self._owner_in_current_room():
            return {"ok": False, "error": "owner is not in the same room — cannot read emotion"}
        reading = self.emotion.poll()
        if reading is None:
            return {"ok": False, "error": "no emotion reading yet (webcam warming up?)"}
        return {"ok": True, "emotion": reading.label, "confidence": round(reading.confidence, 3),
                "distribution": {k: round(v, 3) for k, v in reading.raw.items()}}

    # ---------------------------------------------------------------- dialogue

    def speak(self, text: str) -> dict[str, Any]:
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "empty speech"}
        self.dialogue.append(("robot", text))
        return {"ok": True, "spoken": text}

    # ---------------------------------------------------------------- IoT

    def set_device(self, device_id: str, action: str, **kwargs: Any) -> dict[str, Any]:
        return self.iot.act(device_id, action, **kwargs)

    def list_devices(self) -> dict[str, Any]:
        return {"ok": True, "devices": self.iot.snapshot()}

    # ---------------------------------------------------------------- helpers

    def robot_room(self) -> str | None:
        return self.apt.room_name_at(*self.robot.pos)

    def owner_room(self) -> str | None:
        return self.apt.room_name_at(*self.owner.pos)

    def _owner_in_current_room(self) -> bool:
        rr, orr = self.robot_room(), self.owner_room()
        return rr is not None and rr == orr

    def _owner_visible_in_room(self, room: str) -> bool:
        return self.owner_room() == room

    def _closest_walkable(self, x: int, y: int) -> tuple[int, int]:
        if self.apt.is_walkable(x, y):
            return (x, y)
        # spiral outward
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

    def _commit_path(self, path: list[tuple[int, int]]) -> None:
        """Teleport robot to end (LLM view) and stash the path for animation."""
        if not path:
            return
        self.pending_path.extend(path[1:])  # everything except current pos
        self.robot.x, self.robot.y = path[-1]
