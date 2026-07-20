"""Primitive skills the LLM can call.

Each method returns a JSON-serialisable dict that goes back to the LLM as a
``tool_result``. Skills are intentionally small — the LLM composes them into
behaviors.

Navigation is planned via A* and executed through :class:`homemate.robot.RobotController`.
The robot teleports to the goal for agent logic while ``pending_path`` is
animated tile-by-tile in the Pygame UI.
"""

from __future__ import annotations

from typing import Any, Callable

from ..perception.emotion import EmotionDetector
from ..robot.controller import RobotController
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
        tts: Callable[[str], None] | None = None,
    ) -> None:
        self.apt = apt
        self.robot = robot
        self.owner = owner
        self.iot = iot
        self.emotion = emotion
        self._tts = tts
        self.robot_ctrl = RobotController(apt, robot, owner, iot)
        self.pending_path: list[tuple[int, int]] = []
        self.dialogue: list[tuple[str, str]] = []
        self.owner_found = False

    # ---------------------------------------------------------------- navigation

    def navigate_to_room(self, room: str) -> dict[str, Any]:
        out = self.robot_ctrl.navigate_to_room_center(room, self.pending_path)
        if out.get("ok") and out.get("owner_visible_here"):
            self.owner_found = True
        return out

    def navigate_to_device(self, device_id: str) -> dict[str, Any]:
        dev = self.iot.get(device_id)
        if dev is None:
            return {"ok": False, "error": f"unknown device {device_id}"}
        return self.robot_ctrl.navigate_to_device(dev, self.pending_path)

    # ---------------------------------------------------------------- search

    def find_owner(self) -> dict[str, Any]:
        out = self.robot_ctrl.find_owner_plan(
            self.pending_path,
            owner_check=self._owner_in_current_room,
        )
        if out.get("ok"):
            self.owner_found = True
        else:
            self.owner_found = False
        return out

    def scan_room(self, room: str) -> dict[str, Any]:
        out = self.robot_ctrl.scan_room(
            room, self.pending_path, owner_check=self._owner_in_current_room,
        )
        if out.get("owner_found"):
            self.owner_found = True
        return out

    def explore_frontier(self, max_hops: int = 3) -> dict[str, Any]:
        out = self.robot_ctrl.explore_frontier(
            self.pending_path,
            owner_check=self._owner_in_current_room,
            max_hops=max_hops,
        )
        if out.get("owner_found"):
            self.owner_found = True
        return out

    def plan_device_route(self, device_ids: list[str]) -> dict[str, Any]:
        return self.robot_ctrl.plan_device_route(device_ids)

    def visit_devices(self, device_ids: list[str]) -> dict[str, Any]:
        return self.robot_ctrl.execute_device_route(device_ids, self.pending_path)

    # ---------------------------------------------------------------- sensors

    def look_around(self) -> dict[str, Any]:
        obs = self.robot_ctrl.observe_current_room()
        room = obs.get("room")
        return {
            "ok": True,
            "robot_room": room,
            "owner_in_this_room": obs.get("owner_visible", False),
            "devices_here": [d.snapshot() for d in self.iot.find(room=room)] if room else [],
            "owner_belief": self.robot_ctrl.belief.snapshot(),
        }

    def get_robot_state(self) -> dict[str, Any]:
        return {"ok": True, **self.robot_ctrl.telemetry()}

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
        if self._tts is not None:
            self._tts(text)
        return {"ok": True, "spoken": text}

    # ---------------------------------------------------------------- IoT

    def set_device(self, device_id: str, action: str, **kwargs: Any) -> dict[str, Any]:
        dev = self.iot.get(device_id)
        if dev is None:
            return {"ok": False, "error": f"unknown device {device_id}"}
        reach = self.robot_ctrl.check_device_reach(dev)
        if not reach.get("ok"):
            return {
                "ok": False,
                "error": "robot out of device interaction range",
                "reach": reach,
                "hint": f"call navigate_to_device({device_id!r}) first",
            }
        result = self.iot.act(device_id, action, **kwargs)
        if result.get("ok"):
            self.robot_ctrl.mode = "actuating"
        return result

    def list_devices(self) -> dict[str, Any]:
        return {"ok": True, "devices": self.iot.snapshot()}

    def replan_if_needed(self, *, teleport: bool = False) -> dict[str, Any] | None:
        reason = self.robot_ctrl.check_replan_reason(self.pending_path)
        if reason is None:
            return None
        return self.robot_ctrl.try_replan(self.pending_path, reason=reason, teleport=teleport)

    # ---------------------------------------------------------------- helpers

    def robot_room(self) -> str | None:
        return self.robot_ctrl.robot_room()

    def owner_room(self) -> str | None:
        return self.robot_ctrl.owner_room()

    def _owner_in_current_room(self) -> bool:
        return self.robot_ctrl.owner_visible()

    # Legacy helper used by gif_demo script
    def _closest_walkable(self, x: int, y: int) -> tuple[int, int]:
        return self.robot_ctrl._closest_walkable(x, y)
