"""Save and restore simulator world state (robot, owner, IoT devices).

Snapshots are JSON files under ``data/scenarios/`` by default. Used by the
Pygame UI (F5 / F9) and by ``--load-snapshot`` for reproducible demos.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .world.entities import Owner, Robot
from .world.iot import IoTNetwork

SNAPSHOT_VERSION = 1
DEFAULT_SNAPSHOT_DIR = Path("data/scenarios")
DEFAULT_SNAPSHOT_FILE = DEFAULT_SNAPSHOT_DIR / "last_snapshot.json"


def capture_world(
    *,
    robot: Robot,
    owner: Owner,
    iot: IoTNetwork,
    seed: int,
    owner_room: str | None,
    script: str | None = None,
) -> dict[str, Any]:
    return {
        "version": SNAPSHOT_VERSION,
        "seed": seed,
        "owner_room": owner_room,
        "script": script,
        "robot": {"x": robot.x, "y": robot.y},
        "owner": {"x": owner.x, "y": owner.y},
        "devices": iot.snapshot(),
    }


def restore_world(data: dict[str, Any], *, robot: Robot, owner: Owner, iot: IoTNetwork) -> None:
    if data.get("version") != SNAPSHOT_VERSION:
        raise ValueError(f"unsupported snapshot version: {data.get('version')!r}")
    robot.x = int(data["robot"]["x"])
    robot.y = int(data["robot"]["y"])
    owner.x = int(data["owner"]["x"])
    owner.y = int(data["owner"]["y"])
    by_id = {snap["device_id"]: snap for snap in data.get("devices", [])}
    for dev in iot.list():
        snap = by_id.get(dev.device_id)
        if snap is None:
            continue
        dev.state.clear()
        dev.state.update(dict(snap.get("state", {})))


def save_snapshot(path: Path | str, payload: dict[str, Any]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def load_snapshot(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"snapshot not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid snapshot JSON in {p}: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(f"snapshot root must be an object, got {type(data).__name__}")
    return data
