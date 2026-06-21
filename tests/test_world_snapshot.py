"""Tests for world snapshot save/load."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from homemate.world.entities import Owner, Robot
from homemate.world.iot import IoTNetwork
from homemate.world_snapshot import capture_world, load_snapshot, restore_world, save_snapshot


def test_capture_and_restore_roundtrip(tmp_path: Path) -> None:
    robot = Robot(3, 4)
    owner = Owner(10, 11)
    iot = IoTNetwork.default()
    iot.act("coffee.kitchen", "brew")
    iot.act("lamp.bedroom", "on")
    iot.act("lamp.bedroom", "set_brightness", brightness=0.3)

    payload = capture_world(
        robot=robot, owner=owner, iot=iot,
        seed=7, owner_room="bedroom", script="tired_coffee",
    )
    path = save_snapshot(tmp_path / "snap.json", payload)
    assert path.exists()

    robot2 = Robot(0, 0)
    owner2 = Owner(0, 0)
    iot2 = IoTNetwork.default()
    restore_world(load_snapshot(path), robot=robot2, owner=owner2, iot=iot2)

    assert robot2.pos == (3, 4)
    assert owner2.pos == (10, 11)
    coffee = iot2.get("coffee.kitchen")
    assert coffee is not None
    assert coffee.state["brewing"] is True
    lamp = iot2.get("lamp.bedroom")
    assert lamp is not None
    assert lamp.state["on"] is True
    assert lamp.state["brightness"] == pytest.approx(0.3)


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_snapshot(tmp_path / "missing.json")


def test_load_invalid_json_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid snapshot JSON"):
        load_snapshot(bad)


def test_restore_wrong_version_raises() -> None:
    robot = Robot(0, 0)
    owner = Owner(0, 0)
    iot = IoTNetwork.default()
    with pytest.raises(ValueError, match="unsupported snapshot version"):
        restore_world({"version": 99}, robot=robot, owner=owner, iot=iot)
