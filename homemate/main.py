"""Pygame entry point: top-down apartment + dialogue panel.

Run with::

    python -m homemate.main

Key bindings:
    Enter   open the input field; type a request, press Enter to send
    1..6    inject mock emotion (happy / sad / angry / surprised / neutral / tired)
    w       toggle real webcam emotion detection on/off
    r       reset scenario (re-randomise owner position)
    Esc     quit
"""

from __future__ import annotations

import os
import random
import sys
import threading
from typing import Optional

try:
    from dotenv import load_dotenv
    # override=True so an empty inherited ANTHROPIC_API_KEY doesn't shadow .env
    load_dotenv(override=True)  # populate env BEFORE importing config
except ImportError:
    pass  # dotenv is optional; env vars set directly still work

import pygame  # noqa: E402

from . import config  # noqa: E402
from .action.skills import Skills  # noqa: E402
from .cognition.llm_agent import LLMAgent, MockLLM, TurnResult, make_agent  # noqa: E402
from .memory import MemoryStore  # noqa: E402
from .perception.emotion import (  # noqa: E402
    DeepFaceEmotionDetector, EmotionDetector, MockEmotionDetector,
)
from .world.apartment import Apartment  # noqa: E402
from .world.entities import Owner, Robot, place_in_room, random_room  # noqa: E402
from .world.iot import IoTNetwork  # noqa: E402


# ---------------------------------------------------------------------------
# Application state
# ---------------------------------------------------------------------------


