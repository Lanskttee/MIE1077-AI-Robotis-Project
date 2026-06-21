"""Batch runner for built-in demo scripts (offline, no Pygame).

Runs every entry in :mod:`homemate.demo_scripts` through MockLLM in a fresh
world and checks a minimal success contract (find_owner, read_emotion, speak).
Outputs a table suitable for the course report.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..action.skills import Skills
from ..cognition.llm_agent import MockLLM
from ..demo_scripts import DEMO_SCRIPTS, DemoScript, script_ids
from ..memory import MemoryStore
from ..perception.emotion import MockEmotionDetector
from ..world.apartment import Apartment
from ..world.entities import Owner, Robot, place_in_room
from ..world.iot import IoTNetwork

# Every demo script must exercise the empathy pipeline at minimum.
REQUIRED_TOOLS = ("find_owner", "read_emotion", "speak")


@dataclass
class ScriptCheck:
    name: str
    ok: bool
    note: str = ""


@dataclass
class ScriptRunResult:
    script_id: str
    title: str
    ok: bool
    tool_calls: int = 0
    spoken_lines: int = 0
    tools_used: list[str] = field(default_factory=list)
    checks: list[ScriptCheck] = field(default_factory=list)
    error: str | None = None
    final_text: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "script_id": self.script_id,
            "title": self.title,
            "ok": self.ok,
            "tool_calls": self.tool_calls,
            "spoken_lines": self.spoken_lines,
            "tools_used": self.tools_used,
            "checks": [asdict(c) for c in self.checks],
            "error": self.error,
            "final_text": self.final_text,
        }


def _build_world(script: DemoScript) -> Skills:
    rng = random.Random(script.seed)
    apt = Apartment()
    robot = Robot(0, 0)
    owner = Owner(0, 0)
    place_in_room(robot, apt, "living_room", rng)
    place_in_room(owner, apt, script.owner_room, rng)
    iot = IoTNetwork.default()
    emo = MockEmotionDetector()
    emo.start()
    emo.inject(script.emotion)
    return Skills(apt, robot, owner, iot, emo)


def _tools_used(trace: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for step in trace:
        name = step.get("name", "")
        if name and name not in seen:
            seen.append(name)
    return seen


def run_script(script: DemoScript, *, use_memory: bool = False) -> ScriptRunResult:
    checks: list[ScriptCheck] = []
    try:
        skills = _build_world(script)
        mem = MemoryStore() if use_memory else None
        agent = MockLLM(skills, memory=mem, use_planner=True)
        result = agent.run_turn(script.message)
        used = _tools_used(result.tool_trace)
        for req in REQUIRED_TOOLS:
            checks.append(ScriptCheck(
                name=f"tool:{req}",
                ok=req in used,
                note="" if req in used else "missing from tool trace",
            ))
        iot_calls = [s for s in result.tool_trace if s.get("name") == "set_device"]
        if any(kw in script.message.lower() for kw in ("coffee", "lamp", "curtain", "thermostat", "toast")):
            checks.append(ScriptCheck(
                name="iot_actuation",
                ok=len(iot_calls) > 0,
                note=f"{len(iot_calls)} set_device call(s)",
            ))
        ok = all(c.ok for c in checks) and not any(
            not (s.get("output") or {}).get("ok") for s in result.tool_trace
        )
        return ScriptRunResult(
            script_id=script.id,
            title=script.title,
            ok=ok,
            tool_calls=len(result.tool_trace),
            spoken_lines=len(result.spoken),
            tools_used=used,
            checks=checks,
            final_text=result.final_text,
        )
    except Exception as e:
        checks.append(ScriptCheck(name="run", ok=False, note=str(e)))
        return ScriptRunResult(
            script_id=script.id,
            title=script.title,
            ok=False,
            checks=checks,
            error=f"{type(e).__name__}: {e}",
        )


class DemoBatchRunner:
    """Run some or all demo scripts and collect results."""

    def __init__(self, *, use_memory: bool = False) -> None:
        self.use_memory = use_memory

    def run_many(self, ids: list[str] | None = None) -> list[ScriptRunResult]:
        wanted = ids or script_ids()
        results: list[ScriptRunResult] = []
        for sid in wanted:
            script = DEMO_SCRIPTS[sid]
            results.append(run_script(script, use_memory=self.use_memory))
        return results


def summarize(results: list[ScriptRunResult]) -> dict[str, Any]:
    passed = sum(1 for r in results if r.ok)
    return {
        "scripts": {"passed": passed, "total": len(results)},
        "tool_calls": sum(r.tool_calls for r in results),
    }


def format_table(results: list[ScriptRunResult]) -> str:
    lines = [
        f"{'Script':<22} {'Pass':>4}  {'Tools':>5}  {'Spoken':>6}  Title",
        "-" * 72,
    ]
    for r in results:
        mark = "OK" if r.ok else "FAIL"
        lines.append(
            f"{r.script_id:<22} {mark:>4}  {r.tool_calls:>5}  {r.spoken_lines:>6}  {r.title}"
        )
    s = summarize(results)
    lines.append("-" * 72)
    lines.append(
        f"  Scripts passed: {s['scripts']['passed']}/{s['scripts']['total']}  "
        f"Total tool calls: {s['tool_calls']}"
    )
    return "\n".join(lines)


def dump_jsonl(results: list[ScriptRunResult], path: Path | str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r.to_json(), ensure_ascii=False) + "\n")
