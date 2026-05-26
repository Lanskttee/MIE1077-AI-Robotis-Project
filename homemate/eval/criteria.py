"""Success-criteria builders for the evaluation suite.

A ``Criterion`` is a callable that inspects the post-turn world (skills,
tool trace, dialogue) and returns ``(name, ok, note)``. Scenarios are
declared as a flat list of criteria; the runner evaluates each and reports
a per-criterion pass/fail breakdown plus the scenario-level aggregate.
"""

from __future__ import annotations

from typing import Any, Callable, TypedDict


class Ctx(TypedDict, total=False):
    """Evaluation context handed to each criterion."""
    skills: Any            # homemate.action.skills.Skills
    trace: list[dict[str, Any]]
    spoken: list[str]
    final_text: str


# A criterion: ctx -> (criterion_name, ok, note)
Criterion = Callable[[Ctx], tuple[str, bool, str]]


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def tool_was_called(name: str) -> Criterion:
    """The agent called the named tool at least once."""
    def _check(ctx: Ctx) -> tuple[str, bool, str]:
        ok = any(t.get("name") == name for t in ctx.get("trace", []))
        return (f"tool_called:{name}", ok,
                "" if ok else f"missing {name!r} in trace")
    return _check


def tool_called_with(name: str, **input_fields: Any) -> Criterion:
    """The agent called ``name`` with at least the given input fields."""
    def _check(ctx: Ctx) -> tuple[str, bool, str]:
        for t in ctx.get("trace", []):
            if t.get("name") != name:
                continue
            inp = t.get("input", {}) or {}
            if all(inp.get(k) == v for k, v in input_fields.items()):
                return (f"tool_called:{name}({input_fields})", True, "")
        return (f"tool_called:{name}({input_fields})", False,
                f"no matching {name} call")
    return _check


def device_state_eq(device_id: str, key: str, value: Any) -> Criterion:
    """After the turn, ``device.state[key] == value``."""
    def _check(ctx: Ctx) -> tuple[str, bool, str]:
        skills = ctx["skills"]
        dev = skills.iot.get(device_id)
        if dev is None:
            return (f"state:{device_id}.{key}={value!r}", False,
                    f"no device {device_id!r}")
        actual = dev.state.get(key)
        ok = actual == value
        return (f"state:{device_id}.{key}={value!r}", ok,
                "" if ok else f"got {actual!r}")
    return _check


def device_state_close(device_id: str, key: str,
                       value: float, tol: float = 0.01) -> Criterion:
    """Numeric comparison with absolute tolerance."""
    def _check(ctx: Ctx) -> tuple[str, bool, str]:
        skills = ctx["skills"]
        dev = skills.iot.get(device_id)
        if dev is None:
            return (f"state:{device_id}.{key}~={value}", False,
                    f"no device {device_id!r}")
        actual = dev.state.get(key)
        try:
            ok = abs(float(actual) - float(value)) <= tol
        except (TypeError, ValueError):
            ok = False
        return (f"state:{device_id}.{key}~={value}", ok,
                "" if ok else f"got {actual!r}")
    return _check


def robot_in_room(room: str) -> Criterion:
    def _check(ctx: Ctx) -> tuple[str, bool, str]:
        actual = ctx["skills"].robot_room()
        ok = actual == room
        return (f"robot_in:{room}", ok,
                "" if ok else f"in {actual!r}")
    return _check


def spoken_contains(needle: str) -> Criterion:
    """At least one ``speak`` line contains ``needle`` (case-insensitive)."""
    def _check(ctx: Ctx) -> tuple[str, bool, str]:
        joined = " ".join(ctx.get("spoken", [])).lower()
        ok = needle.lower() in joined
        return (f"spoken_has:{needle!r}", ok,
                "" if ok else "phrase never spoken")
    return _check


def emotion_detected(emotion: str) -> Criterion:
    """The agent successfully called ``read_emotion`` and got the expected label."""
    def _check(ctx: Ctx) -> tuple[str, bool, str]:
        for t in ctx.get("trace", []):
            if t.get("name") != "read_emotion":
                continue
            out = t.get("output", {}) or {}
            if not out.get("ok"):
                continue
            got = out.get("emotion")
            ok = got == emotion
            return (f"emotion={emotion}", ok,
                    "" if ok else f"got {got!r}")
        return (f"emotion={emotion}", False, "no successful read_emotion")
    return _check


def empathy_tone(emotion: str) -> Criterion:
    """Spoken output matches the empathy-line vocabulary for ``emotion``.

    A loose check: at least one of a handful of tone-indicative words for
    that emotion appears in the dialogue. Lets us catch tone mismatch
    (e.g., speaking a 'happy' line at a sad owner) without coupling the test
    to the exact phrasing.
    """
    keywords = {
        "happy":     ("smile", "great", "energy"),
        "sad":       ("here with you", "dim", "calm"),
        "angry":     ("breath", "listening", "what happened"),
        "surprised": ("exciting", "wow", "whoa"),
        "neutral":   ("checking in", "anything"),
        "tired":     ("tired", "coffee", "rest"),
    }[emotion]
    def _check(ctx: Ctx) -> tuple[str, bool, str]:
        joined = " ".join(ctx.get("spoken", [])).lower()
        hit = next((k for k in keywords if k in joined), None)
        return (f"empathy_tone:{emotion}", hit is not None,
                "" if hit else f"no {emotion}-toned word in dialogue")
    return _check
