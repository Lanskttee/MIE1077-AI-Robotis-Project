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
    kind: str           # see subclasses below
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
        return ["start", "stop", "set_level", "pick_up"]

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
        elif action == "pick_up":
            if self.state.get("progress", 0.0) < 1.0 or self.state.get("running"):
                return {"ok": False, "error": "toast not ready yet"}
            self.state["progress"] = 0.0  # reset after pickup
            return {"ok": True, "item": "toast"}
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
        return ["brew", "stop", "pick_up"]

    def apply(self, action: str, **kwargs: Any) -> dict[str, Any]:
        if action == "brew":
            if self.state.get("brewing"):
                return {"ok": False, "error": "already brewing"}
            self.state["brewing"] = True
            self.state["progress"] = 0.0
        elif action == "stop":
            self.state["brewing"] = False
        elif action == "pick_up":
            if self.state.get("cups", 0) < 1:
                return {"ok": False, "error": "no cups ready to pick up"}
            self.state["cups"] -= 1
            return {"ok": True, "item": "coffee", "cups_remaining": self.state["cups"]}
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


@dataclass
class Thermostat(IoTDevice):
    """A simple set-point thermostat. ``mode`` is heat|cool|auto|off."""
    kind: str = "thermostat"

    def __post_init__(self) -> None:
        self.state.setdefault("target_c", 21.0)
        self.state.setdefault("current_c", 21.0)
        self.state.setdefault("mode", "auto")     # heat|cool|auto|off

    def actions(self) -> list[str]:
        return ["set_target", "set_mode", "off"]

    def apply(self, action: str, **kwargs: Any) -> dict[str, Any]:
        if action == "set_target":
            t = float(kwargs.get("target_c", self.state["target_c"]))
            self.state["target_c"] = max(10.0, min(32.0, t))
            if self.state["mode"] == "off":
                self.state["mode"] = "auto"
        elif action == "set_mode":
            mode = str(kwargs.get("mode", "auto")).lower()
            if mode not in ("heat", "cool", "auto", "off"):
                return {"ok": False, "error": f"unknown mode {mode!r}"}
            self.state["mode"] = mode
        elif action == "off":
            self.state["mode"] = "off"
        else:
            return {"ok": False, "error": f"unknown action {action}"}
        return {"ok": True, "state": dict(self.state)}

    def tick(self, dt: float) -> None:
        if self.state["mode"] == "off":
            return
        # drift current_c toward target_c at 0.2 C/sec (visual only)
        cur = float(self.state["current_c"])
        tgt = float(self.state["target_c"])
        if abs(cur - tgt) < 0.05:
            return
        step = 0.2 * dt * (1 if tgt > cur else -1)
        self.state["current_c"] = round(cur + step, 2)


@dataclass
class TV(IoTDevice):
    kind: str = "tv"

    CHANNELS = ("news", "movies", "music", "sports", "kids")

    def __post_init__(self) -> None:
        self.state.setdefault("on", False)
        self.state.setdefault("channel", "news")
        self.state.setdefault("volume", 0.3)

    def actions(self) -> list[str]:
        return ["on", "off", "toggle", "set_channel", "set_volume"]

    def apply(self, action: str, **kwargs: Any) -> dict[str, Any]:
        if action == "on":
            self.state["on"] = True
        elif action == "off":
            self.state["on"] = False
        elif action == "toggle":
            self.state["on"] = not self.state["on"]
        elif action == "set_channel":
            ch = str(kwargs.get("channel", "")).lower()
            if ch not in self.CHANNELS:
                return {"ok": False, "error": f"unknown channel {ch!r}",
                        "available": list(self.CHANNELS)}
            self.state["channel"] = ch
            self.state["on"] = True
        elif action == "set_volume":
            v = float(kwargs.get("volume", 0.3))
            self.state["volume"] = max(0.0, min(1.0, v))
        else:
            return {"ok": False, "error": f"unknown action {action}"}
        return {"ok": True, "state": dict(self.state)}


