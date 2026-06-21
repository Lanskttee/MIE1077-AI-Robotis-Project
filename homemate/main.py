"""Pygame entry point: top-down apartment + dialogue panel.

Run with::

    python -m homemate.main
    python -m homemate.main --offline --owner-room bedroom --emotion tired
    python -m homemate.main --script tired_coffee --auto-run

Key bindings:
    Enter   open the input field; type a request, press Enter to send
    1..6    inject mock emotion (happy / sad / angry / surprised / neutral / tired)
    Tab     cycle sidebar panel (Dialogue / Actions / Memory / Devices)
    d/a/m/i jump to Dialogue / Actions / Memory / Devices panel
    PgUp/Dn scroll the dialogue panel
    F5      save world snapshot (robot, owner, all IoT states)
    F9      load last saved snapshot
    p       toggle session replay mode (step through recorded turns)
    [/]     previous / next replay turn (when replay mode is on)
    v       open Replay sidebar panel
    w       toggle real webcam emotion detection on/off
    r       reset scenario (re-randomise owner position)
    c       clear long-term memory store
    Esc     quit
"""

from __future__ import annotations

import os
import random
import sys
import threading
from typing import Any

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
from .session import ReplayController, SessionStore, TurnRecord  # noqa: E402
from .ui_options import MainOptions, parse_main_args  # noqa: E402
from .ui_devices import format_device_summary, group_devices_by_room  # noqa: E402
from .ui_trace import format_tool_step  # noqa: E402
from .world_snapshot import capture_world, load_snapshot, restore_world, save_snapshot  # noqa: E402
from .world.apartment import Apartment  # noqa: E402
from .world.entities import Owner, Robot, place_in_room, random_room  # noqa: E402
from .world.iot import IoTNetwork  # noqa: E402


SIDEBAR_PANELS = ("dialogue", "trace", "memory", "devices", "replay")
AUTO_RUN_DELAY_FRAMES = 45


# ---------------------------------------------------------------------------
# Application state
# ---------------------------------------------------------------------------


