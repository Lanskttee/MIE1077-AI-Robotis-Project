"""Tests for session recording and replay."""

from __future__ import annotations

from pathlib import Path

import pytest

from homemate.action.skills import Skills
from homemate.cognition.llm_agent import MockLLM
from homemate.perception.emotion import MockEmotionDetector
from homemate.session import ReplayController, SessionStore, TurnRecord
from homemate.world.apartment import Apartment
from homemate.world.entities import Owner, Robot, place_in_room
from homemate.world.iot import IoTNetwork
from homemate.world_snapshot import capture_world, restore_world


def _skills() -> Skills:
    apt = Apartment()
    robot = Robot(0, 0)
    owner = Owner(0, 0)
    place_in_room(robot, apt, "living_room", None)
    place_in_room(owner, apt, "bedroom", None)
    emo = MockEmotionDetector()
    emo.start()
    emo.inject("tired")
    return Skills(apt, robot, owner, IoTNetwork.default(), emo)


def test_session_record_and_load(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    store.start_session(title="test", script="tired_coffee", opts={"seed": 7})
    skills = _skills()
    agent = MockLLM(skills)
    before = capture_world(
        robot=skills.robot, owner=skills.owner, iot=skills.iot,
        seed=7, owner_room="bedroom",
    )
    result = agent.run_turn("I'm tired. Brew some coffee.")
    after = capture_world(
        robot=skills.robot, owner=skills.owner, iot=skills.iot,
        seed=7, owner_room="bedroom",
    )
    store.append_turn(TurnRecord(
        timestamp="",
        user_message="I'm tired. Brew some coffee.",
        world_before=before,
        world_after=after,
        tool_trace=list(result.tool_trace),
        spoken=list(result.spoken),
        final_text=result.final_text,
        emotion_label="tired",
    ))
    rows = store.list_sessions()
    assert len(rows) == 1
    loaded = store.load(rows[0]["session_id"])
    assert len(loaded.turns) == 1
    assert loaded.turns[0].user_message.startswith("I'm tired")


def test_replay_controller_steps(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    store.start_session(title="replay-test")
    skills = _skills()
    wb = capture_world(
        robot=skills.robot, owner=skills.owner, iot=skills.iot,
        seed=1, owner_room="bedroom",
    )
    skills.iot.act("coffee.kitchen", "brew")
    wa = capture_world(
        robot=skills.robot, owner=skills.owner, iot=skills.iot,
        seed=1, owner_room="bedroom",
    )
    store.append_turn(TurnRecord(
        timestamp="t1",
        user_message="brew",
        world_before=wb,
        world_after=wa,
        tool_trace=[],
        spoken=["ok"],
    ))
    rec = store.load(store.list_sessions()[0]["session_id"])
    replay = ReplayController(rec)

    robot2 = Robot(0, 0)
    owner2 = Owner(0, 0)
    iot2 = IoTNetwork.default()
    replay.apply_world(robot=robot2, owner=owner2, iot=iot2, phase="after")
    coffee = iot2.get("coffee.kitchen")
    assert coffee is not None
    assert coffee.state.get("brewing") is True

    dialogue = replay.dialogue_upto_current()
    assert dialogue[0] == ("you", "brew")
    assert dialogue[1] == ("robot", "ok")


def test_export_session(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    store.start_session(title="export")
    out = tmp_path / "export" / "copy.json"
    store.export_session(store.active.session_id, out)
    assert out.exists()