@dataclass
class Speaker(IoTDevice):
    """A bedside / nightstand speaker for music or ambient sounds."""
    kind: str = "speaker"

    PLAYLISTS = ("calm", "rain", "jazz", "pop", "focus")

    def __post_init__(self) -> None:
        self.state.setdefault("playing", False)
        self.state.setdefault("playlist", "calm")
        self.state.setdefault("volume", 0.4)

    def actions(self) -> list[str]:
        return ["play", "stop", "set_playlist", "set_volume"]

    def apply(self, action: str, **kwargs: Any) -> dict[str, Any]:
        if action == "play":
            if "playlist" in kwargs:
                pl = str(kwargs["playlist"]).lower()
                if pl not in self.PLAYLISTS:
                    return {"ok": False, "error": f"unknown playlist {pl!r}",
                            "available": list(self.PLAYLISTS)}
                self.state["playlist"] = pl
            self.state["playing"] = True
        elif action == "stop":
            self.state["playing"] = False
        elif action == "set_playlist":
            pl = str(kwargs.get("playlist", "")).lower()
            if pl not in self.PLAYLISTS:
                return {"ok": False, "error": f"unknown playlist {pl!r}",
                        "available": list(self.PLAYLISTS)}
            self.state["playlist"] = pl
        elif action == "set_volume":
            v = float(kwargs.get("volume", 0.4))
            self.state["volume"] = max(0.0, min(1.0, v))
        else:
            return {"ok": False, "error": f"unknown action {action}"}
        return {"ok": True, "state": dict(self.state)}


@dataclass
class Fan(IoTDevice):
    kind: str = "fan"

    def __post_init__(self) -> None:
        self.state.setdefault("on", False)
        self.state.setdefault("speed", 2)        # 1..3

    def actions(self) -> list[str]:
        return ["on", "off", "toggle", "set_speed"]

    def apply(self, action: str, **kwargs: Any) -> dict[str, Any]:
        if action == "on":
            self.state["on"] = True
        elif action == "off":
            self.state["on"] = False
        elif action == "toggle":
            self.state["on"] = not self.state["on"]
        elif action == "set_speed":
            s = int(kwargs.get("speed", 2))
            self.state["speed"] = max(1, min(3, s))
            self.state["on"] = True
        else:
            return {"ok": False, "error": f"unknown action {action}"}
        return {"ok": True, "state": dict(self.state)}


@dataclass
class DoorLock(IoTDevice):
    """Front-door smart lock — modelled as a room-scoped device for visibility."""
    kind: str = "door_lock"

    def __post_init__(self) -> None:
        self.state.setdefault("locked", True)

    def actions(self) -> list[str]:
        return ["lock", "unlock", "toggle"]

    def apply(self, action: str, **kwargs: Any) -> dict[str, Any]:
        if action == "lock":
            self.state["locked"] = True
        elif action == "unlock":
            self.state["locked"] = False
        elif action == "toggle":
            self.state["locked"] = not self.state["locked"]
        else:
            return {"ok": False, "error": f"unknown action {action}"}
        return {"ok": True, "state": dict(self.state)}


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
        """Default device set covering all four rooms.

        Counts: 2 curtains, 2 lamps, 1 toaster, 1 coffee maker, 1 thermostat,
        1 TV, 1 speaker, 1 fan, 1 front-door lock = 11 devices across all rooms.
        """
        net = cls()
        net.register(Curtain(    "curtain.living_room",  "living_room"))
        net.register(Curtain(    "curtain.bedroom",      "bedroom"))
        net.register(Lamp(       "lamp.living_room",     "living_room"))
        net.register(Lamp(       "lamp.bedroom",         "bedroom"))
        net.register(Toaster(    "toaster.kitchen",      "kitchen"))
        net.register(CoffeeMaker("coffee.kitchen",       "kitchen"))
        net.register(Thermostat( "thermostat.living_room", "living_room"))
        net.register(TV(         "tv.living_room",       "living_room"))
        net.register(Speaker(    "speaker.bedroom",      "bedroom"))
        net.register(Fan(        "fan.bedroom",          "bedroom"))
        net.register(DoorLock(   "lock.front_door",      "living_room"))
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
