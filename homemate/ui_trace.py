"""Sidebar tool-trace formatting — pygame-free for unit tests."""

from __future__ import annotations

from typing import Any


def format_tool_step(step: dict[str, Any]) -> tuple[str, bool]:
    """Render one agent tool call as a short human-readable line."""
    name = step.get("name", "?")
    inp = step.get("input") or {}
    out = step.get("output") or {}
    ok = bool(out.get("ok"))
    if name == "set_device":
        detail = f"{inp.get('device_id', '?')}.{inp.get('action', '?')}"
    elif name == "navigate_to_room":
        detail = str(inp.get("room", ""))
    elif name == "speak":
        detail = (inp.get("text") or "")[:36]
    elif name == "make_plan":
        detail = "plan"
    else:
        detail = ""
    label = f"{name}({detail})" if detail else name
    if not ok:
        err = out.get("error", "failed")
        label += f" -> {err}"
    return label, ok
