"""Claude tool-calling loop (and a MockLLM for offline testing).

Usage::

    agent = LLMAgent.from_env(skills)
    transcript = agent.run_turn("Find me and tell me a joke.")

The agent maintains conversation history across turns. Each turn:

1. Build a system prompt that summarises the world (rooms, devices, robot/owner).
2. Send (history + new user message) to Claude with all tools.
3. While Claude returns ``tool_use`` content blocks, dispatch them via
   ``dispatch_tool`` and feed the results back.
4. When Claude returns only ``text``, the turn ends and we return everything
   said + the tool trace for the UI.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..action.skills import Skills
from ..config import LLM_MODEL, USE_MOCK_LLM
from .tools import TOOL_SCHEMAS, dispatch_tool


SYSTEM_PROMPT = """You are HomeMate, a friendly home companion robot living in
a four-room apartment (living_room, kitchen, bedroom, bathroom). You can move
between rooms, read your owner's facial emotion when you are in the same room,
hold short empathetic conversations, and control smart-home devices
(curtains, lamps, toaster, coffee maker).

Guidelines:
- Always check where you are with `look_around` if unsure.
- If you don't know where the owner is, call `find_owner` (do NOT guess rooms one by one).
- Before speaking to the owner, make sure you are in the same room.
- Before talking emotionally, call `read_emotion` and adapt your tone:
  * sad/tired -> warm, gentle, supportive, suggest something soothing
  * angry -> calm, validating, don't push back
  * happy/surprised -> light, playful, share the energy
  * neutral -> friendly small talk
- Speak in short natural sentences (one or two at a time) via the `speak` tool.
- For IoT actions, prefer concrete device_ids returned by `look_around` or
  `list_devices`.
- When you are done, stop calling tools and produce a one-line summary of
  what you did.
