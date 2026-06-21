"""Tests for IoT sidebar formatting."""

from __future__ import annotations

from homemate.ui_devices import format_device_summary, group_devices_by_room


def test_format_coffee_brewing() -> None:
    line = format_device_summary({
        "device_id": "coffee.kitchen",
        "kind": "coffee_maker",
        "room": "kitchen",
        "state": {"brewing": True, "progress": 0.42, "cups": 1},
    })
    assert "brewing 42%" in line
    assert "kitchen" in line or "coffee" in line


def test_group_devices_by_room() -> None:
    snaps = [
        {"device_id": "lamp.bedroom", "room": "bedroom", "kind": "lamp", "state": {}},
        {"device_id": "coffee.kitchen", "room": "kitchen", "kind": "coffee_maker", "state": {}},
    ]
    grouped = group_devices_by_room(snaps)
    assert list(grouped.keys()) == ["bedroom", "kitchen"]
    assert len(grouped["kitchen"]) == 1
