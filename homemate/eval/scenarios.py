"""The 20 evaluation scenarios.

Each scenario is one user turn against a deterministic world. The mix is
designed to exercise every device kind at least once, every emotion vocabulary
slot at least once, and a few multi-action requests that only the planner
can satisfy in one shot.

Scenario id format: ``s<NN>_<short_slug>``. NN is the seed passed into the
world's RNG, so equal seeds give equal world layouts under the runner.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .criteria import (
    Criterion,
    device_state_close,
    device_state_eq,
    emotion_detected,
    empathy_tone,
    spoken_contains,
    tool_was_called,
)


@dataclass
class Scenario:
    id: str
    description: str
    owner_room: str
    emotion: str               # one of homemate.config.EMOTIONS
    message: str
    criteria: list[Criterion] = field(default_factory=list)
    seed: int = 1
    # Tags used to filter / group scenarios in the report.
    tags: tuple[str, ...] = ()


def _common() -> list[Criterion]:
    """Baseline criteria every scenario must hit: locate owner, sense emotion,
    speak something."""
    return [
        tool_was_called("find_owner"),
        tool_was_called("read_emotion"),
        tool_was_called("speak"),
    ]


SCENARIOS: list[Scenario] = [
    # ---- single-device requests (one per kind) ----
    Scenario(
        id="s01_curtain_open_sad",
        description="Sad owner asks to open bedroom curtains",
        owner_room="bedroom", emotion="sad",
        message="I feel low. Could you open the bedroom curtains?",
        criteria=_common() + [
            emotion_detected("sad"),
            device_state_eq("curtain.bedroom", "open", True),
            empathy_tone("sad"),
        ],
        tags=("single_device", "curtain"),
    ),
    Scenario(
        id="s02_coffee_tired",
        description="Tired owner asks for coffee",
        owner_room="bedroom", emotion="tired",
        message="I'm tired, brew some coffee for me",
        criteria=_common() + [
            emotion_detected("tired"),
            device_state_eq("coffee.kitchen", "brewing", True),
            empathy_tone("tired"),
        ],
        tags=("single_device", "coffee"),
    ),
    Scenario(
        id="s03_lamp_on_happy",
        description="Happy owner asks for living-room lamp on",
        owner_room="living_room", emotion="happy",
        message="Turn on the living room lamp",
        criteria=_common() + [
            emotion_detected("happy"),
            device_state_eq("lamp.living_room", "on", True),
        ],
        tags=("single_device", "lamp"),
    ),
    Scenario(
        id="s04_toaster_start_neutral",
        description="Owner asks to start the toaster",
        owner_room="kitchen", emotion="neutral",
        message="Start the toaster please",
        criteria=_common() + [
            device_state_eq("toaster.kitchen", "running", True),
        ],
        tags=("single_device", "toaster"),
    ),
    Scenario(
        id="s05_lamp_dim_angry",
        description="Angry owner asks to dim the bedroom lamp",
        owner_room="bedroom", emotion="angry",
        message="Dim the bedroom lamp",
        criteria=_common() + [
            emotion_detected("angry"),
            device_state_close("lamp.bedroom", "brightness", 0.3),
            empathy_tone("angry"),
        ],
        tags=("single_device", "lamp"),
    ),
    Scenario(
        id="s06_speaker_calm_sad",
        description="Sad owner asks for calm music",
        owner_room="bedroom", emotion="sad",
        message="Play some calm music for me",
        criteria=_common() + [
            emotion_detected("sad"),
            device_state_eq("speaker.bedroom", "playing", True),
            device_state_eq("speaker.bedroom", "playlist", "calm"),
        ],
        tags=("single_device", "speaker"),
        seed=2,
    ),
    Scenario(
        id="s07_tv_on_tired",
        description="Tired owner asks to turn on the TV",
        owner_room="living_room", emotion="tired",
        message="Turn on the TV",
        criteria=_common() + [
            device_state_eq("tv.living_room", "on", True),
        ],
        tags=("single_device", "tv"),
    ),
    Scenario(
        id="s08_thermostat_heat",
        description="Happy owner asks to heat the apartment",
        owner_room="living_room", emotion="happy",
        message="Turn the heat on",
        criteria=_common() + [
            device_state_eq("thermostat.living_room", "mode", "heat"),
        ],
        tags=("single_device", "thermostat"),
    ),
    Scenario(
        id="s09_fan_on",
        description="Neutral owner asks for the bedroom fan",
        owner_room="bedroom", emotion="neutral",
        message="Turn on the bedroom fan",
        criteria=_common() + [
            device_state_eq("fan.bedroom", "on", True),
        ],
        tags=("single_device", "fan"),
    ),
    Scenario(
        id="s10_door_unlock_surprised",
        description="Surprised owner asks to unlock the front door",
        owner_room="living_room", emotion="surprised",
        message="Unlock the front door",
        criteria=_common() + [
            emotion_detected("surprised"),
            device_state_eq("lock.front_door", "locked", False),
        ],
        tags=("single_device", "lock"),
    ),

    # ---- multi-device requests (planner shines) ----
    Scenario(
        id="s11_coffee_and_curtain",
        description="Tired owner asks for coffee AND curtains open",
        owner_room="bedroom", emotion="tired",
        message="Brew coffee and open the bedroom curtains",
        criteria=_common() + [
            device_state_eq("coffee.kitchen", "brewing", True),
            device_state_eq("curtain.bedroom", "open", True),
        ],
        tags=("multi_device",),
    ),
    Scenario(
        id="s12_sad_ambient",
        description="Sad owner asks to dim the lamp and play rain",
        owner_room="bedroom", emotion="sad",
        message="I'm sad. Dim the bedroom lamp and play rain on the speaker",
        criteria=_common() + [
            emotion_detected("sad"),
            device_state_close("lamp.bedroom", "brightness", 0.3),
            device_state_eq("speaker.bedroom", "playlist", "rain"),
            device_state_eq("speaker.bedroom", "playing", True),
        ],
        tags=("multi_device", "emotional"),
    ),
    Scenario(
        id="s13_happy_morning",
        description="Happy owner wants news on TV and fan on high",
        owner_room="living_room", emotion="happy",
        message="Put the news channel on TV and set the fan to high",
        criteria=_common() + [
            device_state_eq("tv.living_room", "channel", "news"),
            device_state_eq("fan.bedroom", "speed", 3),
        ],
        tags=("multi_device",),
    ),
    Scenario(
        id="s14_angry_lockdown",
        description="Angry owner asks to close curtains and lock the door",
        owner_room="bedroom", emotion="angry",
        message="Close the bedroom curtains and lock the door",
        criteria=_common() + [
            emotion_detected("angry"),
            device_state_eq("curtain.bedroom", "open", False),
            device_state_eq("lock.front_door", "locked", True),
        ],
        tags=("multi_device",),
    ),
    Scenario(
        id="s15_breakfast_combo",
        description="Owner asks for toast and coffee for breakfast",
        owner_room="kitchen", emotion="neutral",
        message="Make me toast and brew coffee",
        criteria=_common() + [
            device_state_eq("toaster.kitchen", "running", True),
            device_state_eq("coffee.kitchen", "brewing", True),
        ],
        tags=("multi_device",),
    ),
    Scenario(
        id="s16_three_actions_sad",
        description="Sad owner: thermostat warmer + brew coffee + dim lamp",
        owner_room="living_room", emotion="sad",
        message="Set the thermostat to 24 degrees, brew coffee, and dim the bedroom lamp",
        criteria=_common() + [
            emotion_detected("sad"),
            device_state_close("thermostat.living_room", "target_c", 24.0),
            device_state_eq("coffee.kitchen", "brewing", True),
            device_state_close("lamp.bedroom", "brightness", 0.3),
        ],
        tags=("multi_device", "three_actions"),
    ),

    # ---- emotional check-ins (no IoT) ----
    Scenario(
        id="s17_emotional_checkin_sad",
        description="Sad owner just wants to talk",
        owner_room="bedroom", emotion="sad",
        message="I had a rough day, can you keep me company?",
        criteria=_common() + [
            emotion_detected("sad"),
            empathy_tone("sad"),
        ],
        tags=("emotional",),
    ),
    Scenario(
        id="s18_emotional_checkin_happy",
        description="Happy owner just wants a chat",
        owner_room="living_room", emotion="happy",
        message="Hi! How's it going today?",
        criteria=_common() + [
            emotion_detected("happy"),
            empathy_tone("happy"),
        ],
        tags=("emotional",),
        seed=3,
    ),

    # ---- room-aware disambiguation ----
    Scenario(
        id="s19_curtain_specifies_living_room",
        description="Owner specifies the living-room curtain, not the bedroom one",
        owner_room="living_room", emotion="neutral",
        message="Open the living room curtains",
        criteria=_common() + [
            device_state_eq("curtain.living_room", "open", True),
            device_state_eq("curtain.bedroom", "open", False),
        ],
        tags=("disambiguation", "curtain"),
    ),

    # ---- comfort routine ----
    Scenario(
        id="s20_comfort_routine_tired",
        description="Tired owner asks for a full wind-down routine",
        owner_room="bedroom", emotion="tired",
        message="I need to wind down. Dim the bedroom lamp, play calm music, "
                "and close the bedroom curtains.",
        criteria=_common() + [
            emotion_detected("tired"),
            device_state_close("lamp.bedroom", "brightness", 0.3),
            device_state_eq("speaker.bedroom", "playing", True),
            device_state_eq("speaker.bedroom", "playlist", "calm"),
            device_state_eq("curtain.bedroom", "open", False),
            empathy_tone("tired"),
        ],
        tags=("multi_device", "three_actions", "emotional"),
        seed=4,
    ),
]


assert len(SCENARIOS) == 20, f"expected 20 scenarios, got {len(SCENARIOS)}"
assert len({s.id for s in SCENARIOS}) == 20, "scenario ids must be unique"