"""


@dataclass
class TurnResult:
    spoken: list[str] = field(default_factory=list)
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
    final_text: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"spoken": self.spoken, "tool_trace": self.tool_trace, "final_text": self.final_text}


# ---------------------------------------------------------------------------
# Real Claude agent
# ---------------------------------------------------------------------------


class LLMAgent:
    def __init__(self, skills: Skills, *, model: str, api_key: str,
                 max_iters: int = 12) -> None:
        try:
            from anthropic import Anthropic
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "anthropic package not installed. Run `pip install -r requirements.txt`."
            ) from exc
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set (see .env.example).")
        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.skills = skills
        self.max_iters = max_iters
        self.history: list[dict[str, Any]] = []

    # --- constructors ---

    @classmethod
    def from_env(cls, skills: Skills) -> "LLMAgent":
        return cls(skills, model=LLM_MODEL, api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    # --- run a turn ---

    def run_turn(self, user_message: str) -> TurnResult:
        self.history.append({"role": "user", "content": user_message})
        return self._run_loop()

    def _world_brief(self) -> str:
        s = self.skills
        return json.dumps({
            "robot_room": s.robot_room(),
            "owner_room_known_to_simulator_only": s.owner_room(),  # informational
            "owner_found_this_episode": s.owner_found,
            "devices": [{"id": d.device_id, "room": d.room, "kind": d.kind,
                         "state": d.state} for d in s.iot.list()],
        }, indent=2)

    def _run_loop(self) -> TurnResult:
        result = TurnResult()
        for _ in range(self.max_iters):
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT + "\n\nCurrent world snapshot:\n" + self._world_brief(),
                tools=TOOL_SCHEMAS,
                messages=self.history,
            )
            assistant_blocks: list[dict[str, Any]] = []
            tool_uses: list[tuple[str, str, dict[str, Any]]] = []

            for block in resp.content:
                if block.type == "text":
                    if block.text.strip():
                        result.final_text = block.text.strip()
                    assistant_blocks.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    tool_uses.append((block.id, block.name, dict(block.input or {})))
                    assistant_blocks.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })

            self.history.append({"role": "assistant", "content": assistant_blocks})

            if not tool_uses:
                # End of turn
                return result

            tool_results_block: list[dict[str, Any]] = []
            for tool_id, name, inp in tool_uses:
                out = dispatch_tool(self.skills, name, inp)
                result.tool_trace.append({"name": name, "input": inp, "output": out})
                if name == "speak" and out.get("ok"):
                    result.spoken.append(out["spoken"])
                tool_results_block.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": json.dumps(out, ensure_ascii=False),
                })
            self.history.append({"role": "user", "content": tool_results_block})

            if resp.stop_reason != "tool_use":
                return result
        return result


# ---------------------------------------------------------------------------
# Mock LLM — deterministic scripted "agent" for offline tests
# ---------------------------------------------------------------------------


class MockLLM:
    """A deterministic stand-in for the Claude agent.

    Strategy for each turn:
      1. find_owner
      2. read_emotion
      3. speak an empathetic line based on emotion
      4. if the user message mentions an IoT verb (open/close/start/brew/on/off),
         dispatch a best-effort tool call
      5. stop
    """

    EMPATHY = {
        "happy":     "You look great today! What's making you smile?",
        "sad":       "I'm here with you. Want me to dim the lights and play something calm?",
        "angry":     "Take a breath — I'm listening. Want to tell me what happened?",
        "surprised": "Whoa, something exciting? Tell me about it!",
        "neutral":   "Hey, just checking in. Anything I can do for you?",
        "tired":     "You look a bit tired. Want me to start the coffee maker?",
    }

    KEYWORDS = {
        "curtain":  ("open",  "close", "toggle"),
        "lamp":     ("on",    "off",   "toggle"),
        "light":    ("on",    "off",   "toggle"),
        "toaster":  ("start", "stop"),
        "coffee":   ("brew",  "stop"),
    }

    def __init__(self, skills: Skills) -> None:
        self.skills = skills
        self.history: list[dict[str, Any]] = []

    def run_turn(self, user_message: str) -> TurnResult:
        result = TurnResult()

        def call(name: str, **inp: Any) -> dict[str, Any]:
            out = dispatch_tool(self.skills, name, inp)
            result.tool_trace.append({"name": name, "input": inp, "output": out})
            if name == "speak" and out.get("ok"):
                result.spoken.append(out["spoken"])
            return out

        # 1. find owner if we don't know where they are
        if not self.skills.owner_found or self.skills.robot_room() != self.skills.owner_room():
            call("find_owner")

        # 2. read emotion
        emotion = "neutral"
        er = call("read_emotion")
        if er.get("ok"):
            emotion = er["emotion"]

        # 3. speak empathetic line
        call("speak", text=self.EMPATHY.get(emotion, self.EMPATHY["neutral"]))

        # 4. naive IoT keyword dispatch
        msg = (user_message or "").lower()
        for kw, _actions in self.KEYWORDS.items():
            if kw in msg:
                self._dispatch_iot_by_keyword(kw, msg, call)

        result.final_text = f"Done. Detected emotion: {emotion}."
        return result

    def _dispatch_iot_by_keyword(self, kw: str, msg: str, call: Callable) -> None:
        # Figure out an action
        if "open" in msg:    action = "open"
        elif "close" in msg: action = "close"
        elif "start" in msg or "brew" in msg or "make" in msg: action = "start" if kw == "toaster" else "brew"
        elif "on" in msg:    action = "on"
        elif "off" in msg:   action = "off"
        else:                action = "toggle"
        # Find a matching device (prefer one whose room appears in the message)
        room_hits = [r for r in ("living_room", "kitchen", "bedroom", "bathroom") if r.split("_")[0] in msg]
        target = None
        for d in self.skills.iot.list():
            if kw not in d.kind and kw != ("light" if d.kind == "lamp" else d.kind):
                continue
            if room_hits and d.room not in room_hits:
                continue
            target = d
            break
        if target is None:
            return
        # Special-case toaster start needs action "start"
        if target.kind == "toaster":
            action = "start" if action in ("on", "open") else action
        if target.kind == "coffee_maker":
            action = "brew" if action in ("on", "open", "start") else action
        if target.kind == "curtain":
            action = action if action in ("open", "close", "toggle") else "toggle"
        if target.kind == "lamp":
            action = action if action in ("on", "off", "toggle") else "toggle"
        # Navigate near, then actuate
        call("navigate_to_device", device_id=target.device_id)
        call("set_device", device_id=target.device_id, action=action)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_agent(skills: Skills) -> "LLMAgent | MockLLM":
    if USE_MOCK_LLM:
        return MockLLM(skills)
    return LLMAgent.from_env(skills)