class App:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("HomeMate — MIE1077 MVP")
        self.screen = pygame.display.set_mode((config.WINDOW_W, config.WINDOW_H))
        self.clock = pygame.time.Clock()
        self.font_sm = pygame.font.SysFont("consolas", 14)
        self.font_md = pygame.font.SysFont("consolas", 18)
        self.font_lg = pygame.font.SysFont("consolas", 22, bold=True)

        self.rng = random.Random(7)
        self.apt = Apartment()
        self.robot = Robot(0, 0)
        self.owner = Owner(0, 0)
        self.iot = IoTNetwork.default()

        # perception: real webcam if installed and not mock; otherwise mock
        self.emotion: EmotionDetector = self._build_emotion_detector()
        self.emotion.start()

        self.skills = Skills(self.apt, self.robot, self.owner, self.iot, self.emotion)
        self.memory = MemoryStore()
        self.agent: LLMAgent | MockLLM
        try:
            self.agent = make_agent(self.skills, memory=self.memory)
        except Exception as e:
            print(f"[warning] LLM init failed ({e}); falling back to MockLLM.")
            self.agent = MockLLM(self.skills, memory=self.memory)

        self.reset_scenario()

        # UI state
        self.input_active = False
        self.input_text = ""
        self.agent_busy = False
        self.last_agent_summary = ""
        self.status_msg = "Press Enter and type a request. Esc to quit."

        self._anim_accumulator = 0
        self._dt_for_iot = 1.0 / config.FPS

        # Owner wanders the apartment between turns. Pure UI animation —
        # Skills/eval don't see it (they only run in headless contexts).
        self._owner_path: list[tuple[int, int]] = []
        self._owner_step_accum = 0
        self._owner_idle_frames = 0
        self.OWNER_STEP_FRAMES = config.ROBOT_STEP_FRAMES * 2   # walks slower than robot
        self.OWNER_IDLE_FRAMES = config.FPS * 6                 # ~6s between trips

    # ---- setup ----

    def _build_emotion_detector(self) -> EmotionDetector:
        if config.USE_MOCK_EMOTION:
            return MockEmotionDetector()
        try:
            import cv2  # noqa: F401
            from deepface import DeepFace  # noqa: F401
            return DeepFaceEmotionDetector()
        except Exception:
            print("[info] DeepFace/OpenCV unavailable — using MockEmotionDetector. "
                  "Press 1..6 to inject emotions.")
            return MockEmotionDetector()

    def reset_scenario(self) -> None:
        place_in_room(self.robot, self.apt, "living_room", self.rng)
        place_in_room(self.owner, self.apt, random_room(self.apt, "living_room", self.rng), self.rng)
        self.skills.pending_path.clear()
        self.skills.dialogue.clear()
        self.skills.owner_found = False
        if isinstance(self.agent, (LLMAgent,)):
            self.agent.history.clear()
        # Stop any in-flight owner walk so the owner starts fresh in the new room.
        if hasattr(self, "_owner_path"):
            self._owner_path.clear()
            self._owner_step_accum = 0
            self._owner_idle_frames = 0

    # ---- main loop ----

    def run(self) -> None:
        running = True
        while running:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                elif ev.type == pygame.KEYDOWN:
                    running = self._handle_key(ev)

            self._tick(1.0 / config.FPS)
            self._draw()
            pygame.display.flip()
            self.clock.tick(config.FPS)

        self.emotion.stop()
        pygame.quit()

    def _handle_key(self, ev) -> bool:
        if self.input_active:
            if ev.key == pygame.K_RETURN:
                msg = self.input_text.strip()
                self.input_text = ""
                self.input_active = False
                if msg:
                    self._run_agent_async(msg)
            elif ev.key == pygame.K_ESCAPE:
                self.input_text = ""
                self.input_active = False
            elif ev.key == pygame.K_BACKSPACE:
                self.input_text = self.input_text[:-1]
            else:
                ch = ev.unicode
                if ch and ch.isprintable():
                    self.input_text += ch
            return True

        if ev.key == pygame.K_ESCAPE:
            return False
        if ev.key == pygame.K_RETURN:
            self.input_active = True
            return True
        if ev.key == pygame.K_r:
            self.reset_scenario()
            self.status_msg = "Scenario reset."
            return True
        if ev.key == pygame.K_w:
            self._toggle_webcam()
            return True
        # emotion injection
        digits = {pygame.K_1: "happy", pygame.K_2: "sad", pygame.K_3: "angry",
                  pygame.K_4: "surprised", pygame.K_5: "neutral", pygame.K_6: "tired"}
        if ev.key in digits and isinstance(self.emotion, MockEmotionDetector):
            self.emotion.inject(digits[ev.key])
            self.status_msg = f"Injected mock emotion: {digits[ev.key]}"
        return True

    def _toggle_webcam(self) -> None:
        if isinstance(self.emotion, DeepFaceEmotionDetector):
            self.emotion.stop()
            self.emotion = MockEmotionDetector()
            self.emotion.start()
            self.skills.emotion = self.emotion
            self.status_msg = "Webcam OFF (using mock emotions; press 1..6)."
        else:
            try:
                new = DeepFaceEmotionDetector()
                new.start()
                self.emotion.stop()
                self.emotion = new
                self.skills.emotion = self.emotion
                self.status_msg = "Webcam ON (DeepFace)."
            except Exception as e:
                self.status_msg = f"Webcam failed: {e}"

    # ---- per-frame update ----

    def _tick(self, dt: float) -> None:
        # animate robot along pending path
        self._anim_accumulator += 1
        if self._anim_accumulator >= config.ROBOT_STEP_FRAMES and self.skills.pending_path:
            self._anim_accumulator = 0
            self.robot.x, self.robot.y = self.skills.pending_path.pop(0)
        self._tick_owner()
        self.iot.tick(dt)

    def _tick_owner(self) -> None:
        """Owner wanders to a new random room every few seconds.

        Paused while the agent is mid-turn so the scene stays readable during
        dialogue / IoT actions. Owner walks at half the robot's speed so the
        viewer can tell who is who.
        """
        if self.agent_busy:
            return
        if self._owner_path:
            self._owner_step_accum += 1
            if self._owner_step_accum >= self.OWNER_STEP_FRAMES:
                self._owner_step_accum = 0
                self.owner.x, self.owner.y = self._owner_path.pop(0)
                # If the owner walks away from the robot, mark them un-found so
                # subsequent agent turns will re-locate them.
                if self.apt.room_name_at(*self.owner.pos) != self.apt.room_name_at(*self.robot.pos):
                    self.skills.owner_found = False
            return
        # No active path — wait OWNER_IDLE_FRAMES, then plan a new trip.
        self._owner_idle_frames += 1
        if self._owner_idle_frames >= self.OWNER_IDLE_FRAMES:
            self._owner_idle_frames = 0
            self._plan_owner_trip()

    def _plan_owner_trip(self) -> None:
        """Pick a random different room and compute an A* path to a tile in it."""
        from .planning.navigator import astar
        current = self.apt.room_name_at(*self.owner.pos)
        others = [r for r in self.apt.room_names() if r != current]
        if not others:
            return
        target_room = self.apt.room(self.rng.choice(others))
        candidates = [(x, y)
                      for x in range(target_room.x0, target_room.x1 + 1)
                      for y in range(target_room.y0, target_room.y1 + 1)
                      if self.apt.is_walkable(x, y)]
        if not candidates:
            return
        target = self.rng.choice(candidates)
        path = astar(self.apt, self.owner.pos, target)
        if path and len(path) > 1:
            self._owner_path = path[1:]   # skip current position

    # ---- agent ----

    def _run_agent_async(self, message: str) -> None:
        if self.agent_busy:
            self.status_msg = "Agent is still working on the previous request."
            return
        self.agent_busy = True
        self.status_msg = f"Sending to LLM: {message[:80]}"
        self.skills.dialogue.append(("you", message))

        def worker() -> None:
            try:
                res: TurnResult = self.agent.run_turn(message)
                self.last_agent_summary = res.final_text or "(no summary)"
                self.status_msg = f"Agent done. {self.last_agent_summary[:80]}"
            except Exception as e:
                self.skills.dialogue.append(("system", f"[agent error] {e}"))
                self.status_msg = f"Agent error: {e}"
            finally:
                self.agent_busy = False

        threading.Thread(target=worker, daemon=True).start()

    # ---- rendering ----

    def _draw(self) -> None:
        self.screen.fill(config.PALETTE.bg)
        self._draw_world()
        self._draw_sidebar()
        self._draw_topbar()
        if self.input_active:
            self._draw_input_box()

    def _draw_world(self) -> None:
        T = config.TILE_PX
        offset_y = config.INFOBAR_PX
        # floors (per room tint)
        for r in self.apt.rooms:
            tint = config.PALETTE.room_tint.get(r.name, config.PALETTE.floor)
            rect = pygame.Rect(r.x0 * T, r.y0 * T + offset_y,
                               (r.x1 - r.x0 + 1) * T, (r.y1 - r.y0 + 1) * T)
            pygame.draw.rect(self.screen, tint, rect)
        # grid
        for x in range(self.apt.cols + 1):
            pygame.draw.line(self.screen, config.PALETTE.grid_line,
                             (x * T, offset_y), (x * T, offset_y + self.apt.rows * T))
        for y in range(self.apt.rows + 1):
            pygame.draw.line(self.screen, config.PALETTE.grid_line,
                             (0, offset_y + y * T), (self.apt.cols * T, offset_y + y * T))
        # walls
        for (x, y) in self.apt.walls():
            if self.apt.is_door(x, y):
                continue
            rect = pygame.Rect(x * T, y * T + offset_y, T, T)
            pygame.draw.rect(self.screen, config.PALETTE.wall, rect)
        # doors
        for (x, y) in self.apt.doors():
            rect = pygame.Rect(x * T + T // 4, y * T + offset_y + T // 4, T // 2, T // 2)
            pygame.draw.rect(self.screen, config.PALETTE.door, rect, border_radius=4)
        # room labels
        for r in self.apt.rooms:
            label = self.font_sm.render(r.name, True, config.PALETTE.text_dim)
            self.screen.blit(label, (r.x0 * T + 6, r.y0 * T + offset_y + 4))
        # IoT devices
        for d in self.iot.list():
            self._draw_device(d, offset_y)
        # pending path (visual trail)
        if self.skills.pending_path:
            for (x, y) in self.skills.pending_path:
                rect = pygame.Rect(x * T + T // 3, y * T + offset_y + T // 3, T // 3, T // 3)
                pygame.draw.rect(self.screen, (110, 190, 250), rect, border_radius=2)
        # robot
        rx, ry = self.robot.pos
        pygame.draw.circle(self.screen, config.PALETTE.robot,
                           (rx * T + T // 2, ry * T + offset_y + T // 2), T // 2 - 4)
        # robot eye
        pygame.draw.circle(self.screen, (20, 30, 40),
                           (rx * T + T // 2, ry * T + offset_y + T // 2), 3)
        # owner
        ox, oy = self.owner.pos
        pygame.draw.rect(self.screen, config.PALETTE.owner,
                         (ox * T + 5, oy * T + offset_y + 5, T - 10, T - 10), border_radius=4)

    DEVICE_SLOTS = {
        "curtain":      (1, 1),     # top-left
        "lamp":         (-1, 1),    # top-right
        "thermostat":   (1, 2),     # left, second row
        "tv":           (-2, 2),    # right-center
        "toaster":      (-1, -1),   # bottom-right
        "coffee_maker": (1, -1),    # bottom-left
        "speaker":      (-1, -2),   # bottom-right, one up
        "fan":          (1, -2),    # bottom-left, one up
        "door_lock":    (-1, 1),    # default fallback
    }

    def _draw_device(self, dev, offset_y: int) -> None:
        T = config.TILE_PX
        room = self.apt.room(dev.room)
        dx, dy = self.DEVICE_SLOTS.get(dev.kind, (1, 1))
        x = room.x1 + dx if dx < 0 else room.x0 + dx
        y = room.y1 + dy if dy < 0 else room.y0 + dy
        x = max(room.x0, min(room.x1, x))
        y = max(room.y0, min(room.y1, y))
        cx, cy = x * T + T // 2, y * T + offset_y + T // 2
        if dev.kind == "curtain":
            color = (200, 200, 220) if dev.state.get("open") else (90, 90, 140)
            pygame.draw.rect(self.screen, color,
                             (x * T + 3, y * T + offset_y + 3, T - 6, T - 6), border_radius=3)
            tag = "C-O" if dev.state.get("open") else "C-X"
        elif dev.kind == "lamp":
            on = dev.state.get("on")
            color = (255, 230, 130) if on else (110, 100, 80)
            pygame.draw.circle(self.screen, color, (cx, cy), T // 2 - 6)
            tag = "L+" if on else "L-"
        elif dev.kind == "toaster":
            running = dev.state.get("running")
            color = (220, 110, 80) if running else (150, 150, 160)
            pygame.draw.rect(self.screen, color,
                             (x * T + 4, y * T + offset_y + 6, T - 8, T - 12), border_radius=2)
            tag = f"T{int(dev.state.get('progress', 0)*100)}%"
        elif dev.kind == "coffee_maker":
            brewing = dev.state.get("brewing")
            color = (140, 90, 60) if brewing else (90, 70, 55)
            pygame.draw.rect(self.screen, color,
                             (x * T + 4, y * T + offset_y + 4, T - 8, T - 8), border_radius=2)
            tag = f"K{dev.state.get('cups',0)}"
        elif dev.kind == "thermostat":
            mode = dev.state.get("mode", "off")
            color = (200, 100, 80) if mode == "heat" else (
                (90, 160, 220) if mode == "cool" else (
                    (160, 160, 170) if mode == "off" else (130, 200, 150)))
            pygame.draw.circle(self.screen, color, (cx, cy), T // 2 - 8)
            tag = f"{dev.state.get('target_c', 0):.0f}C"
        elif dev.kind == "tv":
            on = dev.state.get("on")
            color = (140, 200, 240) if on else (60, 60, 70)
            pygame.draw.rect(self.screen, color,
                             (x * T + 4, y * T + offset_y + 8, T - 8, T - 16), border_radius=2)
            tag = dev.state.get("channel", "")[:3].upper() if on else "TV-"
        elif dev.kind == "speaker":
            playing = dev.state.get("playing")
            color = (180, 140, 220) if playing else (80, 70, 90)
            pygame.draw.rect(self.screen, color,
                             (x * T + 8, y * T + offset_y + 4, T - 16, T - 8), border_radius=4)
            tag = dev.state.get("playlist", "")[:3].upper() if playing else "SP-"
        elif dev.kind == "fan":
            on = dev.state.get("on")
            color = (130, 200, 220) if on else (90, 100, 110)
            pygame.draw.circle(self.screen, color, (cx, cy), T // 2 - 6, width=3)
            tag = f"F{dev.state.get('speed',0)}" if on else "F-"
        elif dev.kind == "door_lock":
            locked = dev.state.get("locked")
            color = (220, 180, 80) if not locked else (140, 110, 60)
            pygame.draw.rect(self.screen, color,
                             (x * T + 6, y * T + offset_y + 6, T - 12, T - 12), border_radius=6)
            tag = "LOCK" if locked else "OPEN"
        else:
            tag = dev.kind[:2]
        lbl = self.font_sm.render(tag, True, config.PALETTE.text)
        self.screen.blit(lbl, (x * T + 2, y * T + offset_y + T - 14))

    def _draw_topbar(self) -> None:
        pygame.draw.rect(self.screen, (32, 32, 38),
                         (0, 0, config.WINDOW_W, config.INFOBAR_PX))
        reading = self.emotion.poll()
        em = f"emotion: {reading.label} ({reading.confidence:.2f})" if reading else "emotion: --"
        room = f"robot: {self.skills.robot_room()}"
        busy = "  [LLM thinking...]" if self.agent_busy else ""
        line = f"{room}   |   {em}   |   {self.status_msg}{busy}"
        self.screen.blit(self.font_md.render(line, True, config.PALETTE.text), (10, 10))

    def _draw_sidebar(self) -> None:
        x0 = config.GRID_COLS * config.TILE_PX
        pygame.draw.rect(self.screen, (30, 30, 36),
                         (x0, config.INFOBAR_PX, config.SIDEBAR_PX,
                          config.WINDOW_H - config.INFOBAR_PX))
        # dialogue
        self.screen.blit(self.font_lg.render("Dialogue", True, config.PALETTE.accent),
                         (x0 + 12, config.INFOBAR_PX + 10))
        y = config.INFOBAR_PX + 44
        for speaker, text in self.skills.dialogue[-18:]:
            color = config.PALETTE.good if speaker == "robot" else (
                config.PALETTE.warn if speaker == "you" else config.PALETTE.bad)
            tag = self.font_sm.render(f"{speaker}:", True, color)
            self.screen.blit(tag, (x0 + 12, y))
            wrapped = self._wrap(text, max_chars=44)
            for line in wrapped:
                self.screen.blit(self.font_sm.render(line, True, config.PALETTE.text),
                                 (x0 + 70, y))
                y += 16
            y += 6
        # bottom: keys
        keys = ["Enter: ask  |  1..6: emotion  |  w: webcam toggle",
                "r: reset scenario  |  Esc: quit"]
        for i, k in enumerate(keys):
            self.screen.blit(self.font_sm.render(k, True, config.PALETTE.text_dim),
                             (x0 + 12, config.WINDOW_H - 38 + i * 16))

    def _draw_input_box(self) -> None:
        w, h = 600, 56
        x = (config.WINDOW_W - w) // 2
        y = config.WINDOW_H - h - 60
        pygame.draw.rect(self.screen, (40, 42, 50), (x, y, w, h), border_radius=6)
        pygame.draw.rect(self.screen, config.PALETTE.accent, (x, y, w, h), 2, border_radius=6)
        self.screen.blit(self.font_md.render("> " + self.input_text + "|", True,
                                              config.PALETTE.text), (x + 12, y + 16))

    @staticmethod
    def _wrap(text: str, max_chars: int) -> list[str]:
        words = text.split()
        lines: list[str] = []
        cur = ""
        for w in words:
            if len(cur) + 1 + len(w) <= max_chars:
                cur = (cur + " " + w).strip()
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines or [""]


def main() -> int:
    App().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
