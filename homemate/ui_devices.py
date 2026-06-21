"""Format IoT device snapshots for the sidebar Devices panel."""

from __future__ import annotations

from typing import Any


def format_device_summary(snap: dict[str, Any]) -> str:
    """One-line human-readable summary for a device snapshot dict."""
    device_id = snap.get("device_id", "?")
    kind = snap.get("kind", "?")
    state = snap.get("state") or {}
    short_id = device_id.split(".", 1)[-1] if "." in device_id else device_id

    if kind == "curtain":
        detail = "open" if state.get("open") else "closed"
    elif kind == "lamp":
        detail = f"on bri={state.get('brightness', 0):.1f}" if state.get("on") else "off"
    elif kind == "toaster":
        if state.get("running"):
            detail = f"toasting {int(float(state.get('progress', 0)) * 100)}%"
        else:
            detail = "idle"
    elif kind == "coffee_maker":
        if state.get("brewing"):
            detail = f"brewing {int(float(state.get('progress', 0)) * 100)}%"
        else:
            detail = f"idle cups={state.get('cups', 0)}"
    elif kind == "thermostat":
        detail = f"{state.get('mode', 'off')} {state.get('target_c', 0):.0f}C"
    elif kind == "tv":
        detail = f"{state.get('channel', 'off')} vol={state.get('volume', 0):.1f}" if state.get("on") else "off"
    elif kind == "speaker":
        if state.get("playing"):
            detail = f"{state.get('playlist', '?')} vol={state.get('volume', 0):.1f}"
        else:
            detail = "stopped"
    elif kind == "fan":
        detail = f"speed={state.get('speed', 0)}" if state.get("on") else "off"
    elif kind == "door_lock":
        detail = "locked" if state.get("locked") else "unlocked"
    else:
        detail = str(state)[:24]
    return f"{short_id}: {detail}"


def group_devices_by_room(snapshots: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for snap in snapshots:
        room = snap.get("room", "?")
        grouped.setdefault(room, []).append(snap)
    for room in grouped:
        grouped[room].sort(key=lambda s: s.get("device_id", ""))
    return dict(sorted(grouped.items()))
