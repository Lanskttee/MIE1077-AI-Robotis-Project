"""Render an animated GIF of a scripted HomeMate scenario.

Headless, deterministic, and re-runnable so the README GIF stays in sync
with the code. The scenario:

    1. Robot is in the living room; owner is in the bedroom and tired.
    2. User asks for coffee.
    3. Robot navigates to the bedroom (find_owner via A*).
    4. Reads emotion, speaks an empathetic line.
    5. Navigates to the kitchen coffee maker.
    6. Starts brewing; coffee maker animates while the robot waits.

Each animation step captures one Pygame frame and the frames are
assembled into a GIF with Pillow.

Run with::

    python -m homemate.scripts.gif_demo
"""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

# Headless SDL so no window pops up.
os.environ["SDL_VIDEODRIVER"] = "dummy"


def main(out_path: Path | None = None,
         *, frame_duration_ms: int = 90,
         scale: float = 0.6) -> int:
    # Force the deterministic mock paths before App() runs.
    from homemate import config
    config.USE_MOCK_EMOTION = True
    config.USE_MOCK_LLM = True

    import pygame
    from PIL import Image

    from homemate.main import App
    from homemate.planning.navigator import astar
    from homemate.world.entities import place_in_room

    app = App()

    # Seed a reproducible starting layout.
    rng = random.Random(7)
    place_in_room(app.robot, app.apt, "living_room", rng)
    place_in_room(app.owner, app.apt, "bedroom", rng)
    app.skills.dialogue.clear()
    app.skills.pending_path.clear()
    app.emotion.inject("neutral")  # will switch to 'tired' mid-scene
    app.status_msg = "Live Pygame demo"

    frames: list[Image.Image] = []
    target_size: tuple[int, int] | None = None

    def capture() -> None:
        nonlocal target_size
        app._draw()
        raw = pygame.image.tobytes(app.screen, "RGB")
        img = Image.frombytes("RGB", app.screen.get_size(), raw)
        if target_size is None:
            w, h = img.size
            target_size = (max(1, int(w * scale)), max(1, int(h * scale)))
        if img.size != target_size:
            img = img.resize(target_size, Image.LANCZOS)
        frames.append(img)

    def hold(n_frames: int, dt: float = 1.0 / 15) -> None:
        for _ in range(n_frames):
            app.iot.tick(dt)
            capture()

    def animate_path(path: list[tuple[int, int]],
                     dt: float = 1.0 / 15) -> None:
        for tile in path:
            app.robot.x, app.robot.y = tile
            app.iot.tick(dt)
            capture()

    # --- Scene -----------------------------------------------------------

    # Establishing shot
    hold(4)

    # User types
    app.skills.dialogue.append(("you", "I'm tired. Brew some coffee."))
    app.status_msg = "Sending to LLM..."
    hold(6)

    # Robot walks to the owner (A* over the grid, animated tile-by-tile).
    start = (app.robot.x, app.robot.y)
    goal = app.skills._closest_walkable(*app.owner.pos)
    path = astar(app.apt, start, goal)
    animate_path(path[1:])
    app.skills.owner_found = True

    # Detect emotion and speak.
    app.emotion.inject("tired")
    hold(3)
    app.skills.dialogue.append(("robot", "You look tired. Let me start the coffee."))
    app.status_msg = "Detected emotion: tired"
    hold(6)

    # Walk to the coffee maker.
    start = (app.robot.x, app.robot.y)
    coffee = app.iot.get("coffee.kitchen")
    goal_room = app.apt.room(coffee.room).center
    goal = app.skills._closest_walkable(*goal_room)
    path = astar(app.apt, start, goal)
    animate_path(path[1:])

    # Brew.
    app.iot.act("coffee.kitchen", "brew")
    app.skills.dialogue.append(("robot", "Brewing. Rest up."))
    app.status_msg = "Coffee brewing"
    hold(18, dt=0.3)  # bigger dt so progress bar visibly advances

    # Final beat.
    app.skills.dialogue.append(("robot", "Coffee is ready."))
    app.status_msg = "Agent done. Detected emotion: tired."
    hold(6)

    # --- Save ------------------------------------------------------------

    out_path = out_path or (Path(__file__).resolve().parents[2]
                            / "docs" / "images" / "pygame_demo.gif")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Pillow palette-optimises automatically when saving GIF.
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=frame_duration_ms,
        loop=0,
        optimize=True,
    )

    size_kb = out_path.stat().st_size / 1024
    print(f"Wrote {out_path}  ({len(frames)} frames, {size_kb:.0f} KB)")

    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
