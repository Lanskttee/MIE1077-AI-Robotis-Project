"""Mock smart-home IoT devices and a tiny REST-style API.

Each device exposes a typed action set. ``IoTNetwork`` is the registry the
rest of the system talks to. The API surface is deliberately JSON-friendly so
it maps cleanly onto Anthropic tool calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------


@dataclass
class IoTDevice:
    device_id: str
    room: str
    kind: str           # 'curtain', 'lamp', 'toaster', 'coffee_maker'
    state: dict[str, Any] = field(default_factory=dict)

    # subclasses override
    def actions(self) -> list[str]:
        return []

    def apply(self, action: str, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError

    def snapshot(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "room": self.room,
            "kind": self.kind,
            "state": dict(self.state),
        }


@dataclass
class Curtain(IoTDevice):
    kind: str = "curtain"

    def __post_init__(self) -> None:
        self.state.setdefault("open", False)
        self.state.setdefault("progress", 0.0)   # 0..1 animation progress

    def actions(self) -> list[str]:
        return ["open", "close", "toggle"]

    def apply(self, action: str, **kwargs: Any) -> dict[str, Any]:
        if action == "open":
            self.state["open"] = True
        elif action == "close":
            self.state["open"] = False
        elif action == "toggle":
            self.state["open"] = not self.state["open"]
        else:
            return {"ok": False, "error": f"unknown action {action}"}
        return {"ok": True, "state": dict(self.state)}


@dataclass
class Lamp(IoTDevice):
    kind: str = "lamp"

    def __post_init__(self) -> None:
        self.state.setdefault("on", False)
        self.state.setdefault("brightness", 0.8)

    def actions(self) -> list[str]:
        return ["on", "off", "toggle", "set_brightness"]

    def apply(self, action: str, **kwargs: Any) -> dict[str, Any]:
        if action == "on":
            self.state["on"] = True
        elif action == "off":
            self.state["on"] = False
        elif action == "toggle":
            self.state["on"] = not self.state["on"]
        elif action == "set_brightness":
            b = float(kwargs.get("brightness", 0.8))
            self.state["brightness"] = max(0.0, min(1.0, b))
            self.state["on"] = self.state["brightness"] > 0.05
        else:
            return {"ok": False, "error": f"unknown action {action}"}
        return {"ok": True, "state": dict(self.state)}


@dataclass
class Toaster(IoTDevice):
    kind: str = "toaster"

    def __post_init__(self) -> None:
        self.state.setdefault("running", False)
        self.state.setdefault("level", 3)        # 1..5 darkness
        self.state.setdefault("progress", 0.0)   # 0..1 cooking progress

    def actions(self) -> list[str]:
        return ["start", "stop", "set_level"]

    def apply(self, action: str, **kwargs: Any) -> dict[str, Any]:
        if action == "start":
            self.state["running"] = True
            self.state["progress"] = 0.0
            if "level" in kwargs:
                self.state["level"] = int(kwargs["level"])
        elif action == "stop":
            self.state["running"] = False
        elif action == "set_level":
            self.state["level"] = max(1, min(5, int(kwargs.get("level", 3))))
        else:
            return {"ok": False, "error": f"unknown action {action}"}
        return {"ok": True, "state": dict(self.state)}

    def tick(self, dt: float) -> None:
        """Advance cooking progress; auto-stop when done."""
        if not self.state["running"]:
            return
        # toaster cooks for (4 + level) seconds
        total = 4.0 + float(self.state["level"])
        self.state["progress"] = min(1.0, self.state["progress"] + dt / total)
        if self.state["progress"] >= 1.0:
            self.state["running"] = False


@dataclass
class CoffeeMaker(IoTDevice):
    kind: str = "coffee_maker"

    def __post_init__(self) -> None:
        self.state.setdefault("brewing", False)
        self.state.setdefault("cups", 0)
        self.state.setdefault("progress", 0.0)

    def actions(self) -> list[str]:
        return ["brew", "stop"]

    def apply(self, action: str, **kwargs: Any) -> dict[str, Any]:
        if action == "brew":
            self.state["brewing"] = True
            self.state["progress"] = 0.0
        elif action == "stop":
            self.state["brewing"] = False
        else:
            return {"ok": False, "error": f"unknown action {action}"}
        return {"ok": True, "state": dict(self.state)}

    def tick(self, dt: float) -> None:
        if not self.state["brewing"]:
            return
        self.state["progress"] = min(1.0, self.state["progress"] + dt / 6.0)
        if self.state["progress"] >= 1.0:
            self.state["brewing"] = False
            self.state["cups"] += 1


# ---------------------------------------------------------------------------
# Network / registry
# ---------------------------------------------------------------------------


class IoTNetwork:
    """Registry + JSON-friendly action API."""

    def __init__(self) -> None:
        self._devices: dict[str, IoTDevice] = {}

    # ---- registration ----

    def register(self, device: IoTDevice) -> None:
        self._devices[device.device_id] = device

    @classmethod
    def default(cls) -> "IoTNetwork":
        """Default device set used by the MVP."""
        net = cls()
        net.register(Curtain("curtain.living_room",  "living_room"))
        net.register(Curtain("curtain.bedroom",      "bedroom"))
        net.register(Lamp(   "lamp.living_room",     "living_room"))
        net.register(Lamp(   "lamp.bedroom",         "bedroom"))
        net.register(Toaster("toaster.kitchen",      "kitchen"))
        net.register(CoffeeMaker("coffee.kitchen",   "kitchen"))
        return net

    # ---- queries ----

    def list(self) -> list[IoTDevice]:
        return list(self._devices.values())

    def get(self, device_id: str) -> IoTDevice | None:
        return self._devices.get(device_id)

    def find(self, *, room: str | None = None, kind: str | None = None) -> list[IoTDevice]:
        out = self.list()
        if room is not None:
            out = [d for d in out if d.room == room]
        if kind is not None:
            out = [d for d in out if d.kind == kind]
        return out

    def snapshot(self) -> list[dict[str, Any]]:
        return [d.snapshot() for d in self._devices.values()]

    # ---- act ----

    def act(self, device_id: str, action: str, **kwargs: Any) -> dict[str, Any]:
        dev = self.get(device_id)
        if dev is None:
            return {"ok": False, "error": f"unknown device_id {device_id}"}
        if action not in dev.actions():
            return {"ok": False, "error": f"{dev.kind} does not support {action}",
                    "available": dev.actions()}
        return dev.apply(action, **kwargs)

    def tick(self, dt: float) -> None:
        for d in self._devices.values():
            if hasattr(d, "tick"):
                d.tick(dt)
