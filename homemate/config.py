"""Global configuration: layout sizes, colors, and runtime flags.

The 2D apartment is rendered on a uniform grid. All coordinates in the world
modules are (col, row) tile indices; rendering converts them to pixels using
TILE_PX.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


# ----- Window / grid ----------------------------------------------------------

TILE_PX = 32                       # pixels per grid tile
GRID_COLS = 24                     # apartment width  (tiles)
GRID_ROWS = 16                     # apartment height (tiles)
SIDEBAR_PX = 360                   # right-hand dialogue / state panel
INFOBAR_PX = 52                    # top status strip (two lines)

WINDOW_W = GRID_COLS * TILE_PX + SIDEBAR_PX
WINDOW_H = GRID_ROWS * TILE_PX + INFOBAR_PX

FPS = 30
ROBOT_STEP_FRAMES = 4              # frames between grid steps (movement speed)


# ----- Palette (CSS-ish) ------------------------------------------------------

@dataclass(frozen=True)
class Palette:
    bg:        tuple = (24, 24, 28)
    floor:     tuple = (45, 47, 54)
    wall:      tuple = (90, 90, 100)
    door:      tuple = (170, 130, 60)
    grid_line: tuple = (35, 37, 42)

    text:      tuple = (230, 230, 235)
    text_dim:  tuple = (150, 150, 160)
    accent:    tuple = (110, 190, 250)
    warn:      tuple = (240, 180, 60)
    bad:       tuple = (240, 100, 100)
    good:      tuple = (120, 220, 140)

    robot:     tuple = (110, 190, 250)
    owner:     tuple = (140, 220, 140)
    path:      tuple = (110, 190, 250, 90)

    room_tint: dict = None         # filled below


PALETTE = Palette(room_tint={
    "living_room": (55, 60, 70),
    "kitchen":     (60, 55, 50),
    "bedroom":     (50, 55, 65),
    "bathroom":    (55, 65, 65),
})


# ----- Runtime flags (env-driven) --------------------------------------------

def env_flag(name: str, default: bool = False) -> bool:
    v = os.environ.get(name, "")
    return v.strip().lower() in ("1", "true", "yes", "on")


USE_MOCK_LLM     = env_flag("HOMEMATE_USE_MOCK_LLM",     False)
USE_MOCK_EMOTION = env_flag("HOMEMATE_USE_MOCK_EMOTION", False)
LLM_MODEL        = os.environ.get("HOMEMATE_MODEL", "claude-sonnet-4-6")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY   = os.environ.get("OPENAI_API_KEY", "")
TTS_VOICE        = os.environ.get("HOMEMATE_TTS_VOICE", "nova")


# ----- Emotion vocabulary -----------------------------------------------------

EMOTIONS = ("happy", "sad", "angry", "surprised", "neutral", "tired")
