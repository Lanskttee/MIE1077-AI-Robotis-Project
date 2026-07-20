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
from ..memory import MemoryStore, build_episode_from_turn
from .tools import TOOL_SCHEMAS, dispatch_tool


SYSTEM_PROMPT = """You are HomeMate, a friendly home companion robot living in
a four-room apartment (living_room, kitchen, bedroom, bathroom). You can move
between rooms, read your owner's facial emotion when you are in the same room,
hold short empathetic conversations, and control smart-home devices
(curtains, lamps, toaster, coffee maker, thermostat, TV, speaker, fan,
front-door lock).

Guidelines:
- For multi-step requests, you may first call `make_plan` to get a structured
  plan (find_owner -> sense_emotion -> speak -> goto_device + actuate per
  device). Read the plan, then execute its steps using the other tools. The
  plan is a suggestion — deviate when it makes sense.
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
- After operating a food or drink device (coffee maker, toaster), ALWAYS navigate
  back to the owner using `find_owner` and then `speak` to report completion,
  e.g. "Your coffee is ready!" You do not need to be told to deliver — it is
  always implied for food/drink. Never say you can't move objects.
- If the owner explicitly asks you to "bring it", "send it", "deliver", or
  "come to me": same as above — use `find_owner` then `speak`.
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
                 max_iters: int = 12,
                 memory: MemoryStore | None = None) -> None:
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
        self.memory = memory
        self.history: list[dict[str, Any]] = []

    # --- constructors ---

    @classmethod
    def from_env(cls, skills: Skills,
                 memory: MemoryStore | None = None) -> "LLMAgent":
        return cls(skills, model=LLM_MODEL,
                   api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
                   memory=memory)

    # --- run a turn ---

    def run_turn(self, user_message: str) -> TurnResult:
        room_start = self.skills.robot_room()
        self.history.append({"role": "user", "content": user_message})
        result = self._run_loop()
        self._record(user_message, room_start, result)
        return result

    def _world_brief(self) -> str:
        s = self.skills
        return json.dumps({
            "robot_room": s.robot_room(),
            "owner_room_known_to_simulator_only": s.owner_room(),  # informational
            "owner_found_this_episode": s.owner_found,
            "devices": [{"id": d.device_id, "room": d.room, "kind": d.kind,
                         "state": d.state} for d in s.iot.list()],
        }, indent=2)

    def build_system(self) -> str:
        """Assemble the full system prompt for the current turn.

        Exposed (not prefixed with _) so tests can inspect it without calling
        the real API.
        """
        parts = [SYSTEM_PROMPT,
                 "\n\nCurrent world snapshot:\n", self._world_brief()]
        if self.memory:
            brief = self.memory.memory_brief()
            if brief:
                parts.append("\n\nWhat you remember about this owner:\n")
                parts.append(brief)
        return "".join(parts)

    def _record(self, user_message: str, room_start: str | None,
                result: TurnResult) -> None:
        if not self.memory:
            return
        ep = build_episode_from_turn(
            user_message=user_message,
            robot_room_start=room_start,
            robot_room_end=self.skills.robot_room(),
            owner_room=self.skills.owner_room() if self.skills.owner_found else None,
            tool_trace=result.tool_trace,
            spoken=result.spoken,
            final_text=result.final_text,
        )
        self.memory.record_episode(ep)

    def _run_loop(self) -> TurnResult:
        result = TurnResult()
        for _ in range(self.max_iters):
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=self.build_system(),
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

    By default each turn runs the :class:`ReActPlanner` to decompose the user
    message into a sequence of sub-goals (find owner → read emotion → speak
    → goto+actuate per device) and then executes them via the same tool
    dispatch path the real LLM uses.

    Pass ``use_planner=False`` to fall back to a "no-planner" baseline used by
    the evaluation suite's ablation runs. In that mode, the agent always does
    find_owner → read_emotion → speak, then runs the legacy single-keyword IoT
    dispatch with no multi-step decomposition.
    """

    EMPATHY: dict[str, str]  # populated below from planner

    def __init__(self, skills: Skills,
                 memory: MemoryStore | None = None,
                 *, use_planner: bool = True) -> None:
        self.skills = skills
        self.memory = memory
        self.history: list[dict[str, Any]] = []
        self.use_planner = use_planner
        # Lazy import — keeps the cognition <-> planning boundary clean.
        from ..planning.react import EMPATHY, KIND_KEYWORDS, PlanExecutor, ReActPlanner
        self._planner = ReActPlanner()
        self._executor = PlanExecutor(skills, empathy_lines=EMPATHY)
        self.EMPATHY = EMPATHY
        self.KEYWORDS = KIND_KEYWORDS

    def run_turn(self, user_message: str) -> TurnResult:
        room_start = self.skills.robot_room()
        if self.use_planner:
            result = self._run_with_planner(user_message)
        else:
            result = self._run_legacy(user_message)
        self._record(user_message, room_start, result)
        return result

    # ---- planner-driven path ----

    def _run_with_planner(self, user_message: str) -> TurnResult:
        plan = self._planner.plan(user_message, skills=self.skills)
        exec_res = self._executor.execute(plan)
        result = TurnResult(
            spoken=list(exec_res.spoken),
            tool_trace=list(exec_res.tool_trace),
            final_text=f"Done. Detected emotion: {exec_res.detected_emotion}.",
        )
        return result

    # ---- legacy / "no-planner" ablation path ----

    def _run_legacy(self, user_message: str) -> TurnResult:
        result = TurnResult()

        def call(name: str, **inp: Any) -> dict[str, Any]:
            out = dispatch_tool(self.skills, name, inp)
            result.tool_trace.append({"name": name, "input": inp, "output": out})
            if name == "speak" and out.get("ok"):
                result.spoken.append(out["spoken"])
            return out

        if not self.skills.owner_found or self.skills.robot_room() != self.skills.owner_room():
            call("find_owner")

        emotion = "neutral"
        er = call("read_emotion")
        if er.get("ok"):
            emotion = er["emotion"]
        call("speak", text=self.EMPATHY.get(emotion, self.EMPATHY["neutral"]))

        msg = (user_message or "").lower()
        kinds_dispatched: set[str] = set()
        for kw, kind in self.KEYWORDS.items():
            if kw in msg and kind not in kinds_dispatched:
                self._dispatch_iot_by_keyword(kw, msg, call)
                kinds_dispatched.add(kind)

        result.final_text = f"Done. Detected emotion: {emotion}."
        return result

    def _record(self, user_message: str, room_start: str | None,
                result: TurnResult) -> None:
        if not self.memory:
            return
        ep = build_episode_from_turn(
            user_message=user_message,
            robot_room_start=room_start,
            robot_room_end=self.skills.robot_room(),
            owner_room=self.skills.owner_room() if self.skills.owner_found else None,
            tool_trace=result.tool_trace,
            spoken=result.spoken,
            final_text=result.final_text,
        )
        self.memory.record_episode(ep)

    def _dispatch_iot_by_keyword(self, kw: str, msg: str, call: Callable) -> None:
        from ..planning.react import action_for
        kind = self.KEYWORDS.get(kw)
        if kind is None:
            return
        room_hits = [r for r in ("living_room", "kitchen", "bedroom", "bathroom")
                     if r in msg or r.split("_")[0] in msg]
        target = None
        for d in self.skills.iot.list():
            if d.kind == kind and (not room_hits or d.room in room_hits):
                target = d
                break
        if target is None:
            for d in self.skills.iot.list():
                if d.kind == kind:
                    target = d
                    break
        if target is None:
            return
        action, kwargs = action_for(target.kind, msg)
        if action is None:
            return
        call("navigate_to_device", device_id=target.device_id)
        if kwargs:
            call("set_device", device_id=target.device_id, action=action, kwargs=kwargs)
        else:
            call("set_device", device_id=target.device_id, action=action)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_agent(skills: Skills,
               memory: MemoryStore | None = None) -> "LLMAgent | MockLLM":
    if USE_MOCK_LLM:
        return MockLLM(skills, memory=memory)
    from ..config import ANTHROPIC_API_KEY, OPENAI_API_KEY
    if OPENAI_API_KEY and not ANTHROPIC_API_KEY:
        from .openai_agent import OpenAIAgent
        model = os.environ.get("HOMEMATE_OPENAI_MODEL", "gpt-4o-mini")
        return OpenAIAgent(skills, model=model, api_key=OPENAI_API_KEY, memory=memory)
    return LLMAgent.from_env(skills, memory=memory)
