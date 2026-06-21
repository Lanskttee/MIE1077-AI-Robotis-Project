"""Built-in demo scripts for reproducible Pygame recordings.

Each script pins world layout (seed, owner room, emotion) and supplies a
canonical user message that exercises a distinct slice of the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass

from .ui_options import MainOptions


@dataclass(frozen=True)
class DemoScript:
    id: str
    title: str
    description: str
    message: str
    emotion: str
    owner_room: str
    seed: int = 7


DEMO_SCRIPTS: dict[str, DemoScript] = {
    "tired_coffee": DemoScript(
        id="tired_coffee",
        title="Tired owner, brew coffee",
        description="Find owner in bedroom, read tired emotion, empathise, brew coffee.",
        message="I'm tired. Brew some coffee.",
        emotion="tired",
        owner_room="bedroom",
        seed=7,
    ),
    "sad_talk": DemoScript(
        id="sad_talk",
        title="Sad emotional check-in",
        description="Pure empathy path — no IoT actuation.",
        message="I feel low today. Can we just talk?",
        emotion="sad",
        owner_room="living_room",
        seed=11,
    ),
    "wind_down": DemoScript(
        id="wind_down",
        title="Tired wind-down routine",
        description="Multi-device: dim lamp, calm music, close curtains.",
        message="I need to wind down. Dim the bedroom lamp, play calm music, "
                 "and close the bedroom curtains.",
        emotion="tired",
        owner_room="bedroom",
        seed=4,
    ),
    "multi_comfort": DemoScript(
        id="multi_comfort",
        title="Three-action comfort",
        description="Thermostat + coffee + lamp in one planner turn.",
        message="Set the thermostat to 24 degrees, brew coffee, "
                 "and dim the bedroom lamp.",
        emotion="sad",
        owner_room="bedroom",
        seed=16,
    ),
}


def script_ids() -> list[str]:
    return list(DEMO_SCRIPTS.keys())


def get_script(script_id: str) -> DemoScript:
    if script_id not in DEMO_SCRIPTS:
        known = ", ".join(script_ids())
        raise ValueError(f"unknown script {script_id!r}; choose from: {known}")
    return DEMO_SCRIPTS[script_id]


def apply_script(base: MainOptions, script_id: str) -> MainOptions:
    """Merge a demo script into CLI options (always offline-friendly)."""
    script = get_script(script_id)
    return MainOptions(
        seed=script.seed,
        owner_room=script.owner_room,
        emotion=script.emotion,
        mock_llm=True,
        mock_emotion=True,
        freeze_owner=True,
        script=script_id,
        auto_run=base.auto_run,
        auto_message=script.message if base.auto_run else None,
        load_snapshot=base.load_snapshot,
        snapshot_path=base.snapshot_path,
        record_session=base.record_session,
        replay_session=base.replay_session,
        session_title=base.session_title or script.title,
    )