class App:
    def __init__(self, opts: MainOptions | None = None) -> None:
        self.opts = opts or MainOptions()
        pygame.init()
        agent_tag = "MockLLM" if self.opts.mock_llm else "Agent"
        caption = f"HomeMate — {agent_tag} demo"
        if self.opts.script:
            caption += f" [{self.opts.script}]"
        pygame.display.set_caption(caption)
        self.screen = pygame.display.set_mode((config.WINDOW_W, config.WINDOW_H))
        self.clock = pygame.time.Clock()
        self.font_sm = pygame.font.SysFont("consolas", 14)
        self.font_md = pygame.font.SysFont("consolas", 18)
        self.font_lg = pygame.font.SysFont("consolas", 22, bold=True)

        self.rng = random.Random(self.opts.seed)
        self.apt = Apartment()
        self.robot = Robot(0, 0)
        self.owner = Owner(0, 0)
        self.iot = IoTNetwork.default()

        self.emotion: EmotionDetector = self._build_emotion_detector()
        self.emotion.start()
        if self.opts.emotion and isinstance(self.emotion, MockEmotionDetector):
            self.emotion.inject(self.opts.emotion)

        self.skills = Skills(self.apt, self.robot, self.owner, self.iot, self.emotion)
        self.memory = MemoryStore()
        self.session_store = SessionStore()
        self.replay: ReplayController | None = None
        self.replay_mode = False
        self.agent: LLMAgent | MockLLM = self._build_agent()

        # UI state
        self.input_active = False
        self.input_text = ""
        self.agent_busy = False
        self.last_agent_summary = ""
        self.last_tool_trace: list[dict[str, Any]] = []
        self.sidebar_panel = "dialogue"
        self.dialogue_scroll = 0
        self.status_msg = self._startup_status()

        self._anim_accumulator = 0
        self._dt_for_iot = 1.0 / config.FPS

        # Owner wanders between turns unless frozen for scripted demos.
        self._owner_path: list[tuple[int, int]] = []
        self._owner_step_accum = 0
        self._owner_idle_frames = 0
        self.OWNER_STEP_FRAMES = config.ROBOT_STEP_FRAMES * 2
        self.OWNER_IDLE_FRAMES = config.FPS * 6

        self._auto_run_message: str | None = self.opts.auto_message
        self._auto_run_frames = 0

        self.reset_scenario(initial=True)
        if self.opts.load_snapshot:
            try:
                self._restore_snapshot_from(self.opts.load_snapshot)
                self.status_msg = f"Loaded snapshot: {self.opts.load_snapshot}"
            except (OSError, ValueError) as e:
                self.status_msg = f"Snapshot load failed: {e}"
        elif self.opts.replay_session:
            self._load_replay_session(self.opts.replay_session)
        elif self.opts.record_session:
            title = self.opts.session_title or (
                f"script:{self.opts.script}" if self.opts.script else "Pygame demo"
            )
            self.session_store.start_session(
                title=title,
                script=self.opts.script,
                opts={
                    "seed": self.opts.seed,
                    "owner_room": self.opts.owner_room,
                    "emotion": self.opts.emotion,
                    "mock_llm": self.opts.mock_llm,
                },
            )
            self.status_msg = f"Recording session: {self.session_store.active.session_id}"

    # ---- setup ----

    def _build_agent(self) -> LLMAgent | MockLLM:
        if self.opts.mock_llm:
            return MockLLM(self.skills, memory=self.memory)
        try:
            return make_agent(self.skills, memory=self.memory)
        except Exception as e:
            print(f"[warning] LLM init failed ({e}); falling back to MockLLM.")
            return MockLLM(self.skills, memory=self.memory)

    def _build_emotion_detector(self) -> EmotionDetector:
        if self.opts.mock_emotion or config.USE_MOCK_EMOTION:
            return MockEmotionDetector()
        try:
            import cv2  # noqa: F401
            from deepface import DeepFace  # noqa: F401
            return DeepFaceEmotionDetector()
        except Exception:
            print("[info] DeepFace/OpenCV unavailable — using MockEmotionDetector. "
                  "Press 1..6 to inject emotions.")
            return MockEmotionDetector()

    def _startup_status(self) -> str:
        parts = ["Press Enter to ask. Tab: sidebar panels."]
        if isinstance(self.emotion, MockEmotionDetector):
            if self.opts.emotion:
                parts.append(f"Mock emotion preset: {self.opts.emotion}.")
            else:
                parts.append("Press 1..6 to inject mock emotion first.")
        if self.opts.freeze_owner:
            parts.append("Owner frozen.")
        if self._auto_run_message:
            parts.append(f"Auto-run pending: {self._auto_run_message[:40]}...")
        return "  ".join(parts)

    def reset_scenario(self, *, initial: bool = False) -> None:
        place_in_room(self.robot, self.apt, "living_room", self.rng)
        if self.opts.owner_room:
            owner_room = self.opts.owner_room
        else:
            owner_room = random_room(self.apt, "living_room", self.rng)
        place_in_room(self.owner, self.apt, owner_room, self.rng)
        self.skills.pending_path.clear()
        if not initial:
            self.skills.dialogue.clear()
            self.dialogue_scroll = 0
        self.skills.owner_found = False
        self.last_tool_trace.clear()
        if isinstance(self.agent, LLMAgent):
            self.agent.history.clear()
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
            self._tick_auto_run()
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
            if self.replay_mode:
                self.status_msg = "Replay mode — press p to exit before sending new requests."
                return True
            self.input_active = True
            return True
        if ev.key == pygame.K_r:
            self.reset_scenario()
            self.status_msg = "Scenario reset."
            return True
        if ev.key == pygame.K_w:
            self._toggle_webcam()
            return True
        if ev.key == pygame.K_TAB:
            idx = SIDEBAR_PANELS.index(self.sidebar_panel)
            self.sidebar_panel = SIDEBAR_PANELS[(idx + 1) % len(SIDEBAR_PANELS)]
            return True
        if ev.key == pygame.K_d:
            self.sidebar_panel = "dialogue"
            return True
        if ev.key == pygame.K_a:
            self.sidebar_panel = "trace"
            return True
        if ev.key == pygame.K_m:
            self.sidebar_panel = "memory"
            return True
        if ev.key == pygame.K_i:
            self.sidebar_panel = "devices"
            return True
        if ev.key == pygame.K_v:
            self.sidebar_panel = "replay"
            return True
        if ev.key == pygame.K_p:
            self._toggle_replay_mode()
            return True
        if ev.key == pygame.K_LEFTBRACKET:
            self._step_replay(-1)
            return True
        if ev.key == pygame.K_RIGHTBRACKET:
            self._step_replay(1)
            return True
        if ev.key == pygame.K_F5:
            self._save_snapshot_to_default()
            return True
        if ev.key == pygame.K_F9:
            self._restore_snapshot_from(self.opts.snapshot_path)
            return True
        if ev.key == pygame.K_c:
            self.memory.reset()
            self.status_msg = "Long-term memory cleared."
            self.sidebar_panel = "memory"
            return True
        if ev.key == pygame.K_PAGEUP:
            self.dialogue_scroll = max(0, self.dialogue_scroll - 3)
            return True
        if ev.key == pygame.K_PAGEDOWN:
            self.dialogue_scroll += 3
            return True
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
        self._anim_accumulator += 1
        if self._anim_accumulator >= config.ROBOT_STEP_FRAMES and self.skills.pending_path:
            self._anim_accumulator = 0
            self.robot.x, self.robot.y = self.skills.pending_path.pop(0)
            self.skills.robot_ctrl.update_map()
            res = self.skills.replan_if_needed(teleport=False)
            if res and res.get("replanned"):
                self.status_msg = (
                    f"Replan ({res.get('reason')}): "
                    f"{res.get('tile_steps')} tiles, planner={res.get('planner')}"
                )
        if not self.opts.freeze_owner:
            self._tick_owner()
        self.iot.tick(dt)

    def _tick_auto_run(self) -> None:
        if not self._auto_run_message or self.agent_busy:
            return
        self._auto_run_frames += 1
        if self._auto_run_frames >= AUTO_RUN_DELAY_FRAMES:
            msg = self._auto_run_message
            self._auto_run_message = None
            self._run_agent_async(msg)

    def _capture_snapshot_payload(self) -> dict[str, Any]:
        return capture_world(
            robot=self.robot,
            owner=self.owner,
            iot=self.iot,
            seed=self.opts.seed,
            owner_room=self.opts.owner_room,
            script=self.opts.script,
        )

    def _save_snapshot_to_default(self) -> None:
        try:
            path = save_snapshot(self.opts.snapshot_path, self._capture_snapshot_payload())
            self.status_msg = f"Saved snapshot -> {path}"
            self.sidebar_panel = "devices"
        except OSError as e:
            self.status_msg = f"Snapshot save failed: {e}"

    def _restore_snapshot_from(self, path: str) -> None:
        data = load_snapshot(path)
        restore_world(data, robot=self.robot, owner=self.owner, iot=self.iot)
        self.skills.pending_path.clear()
        self.skills.owner_found = (
            self.apt.room_name_at(*self.robot.pos) == self.apt.room_name_at(*self.owner.pos)
        )

    def _load_replay_session(self, session_id_or_path: str) -> None:
        try:
            rec = self.session_store.load(session_id_or_path)
        except (OSError, ValueError) as e:
            self.status_msg = f"Replay load failed: {e}"
            return
        self.replay = ReplayController(rec)
        self.replay_mode = True
        self._apply_replay_turn()
        self.sidebar_panel = "replay"
        self.status_msg = self.replay.summary_line()

    def _toggle_replay_mode(self) -> None:
        if self.replay is None:
            active = self.session_store.active
            if active and active.turns:
                self.replay = ReplayController(active)
            else:
                self.status_msg = "No recorded turns to replay yet."
                return
        self.replay_mode = not self.replay_mode
        if self.replay_mode:
            self._apply_replay_turn()
            self.sidebar_panel = "replay"
            self.status_msg = self.replay.summary_line() if self.replay else "Replay on."
        else:
            self.status_msg = "Replay mode off — live demo resumed."

    def _step_replay(self, delta: int) -> None:
        if self.replay is None or not self.replay.turn_count:
            self.status_msg = "No session loaded for replay."
            return
        if not self.replay_mode:
            self.replay_mode = True
        self.replay.step(delta)
        self._apply_replay_turn()
        self.status_msg = self.replay.summary_line()

    def _apply_replay_turn(self) -> None:
        if self.replay is None:
            return
        self.replay.apply_world(
            robot=self.robot, owner=self.owner, iot=self.iot, phase="after",
        )
        self.skills.pending_path.clear()
        self.skills.owner_found = (
            self.apt.room_name_at(*self.robot.pos) == self.apt.room_name_at(*self.owner.pos)
        )
        turn = self.replay.current
        if turn is None:
            return
        self.skills.dialogue = self.replay.dialogue_upto_current()
        self.last_tool_trace = list(turn.tool_trace)
        self.last_agent_summary = turn.final_text
        self.dialogue_scroll = 0

    def _tick_owner(self) -> None:
        if self.agent_busy:
            return
        if self._owner_path:
            self._owner_step_accum += 1
            if self._owner_step_accum >= self.OWNER_STEP_FRAMES:
                self._owner_step_accum = 0
                self.owner.x, self.owner.y = self._owner_path.pop(0)
                if self.apt.room_name_at(*self.owner.pos) != self.apt.room_name_at(*self.robot.pos):
                    self.skills.owner_found = False
                if self.skills.pending_path:
                    self.skills.replan_if_needed(teleport=False)
            return
        self._owner_idle_frames += 1
        if self._owner_idle_frames >= self.OWNER_IDLE_FRAMES:
            self._owner_idle_frames = 0
            self._plan_owner_trip()

    def _plan_owner_trip(self) -> None:
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
            self._owner_path = path[1:]

    # ---- agent ----

    def _run_agent_async(self, message: str) -> None:
        if self.replay_mode:
            self.status_msg = "Exit replay mode (p) before sending a new request."
            return
        if self.agent_busy:
            self.status_msg = "Agent is still working on the previous request."
            return
        world_before = self._capture_snapshot_payload()
        self.agent_busy = True
        agent_name = "MockLLM" if isinstance(self.agent, MockLLM) else "Agent"
        self.status_msg = f"Sending to {agent_name}: {message[:60]}"
        self.skills.dialogue.append(("you", message))

        def worker() -> None:
            try:
                res: TurnResult = self.agent.run_turn(message)
                self.last_tool_trace = list(res.tool_trace)
                self.last_agent_summary = res.final_text or "(no summary)"
                n_ok = sum(1 for s in res.tool_trace
                           if (s.get("output") or {}).get("ok"))
                n_fail = len(res.tool_trace) - n_ok
                self.status_msg = (
                    f"Done ({n_ok} ok"
                    + (f", {n_fail} failed" if n_fail else "")
                    + f"). {self.last_agent_summary[:50]}"
                )
                if n_fail:
                    self.skills.dialogue.append(
                        ("system", f"{n_fail} tool step(s) failed — open Actions panel (a)."))
                self.sidebar_panel = "trace"
                self._record_turn(message, world_before, res)
            except Exception as e:
                self.last_tool_trace = []
                self.skills.dialogue.append(("system", f"[agent error] {e}"))
                self.status_msg = f"Agent error: {e}"
                self.sidebar_panel = "trace"
            finally:
                self.agent_busy = False

        threading.Thread(target=worker, daemon=True).start()

    def _record_turn(self, message: str, world_before: dict[str, Any],
                     res: TurnResult) -> None:
        if not self.opts.record_session or self.session_store.active is None:
            return
        emotion_label: str | None = None
        for step in res.tool_trace:
            if step.get("name") == "read_emotion":
                out = step.get("output") or {}
                if out.get("ok"):
                    emotion_label = out.get("emotion")
        turn = TurnRecord(
            timestamp="",
            user_message=message,
            world_before=world_before,
            world_after=self._capture_snapshot_payload(),
            tool_trace=list(res.tool_trace),
            spoken=list(res.spoken),
            final_text=res.final_text,
            emotion_label=emotion_label,
        )
        self.session_store.append_turn(turn)
        self.replay = ReplayController(self.session_store.active)
        self.status_msg += f"  [saved turn {len(self.session_store.active.turns)}]"

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
        for r in self.apt.rooms:
            tint = config.PALETTE.room_tint.get(r.name, config.PALETTE.floor)
            rect = pygame.Rect(r.x0 * T, r.y0 * T + offset_y,
                               (r.x1 - r.x0 + 1) * T, (r.y1 - r.y0 + 1) * T)
            pygame.draw.rect(self.screen, tint, rect)
        for x in range(self.apt.cols + 1):
            pygame.draw.line(self.screen, config.PALETTE.grid_line,
                             (x * T, offset_y), (x * T, offset_y + self.apt.rows * T))
        for y in range(self.apt.rows + 1):
            pygame.draw.line(self.screen, config.PALETTE.grid_line,
                             (0, offset_y + y * T), (self.apt.cols * T, offset_y + y * T))
        for (x, y) in self.apt.walls():
            if self.apt.is_door(x, y):
                continue
            rect = pygame.Rect(x * T, y * T + offset_y, T, T)
            pygame.draw.rect(self.screen, config.PALETTE.wall, rect)
        for (x, y) in self.apt.doors():
            rect = pygame.Rect(x * T + T // 4, y * T + offset_y + T // 4, T // 2, T // 2)
            pygame.draw.rect(self.screen, config.PALETTE.door, rect, border_radius=4)
        for r in self.apt.rooms:
            label = self.font_sm.render(r.name, True, config.PALETTE.text_dim)
            self.screen.blit(label, (r.x0 * T + 6, r.y0 * T + offset_y + 4))
        for (x, y), state in self.skills.robot_ctrl.map.cells.items():
            if state == 0:  # FREE
                rect = pygame.Rect(x * T + 2, y * T + offset_y + 2, T - 4, T - 4)
                pygame.draw.rect(self.screen, (40, 70, 50), rect, border_radius=2)
        for d in self.iot.list():
            self._draw_device(d, offset_y)
        if self.skills.pending_path:
            for (x, y) in self.skills.pending_path:
                rect = pygame.Rect(x * T + T // 3, y * T + offset_y + T // 3, T // 3, T // 3)
                pygame.draw.rect(self.screen, (110, 190, 250), rect, border_radius=2)
        rx, ry = self.robot.pos
        pygame.draw.circle(self.screen, config.PALETTE.robot,
                           (rx * T + T // 2, ry * T + offset_y + T // 2), T // 2 - 4)
        pygame.draw.circle(self.screen, (20, 30, 40),
                           (rx * T + T // 2, ry * T + offset_y + T // 2), 3)
        rob_lbl = self.font_sm.render("ROBOT", True, config.PALETTE.accent)
        self.screen.blit(rob_lbl, (rx * T + 2, ry * T + offset_y - 14))
        ox, oy = self.owner.pos
        pygame.draw.rect(self.screen, config.PALETTE.owner,
                         (ox * T + 5, oy * T + offset_y + 5, T - 10, T - 10), border_radius=4)
        own_lbl = self.font_sm.render("OWNER", True, config.PALETTE.good)
        self.screen.blit(own_lbl, (ox * T + 2, oy * T + offset_y - 14))

    DEVICE_SLOTS = {
        "curtain":      (1, 1),
        "lamp":         (-1, 1),
        "thermostat":   (1, 2),
        "tv":           (-2, 2),
        "toaster":      (-1, -1),
        "coffee_maker": (1, -1),
        "speaker":      (-1, -2),
        "fan":          (1, -2),
        "door_lock":    (-1, 1),
    }

    def _draw_progress_bar(self, x: int, y: int, w: int, h: int,
                           progress: float, fill: tuple[int, int, int]) -> None:
        progress = max(0.0, min(1.0, progress))
        pygame.draw.rect(self.screen, (35, 37, 42), (x, y, w, h), border_radius=2)
        if progress > 0:
            fill_w = max(1, int(w * progress))
            pygame.draw.rect(self.screen, fill, (x, y, fill_w, h), border_radius=2)
        pygame.draw.rect(self.screen, (70, 72, 80), (x, y, w, h), 1, border_radius=2)

    def _draw_device(self, dev, offset_y: int) -> None:
        T = config.TILE_PX
        room = self.apt.room(dev.room)
        dx, dy = self.DEVICE_SLOTS.get(dev.kind, (1, 1))
        x = room.x1 + dx if dx < 0 else room.x0 + dx
        y = room.y1 + dy if dy < 0 else room.y0 + dy
        x = max(room.x0, min(room.x1, x))
        y = max(room.y0, min(room.y1, y))
        cx, cy = x * T + T // 2, y * T + offset_y + T // 2
        tile_x, tile_y = x * T, y * T + offset_y
        progress = float(dev.state.get("progress", 0.0))

        if dev.kind == "curtain":
            open_ = dev.state.get("open")
            color = (200, 200, 220) if open_ else (90, 90, 140)
            pygame.draw.rect(self.screen, color,
                             (tile_x + 3, tile_y + 3, T - 6, T - 6), border_radius=3)
            if not open_ and progress > 0:
                self._draw_progress_bar(tile_x + 4, tile_y + T - 10, T - 8, 5,
                                        progress, (160, 170, 220))
            tag = "C-O" if open_ else "C-X"
        elif dev.kind == "lamp":
            on = dev.state.get("on")
            color = (255, 230, 130) if on else (110, 100, 80)
            pygame.draw.circle(self.screen, color, (cx, cy), T // 2 - 6)
            if on:
                bright = float(dev.state.get("brightness", 0.8))
                self._draw_progress_bar(tile_x + 4, tile_y + T - 10, T - 8, 5,
                                        bright, (255, 220, 120))
            tag = "L+" if on else "L-"
        elif dev.kind == "toaster":
            running = dev.state.get("running")
            color = (220, 110, 80) if running else (150, 150, 160)
            pygame.draw.rect(self.screen, color,
                             (tile_x + 4, tile_y + 6, T - 8, T - 12), border_radius=2)
            if running or progress > 0:
                self._draw_progress_bar(tile_x + 4, tile_y + T - 10, T - 8, 5,
                                        progress, (240, 140, 90))
            tag = f"T{int(progress * 100)}%"
        elif dev.kind == "coffee_maker":
            brewing = dev.state.get("brewing")
            color = (140, 90, 60) if brewing else (90, 70, 55)
            pygame.draw.rect(self.screen, color,
                             (tile_x + 4, tile_y + 4, T - 8, T - 8), border_radius=2)
            if brewing or progress > 0:
                self._draw_progress_bar(tile_x + 4, tile_y + T - 10, T - 8, 5,
                                        progress, (180, 120, 70))
            tag = f"K{dev.state.get('cups', 0)}"
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
                             (tile_x + 4, tile_y + 8, T - 8, T - 16), border_radius=2)
            if on:
                vol = float(dev.state.get("volume", 0.5))
                self._draw_progress_bar(tile_x + 4, tile_y + T - 10, T - 8, 5,
                                        vol, (120, 190, 230))
            tag = dev.state.get("channel", "")[:3].upper() if on else "TV-"
        elif dev.kind == "speaker":
            playing = dev.state.get("playing")
            color = (180, 140, 220) if playing else (80, 70, 90)
            pygame.draw.rect(self.screen, color,
                             (tile_x + 8, tile_y + 4, T - 16, T - 8), border_radius=4)
            if playing:
                vol = float(dev.state.get("volume", 0.5))
                self._draw_progress_bar(tile_x + 4, tile_y + T - 10, T - 8, 5,
                                        vol, (200, 160, 240))
            tag = dev.state.get("playlist", "")[:3].upper() if playing else "SP-"
        elif dev.kind == "fan":
            on = dev.state.get("on")
            color = (130, 200, 220) if on else (90, 100, 110)
            pygame.draw.circle(self.screen, color, (cx, cy), T // 2 - 6, width=3)
            if on:
                spd = float(dev.state.get("speed", 1)) / 3.0
                self._draw_progress_bar(tile_x + 4, tile_y + T - 10, T - 8, 5,
                                        spd, (100, 210, 230))
            tag = f"F{dev.state.get('speed', 0)}" if on else "F-"
        elif dev.kind == "door_lock":
            locked = dev.state.get("locked")
            color = (220, 180, 80) if not locked else (140, 110, 60)
            pygame.draw.rect(self.screen, color,
                             (tile_x + 6, tile_y + 6, T - 12, T - 12), border_radius=6)
            tag = "LOCK" if locked else "OPEN"
        else:
            tag = dev.kind[:2]
        lbl = self.font_sm.render(tag, True, config.PALETTE.text)
        self.screen.blit(lbl, (tile_x + 2, tile_y + T - 14))

    def _draw_topbar(self) -> None:
        pygame.draw.rect(self.screen, (32, 32, 38),
                         (0, 0, config.WINDOW_W, config.INFOBAR_PX))
        reading = self.emotion.poll()
        em = f"emotion: {reading.label} ({reading.confidence:.2f})" if reading else "emotion: --"
        robot_r = self.skills.robot_room()
        owner_r = self.skills.owner_room()
        agent_tag = "MockLLM" if isinstance(self.agent, MockLLM) else "Claude"
        busy = "  [thinking...]" if self.agent_busy else ""
        replay = "  [REPLAY]" if self.replay_mode else ""
        tel = self.skills.robot_ctrl.telemetry()
        mode = tel.get("mode", "idle")
        tiles = tel.get("motion", {}).get("total_tiles_traveled", 0)
        line = (f"{agent_tag}{replay}  |  robot: {robot_r} ({mode}, {tiles}t)  "
                f"owner: {owner_r}  |  {em}  |  "
                f"{self.status_msg}{busy}")
        if len(line) > 120:
            line = line[:117] + "..."
        self.screen.blit(self.font_md.render(line, True, config.PALETTE.text), (10, 10))

    def _sidebar_rect(self) -> tuple[int, int, int, int]:
        x0 = config.GRID_COLS * config.TILE_PX
        y0 = config.INFOBAR_PX
        return x0, y0, config.SIDEBAR_PX, config.WINDOW_H - config.INFOBAR_PX

    def _draw_sidebar(self) -> None:
        x0, y0, w, h = self._sidebar_rect()
        pygame.draw.rect(self.screen, (30, 30, 36), (x0, y0, w, h))
        self._draw_sidebar_tabs(x0, y0, w)
        content_top = y0 + 36
        content_bottom = config.WINDOW_H - 52
        if self.sidebar_panel == "dialogue":
            self._draw_dialogue_panel(x0, content_top, w, content_bottom)
        elif self.sidebar_panel == "trace":
            self._draw_trace_panel(x0, content_top, w, content_bottom)
        elif self.sidebar_panel == "memory":
            self._draw_memory_panel(x0, content_top, w, content_bottom)
        elif self.sidebar_panel == "devices":
            self._draw_devices_panel(x0, content_top, w, content_bottom)
        else:
            self._draw_replay_panel(x0, content_top, w, content_bottom)
        keys = [
            "Tab/d/a/m/i/v: panels  |  p/[/]: replay  |  Enter: ask",
            "F5/F9: snapshot  |  c: clear mem  |  r: reset  |  Esc: quit",
        ]
        for i, k in enumerate(keys):
            self.screen.blit(self.font_sm.render(k, True, config.PALETTE.text_dim),
                             (x0 + 12, config.WINDOW_H - 40 + i * 16))

    def _draw_sidebar_tabs(self, x0: int, y0: int, w: int) -> None:
        labels = (
            ("dialogue", "Chat"),
            ("trace", "Act"),
            ("memory", "Mem"),
            ("devices", "IoT"),
            ("replay", "Replay"),
        )
        tab_w = w // len(labels)
        for i, (key, label) in enumerate(labels):
            active = self.sidebar_panel == key
            bg = (50, 55, 68) if active else (38, 40, 48)
            rect = pygame.Rect(x0 + i * tab_w, y0, tab_w, 32)
            pygame.draw.rect(self.screen, bg, rect)
            if active:
                pygame.draw.line(self.screen, config.PALETTE.accent,
                                 (rect.left, rect.bottom - 2), (rect.right, rect.bottom - 2), 2)
            color = config.PALETTE.text if active else config.PALETTE.text_dim
            surf = self.font_sm.render(label, True, color)
            self.screen.blit(surf, surf.get_rect(center=rect.center))

    def _draw_dialogue_panel(self, x0: int, y0: int, w: int, y_max: int) -> None:
        entries = self.skills.dialogue
        page_size = 12
        max_scroll = max(0, len(entries) - page_size)
        self.dialogue_scroll = min(self.dialogue_scroll, max_scroll)
        end = len(entries) - self.dialogue_scroll
        visible = entries[max(0, end - page_size):end]
        y = y0 + 8
        for speaker, text in visible:
            if y > y_max:
                break
            color = config.PALETTE.good if speaker == "robot" else (
                config.PALETTE.warn if speaker == "you" else config.PALETTE.bad)
            tag = self.font_sm.render(f"{speaker}:", True, color)
            self.screen.blit(tag, (x0 + 12, y))
            wrapped = self._wrap(text, max_chars=40)
            for line in wrapped:
                if y > y_max:
                    break
                self.screen.blit(self.font_sm.render(line, True, config.PALETTE.text),
                                 (x0 + 68, y))
                y += 16
            y += 6

    def _draw_trace_panel(self, x0: int, y0: int, w: int, y_max: int) -> None:
        y = y0 + 4
        if not self.last_tool_trace:
            msg = "No agent run yet — send a request with Enter."
            if isinstance(self.emotion, MockEmotionDetector) and self.emotion.poll() is None:
                msg = "Tip: press 1..6 to inject emotion before asking."
            for line in self._wrap(msg, 42):
                self.screen.blit(self.font_sm.render(line, True, config.PALETTE.text_dim),
                                 (x0 + 12, y))
                y += 16
            return
        summary = f"Last turn: {len(self.last_tool_trace)} tool call(s)"
        self.screen.blit(self.font_sm.render(summary, True, config.PALETTE.accent),
                         (x0 + 12, y))
        y += 20
        for step in self.last_tool_trace:
            if y > y_max:
                break
            label, ok = format_tool_step(step)
            mark = "+" if ok else "!"
            color = config.PALETTE.good if ok else config.PALETTE.bad
            for line in self._wrap(f"{mark} {label}", 42):
                if y > y_max:
                    break
                self.screen.blit(self.font_sm.render(line, True, color), (x0 + 12, y))
                y += 16

    def _draw_memory_panel(self, x0: int, y0: int, w: int, y_max: int) -> None:
        prof = self.memory.profile()
        y = y0 + 4
        header = f"Episodes on disk: {prof.total_episodes}"
        self.screen.blit(self.font_sm.render(header, True, config.PALETTE.accent),
                         (x0 + 12, y))
        y += 20
        brief = self.memory.memory_brief()
        if not brief:
            self.screen.blit(
                self.font_sm.render("No memory yet — complete a turn first.",
                                    True, config.PALETTE.text_dim),
                (x0 + 12, y),
            )
            return
        for line in brief.split("\n"):
            if y > y_max:
                break
            for wrapped in self._wrap(line, 42):
                if y > y_max:
                    break
                self.screen.blit(self.font_sm.render(wrapped, True, config.PALETTE.text),
                                 (x0 + 12, y))
                y += 16

    def _draw_devices_panel(self, x0: int, y0: int, w: int, y_max: int) -> None:
        y = y0 + 4
        snaps = self.iot.snapshot()
        header = f"Devices ({len(snaps)}) — F5 save, F9 load"
        self.screen.blit(self.font_sm.render(header, True, config.PALETTE.accent),
                         (x0 + 12, y))
        y += 20
        grouped = group_devices_by_room(snaps)
        for room, devices in grouped.items():
            if y > y_max:
                break
            self.screen.blit(
                self.font_sm.render(room, True, config.PALETTE.warn),
                (x0 + 12, y),
            )
            y += 16
            for snap in devices:
                if y > y_max:
                    break
                line = format_device_summary(snap)
                for wrapped in self._wrap(line, 40):
                    if y > y_max:
                        break
                    self.screen.blit(
                        self.font_sm.render(wrapped, True, config.PALETTE.text),
                        (x0 + 20, y),
                    )
                    y += 15
            y += 4

    def _draw_replay_panel(self, x0: int, y0: int, w: int, y_max: int) -> None:
        y = y0 + 4
        if self.replay is None:
            active = self.session_store.active
            if active is None:
                msg = "Session recording disabled or not started."
            else:
                msg = (
                    f"Recording: {active.session_id}\n"
                    f"Turns so far: {len(active.turns)}\n"
                    f"Complete a request, then press p to replay."
                )
            for line in msg.split("\n"):
                for wrapped in self._wrap(line, 42):
                    self.screen.blit(
                        self.font_sm.render(wrapped, True, config.PALETTE.text_dim),
                        (x0 + 12, y),
                    )
                    y += 16
            return
        meta = self.replay.turn_meta()
        header = self.replay.summary_line()
        self.screen.blit(self.font_sm.render(header, True, config.PALETTE.accent),
                         (x0 + 12, y))
        y += 20
        if meta:
            details = [
                f"Tools: {meta.get('tools_ok', 0)}/{meta.get('tool_calls', 0)} ok",
                f"Spoken lines: {meta.get('spoken_lines', 0)}",
                f"Emotion: {meta.get('emotion') or '--'}",
            ]
            for d in details:
                self.screen.blit(self.font_sm.render(d, True, config.PALETTE.text),
                                 (x0 + 12, y))
                y += 16
        y += 6
        hint = "p: toggle replay  |  [: prev  |  ]: next turn"
        self.screen.blit(self.font_sm.render(hint, True, config.PALETTE.text_dim),
                         (x0 + 12, y))
        y += 20
        self.screen.blit(self.font_sm.render("Recent sessions:", True, config.PALETTE.warn),
                         (x0 + 12, y))
        y += 16
        for row in self.session_store.list_sessions()[:6]:
            if y > y_max:
                break
            line = f"{row['session_id'][:28]}  ({row['turns']} turns)"
            self.screen.blit(self.font_sm.render(line, True, config.PALETTE.text_dim),
                             (x0 + 12, y))
            y += 15

    def _draw_input_box(self) -> None:
        box_w, box_h = 600, 56
        x = (config.WINDOW_W - box_w) // 2
        y = config.WINDOW_H - box_h - 60
        pygame.draw.rect(self.screen, (40, 42, 50), (x, y, box_w, box_h), border_radius=6)
        pygame.draw.rect(self.screen, config.PALETTE.accent, (x, y, box_w, box_h), 2, border_radius=6)
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


def main(argv: list[str] | None = None) -> int:
    opts = parse_main_args(argv)
    if opts.mock_llm:
        os.environ["HOMEMATE_USE_MOCK_LLM"] = "1"
    if opts.mock_emotion:
        os.environ["HOMEMATE_USE_MOCK_EMOTION"] = "1"
    App(opts).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
