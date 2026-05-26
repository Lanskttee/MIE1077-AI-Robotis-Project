"""ReAct-style high-level planner.

Decomposes a free-text user message into an ordered list of *sub-goals*
(``PlanStep``s) the robot can execute via the existing tool surface. The
planner is deterministic and stdlib-only, so it runs inside ``MockLLM`` and
inside tests without an API key. The real Claude agent can also call it as
the ``make_plan`` tool to "think before acting" on multi-step requests.

A plan is *informational*: it suggests a sequence of (tool_name, tool_input)
calls but does not run them. ``PlanExecutor`` runs a plan against the same
``dispatch_tool`` path the LLM uses, so what works for the planner works
live.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ..action.skills import Skills


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------


ROOMS = ("living_room", "kitchen", "bedroom", "bathroom")

# Free-text keyword -> IoT device kind. One source of truth for keyword routing.
KIND_KEYWORDS: dict[str, str] = {
    "curtain":     "curtain",
    "lamp":        "lamp",
    "light":       "lamp",
    "toaster":     "toaster",
    "toast":       "toaster",
    "coffee":      "coffee_maker",
    "brew":        "coffee_maker",
    "thermostat":  "thermostat",
    "temperature": "thermostat",
    "heat":        "thermostat",
    "cool":        "thermostat",
    "ac":          "thermostat",
    "tv":          "tv",
    "television":  "tv",
    "channel":     "tv",
    "speaker":     "speaker",
    "music":       "speaker",
    "playlist":    "speaker",
    "song":        "speaker",
    "fan":         "fan",
    "lock":        "door_lock",
    "door":        "door_lock",
    "unlock":      "door_lock",
}


# Empathetic openers per detected emotion.
EMPATHY: dict[str, str] = {
    "happy":     "You look great today! What's making you smile?",
    "sad":       "I'm here with you. Want me to dim the lights and play something calm?",
    "angry":     "Take a breath — I'm listening. Want to tell me what happened?",
    "surprised": "Whoa, something exciting? Tell me about it!",
    "neutral":   "Hey, just checking in. Anything I can do for you?",
    "tired":     "You look a bit tired. Want me to start the coffee maker?",
}


# ---------------------------------------------------------------------------
# Plan structures
# ---------------------------------------------------------------------------


@dataclass
class PlanStep:
    """One sub-goal in a plan.

    ``kind`` is the planner-level verb (``find_owner``, ``goto_room``,
    ``goto_device``, ``look_around``, ``sense_emotion``, ``speak``, ``actuate``).
    ``args`` carries kind-specific parameters. ``rationale`` is a short human-
    readable note explaining why the step is in the plan; it is included so the
    LLM (and human reviewers) can audit the planner's reasoning.
    """

    kind: str
    args: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "args": dict(self.args), "rationale": self.rationale}


@dataclass
class Plan:
    user_message: str
    steps: list[PlanStep] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "user_message": self.user_message,
            "steps": [s.to_json() for s in self.steps],
        }


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


class ReActPlanner:
    """Decompose a user message into an ordered sequence of sub-goals."""

    def plan(self, user_message: str, *,
             skills: Skills,
             memory_brief: str = "") -> Plan:
        msg = (user_message or "").lower()
        plan = Plan(user_message=user_message)

        # 1. Locate the owner if we don't already know where they are.
        owner_room = skills.owner_room() if skills.owner_found else None
        robot_room = skills.robot_room()
        if owner_room is None or robot_room != owner_room:
            plan.steps.append(PlanStep(
                kind="find_owner",
                rationale="Owner location unknown or not yet in robot's room.",
            ))

        # 2. Always read emotion once we are with the owner — preconditions an
        #    empathetic response.
        plan.steps.append(PlanStep(
            kind="sense_emotion",
            rationale="Read the owner's mood before responding.",
        ))

        # 3. Empathetic opener tuned to the detected emotion at execution time.
        plan.steps.append(PlanStep(
            kind="speak",
            args={"intent": "empathy"},
            rationale="Open with a line that fits the owner's current emotion.",
        ))

        # 4. Device actions. Iterate keywords in declaration order so behavior
        #    is reproducible; deduplicate by device kind so "brew coffee" does
        #    not fire twice.
        kinds_seen: set[str] = set()
        for kw, kind in KIND_KEYWORDS.items():
            if kw not in msg or kind in kinds_seen:
                continue
            target = self._pick_target_device(skills, kind, msg)
            if target is None:
                continue
            action, kwargs = action_for(kind, msg)
            if action is None:
                continue
            kinds_seen.add(kind)
            plan.steps.append(PlanStep(
                kind="goto_device",
                args={"device_id": target.device_id},
                rationale=f"Robot must be near {target.device_id} to actuate it.",
            ))
            plan.steps.append(PlanStep(
                kind="actuate",
                args={"device_id": target.device_id, "action": action, "kwargs": kwargs},
                rationale=f"Carry out the '{kw}' request on {target.device_id}.",
            ))

        return plan

    @staticmethod
    def _pick_target_device(skills: Skills, kind: str, msg: str):
        """Choose a device of ``kind``, preferring rooms mentioned in ``msg``."""
        room_hits = [r for r in ROOMS if r in msg or r.split("_")[0] in msg]
        for d in skills.iot.list():
            if d.kind == kind and (not room_hits or d.room in room_hits):
                return d
        for d in skills.iot.list():
            if d.kind == kind:
                return d
        return None


def _has_word(msg: str, *words: str) -> bool:
    """True if any of ``words`` appears in ``msg`` as a whole word.

    Whole-word matching prevents false hits like ``"off"`` matching inside
    ``"coffee"`` or ``"ac"`` matching inside ``"action"``.
    """
    for w in words:
        if re.search(rf"\b{re.escape(w)}\b", msg):
            return True
    return False


def action_for(kind: str, msg: str) -> tuple[str | None, dict[str, Any]]:
    """Best-effort mapping from free-text ``msg`` to a (action, kwargs) pair
    for the given device kind. Returns (None, {}) if no sensible match.
    """
    m = msg.lower()
    if kind == "curtain":
        if _has_word(m, "open"): return "open", {}
        if _has_word(m, "close", "shut"): return "close", {}
        return "toggle", {}
    if kind == "lamp":
        if _has_word(m, "dim"): return "set_brightness", {"brightness": 0.3}
        if _has_word(m, "bright", "brighten"): return "set_brightness", {"brightness": 1.0}
        if _has_word(m, "off"): return "off", {}
        return "on", {}
    if kind == "toaster":
        if _has_word(m, "stop"): return "stop", {}
        return "start", {}
    if kind == "coffee_maker":
        if _has_word(m, "stop"): return "stop", {}
        return "brew", {}
    if kind == "thermostat":
        digits = re.search(r"\b(\d{2})\b\s*(?:c|deg|degrees|°)?", m)
        if _has_word(m, "off"): return "off", {}
        if _has_word(m, "heat", "warm", "warmer"): return "set_mode", {"mode": "heat"}
        if _has_word(m, "cool", "cooler", "ac", "cold"): return "set_mode", {"mode": "cool"}
        if digits: return "set_target", {"target_c": float(digits.group(1))}
        return "set_mode", {"mode": "auto"}
    if kind == "tv":
        if _has_word(m, "off"): return "off", {}
        for ch in ("news", "movies", "music", "sports", "kids"):
            if _has_word(m, ch): return "set_channel", {"channel": ch}
        if "louder" in m or "volume up" in m: return "set_volume", {"volume": 0.7}
        if "quieter" in m or "volume down" in m: return "set_volume", {"volume": 0.2}
        return "on", {}
    if kind == "speaker":
        if _has_word(m, "stop", "pause"): return "stop", {}
        for pl in ("calm", "rain", "jazz", "pop", "focus"):
            if _has_word(m, pl): return "play", {"playlist": pl}
        return "play", {}
    if kind == "fan":
        if _has_word(m, "off"): return "off", {}
        if _has_word(m, "high", "fast"): return "set_speed", {"speed": 3}
        if _has_word(m, "low", "slow"): return "set_speed", {"speed": 1}
        return "on", {}
    if kind == "door_lock":
        if _has_word(m, "unlock") or _has_word(m, "open"): return "unlock", {}
        return "lock", {}
    return None, {}


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


@dataclass
class ExecutionResult:
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
    spoken: list[str] = field(default_factory=list)
    detected_emotion: str = "neutral"


class PlanExecutor:
    """Run a :class:`Plan` against ``skills`` via ``dispatch_tool``."""

    def __init__(self, skills: Skills,
                 empathy_lines: dict[str, str] | None = None) -> None:
        self.skills = skills
        self.empathy = empathy_lines or EMPATHY

    def execute(self, plan: Plan,
                on_step: Callable[[PlanStep, str, dict[str, Any], dict[str, Any]], None]
                | None = None) -> ExecutionResult:
        # Local import: avoids a cognition <-> planning cycle.
        from ..cognition.tools import dispatch_tool
        result = ExecutionResult()
        for step in plan.steps:
            name, inp = self._step_to_call(step, result.detected_emotion)
            out = dispatch_tool(self.skills, name, inp)
            result.tool_trace.append({"name": name, "input": inp, "output": out})
            if name == "read_emotion" and out.get("ok"):
                result.detected_emotion = out["emotion"]
            if name == "speak" and out.get("ok"):
                result.spoken.append(out["spoken"])
            if on_step is not None:
                on_step(step, name, inp, out)
        return result

    def _step_to_call(self, step: PlanStep,
                      detected_emotion: str) -> tuple[str, dict[str, Any]]:
        if step.kind == "find_owner":
            return "find_owner", {}
        if step.kind == "look_around":
            return "look_around", {}
        if step.kind == "goto_room":
            return "navigate_to_room", {"room": step.args["room"]}
        if step.kind == "goto_device":
            return "navigate_to_device", {"device_id": step.args["device_id"]}
        if step.kind == "sense_emotion":
            return "read_emotion", {}
        if step.kind == "speak":
            intent = step.args.get("intent", "empathy")
            if intent == "empathy":
                text = self.empathy.get(detected_emotion, self.empathy["neutral"])
            else:
                text = step.args.get("text") or "Done."
            return "speak", {"text": text}
        if step.kind == "actuate":
            kwargs = step.args.get("kwargs") or {}
            inp: dict[str, Any] = {
                "device_id": step.args["device_id"],
                "action": step.args["action"],
            }
            if kwargs:
                inp["kwargs"] = kwargs
            return "set_device", inp
        raise ValueError(f"unknown plan step kind: {step.kind!r}")
