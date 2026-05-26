"""Runner for the evaluation suite.

Each scenario is run in a fresh world (own Apartment, own Skills, own
IoTNetwork, own MockEmotionDetector). The agent is then asked to run the
scenario's single user turn; the resulting tool trace, spoken lines, and
final world state are passed through every ``Criterion`` and the results
are collected into a ``ScenarioResult``.

Ablations:
    - ``planner=False``         : disables ReAct planning (MockLLM legacy path)
    - ``memory=False``          : runs without long-term memory
    - ``inject_emotion=False``  : skips the explicit emotion injection

The runner is offline by default (``MockLLM``). Pass ``use_llm=True`` to
exercise real Claude via ``LLMAgent`` instead — requires an API key.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from ..action.skills import Skills
from ..cognition.llm_agent import LLMAgent, MockLLM
from ..memory import MemoryStore
from ..perception.emotion import MockEmotionDetector
from ..world.apartment import Apartment
from ..world.entities import Owner, Robot, place_in_room
from ..world.iot import IoTNetwork
from .criteria import Ctx
from .scenarios import SCENARIOS, Scenario


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class CriterionResult:
    name: str
    ok: bool
    note: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScenarioResult:
    scenario_id: str
    description: str
    passed: int
    total: int
    criteria: list[CriterionResult] = field(default_factory=list)
    error: str | None = None     # set if the agent crashed mid-turn
    tool_calls: int = 0
    spoken_lines: int = 0

    @property
    def ok(self) -> bool:
        return self.error is None and self.passed == self.total

    def to_json(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "description": self.description,
            "passed": self.passed,
            "total": self.total,
            "ok": self.ok,
            "tool_calls": self.tool_calls,
            "spoken_lines": self.spoken_lines,
            "error": self.error,
            "criteria": [c.to_json() for c in self.criteria],
        }


# ---------------------------------------------------------------------------
# World builder
# ---------------------------------------------------------------------------


def _build_world(scenario: Scenario, inject_emotion: bool = True) -> Skills:
    rng = random.Random(scenario.seed)
    apt = Apartment()
    robot = Robot(0, 0)
    owner = Owner(0, 0)
    place_in_room(robot, apt, "living_room", rng)
    place_in_room(owner, apt, scenario.owner_room, rng)
    iot = IoTNetwork.default()
    emo = MockEmotionDetector()
    emo.start()
    if inject_emotion:
        emo.inject(scenario.emotion)
    return Skills(apt, robot, owner, iot, emo)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class EvalRunner:
    """Run a list of scenarios under a single configuration."""

    def __init__(self, *,
                 planner: bool = True,
                 memory: bool = True,
                 inject_emotion: bool = True,
                 use_llm: bool = False) -> None:
        self.planner = planner
        self.memory = memory
        self.inject_emotion = inject_emotion
        self.use_llm = use_llm

    def run_one(self, scenario: Scenario) -> ScenarioResult:
        skills = _build_world(scenario, inject_emotion=self.inject_emotion)
        with TemporaryDirectory() as tmp:
            mem = MemoryStore(Path(tmp)) if self.memory else None
            agent = self._build_agent(skills, mem)
            try:
                turn = agent.run_turn(scenario.message)
            except Exception as exc:   # pragma: no cover — defensive
                return ScenarioResult(
                    scenario_id=scenario.id,
                    description=scenario.description,
                    passed=0, total=len(scenario.criteria),
                    error=f"{type(exc).__name__}: {exc}",
                )
        ctx: Ctx = {
            "skills": skills,
            "trace": turn.tool_trace,
            "spoken": turn.spoken,
            "final_text": turn.final_text,
        }
        criteria_results: list[CriterionResult] = []
        for criterion in scenario.criteria:
            name, ok, note = criterion(ctx)
            criteria_results.append(CriterionResult(name=name, ok=ok, note=note))
        passed = sum(1 for c in criteria_results if c.ok)
        return ScenarioResult(
            scenario_id=scenario.id,
            description=scenario.description,
            passed=passed,
            total=len(criteria_results),
            criteria=criteria_results,
            tool_calls=len(turn.tool_trace),
            spoken_lines=len(turn.spoken),
        )

    def run_many(self, scenarios: list[Scenario]) -> list[ScenarioResult]:
        return [self.run_one(s) for s in scenarios]

    # ---- agent factory ----

    def _build_agent(self, skills: Skills, mem: MemoryStore | None):
        if self.use_llm:
            return LLMAgent.from_env(skills, memory=mem)
        return MockLLM(skills, memory=mem, use_planner=self.planner)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run_all(scenarios: list[Scenario] | None = None,
            **runner_kwargs: Any) -> list[ScenarioResult]:
    """Convenience: build a runner with the given kwargs and execute all scenarios."""
    return EvalRunner(**runner_kwargs).run_many(scenarios or SCENARIOS)


def summarize(results: list[ScenarioResult]) -> dict[str, Any]:
    total_scenarios = len(results)
    passed_scenarios = sum(1 for r in results if r.ok)
    total_criteria = sum(r.total for r in results)
    passed_criteria = sum(r.passed for r in results)
    return {
        "scenarios": {
            "passed": passed_scenarios,
            "total": total_scenarios,
            "pct": round(100.0 * passed_scenarios / max(1, total_scenarios), 1),
        },
        "criteria": {
            "passed": passed_criteria,
            "total": total_criteria,
            "pct": round(100.0 * passed_criteria / max(1, total_criteria), 1),
        },
        "avg_tool_calls": round(
            sum(r.tool_calls for r in results) / max(1, total_scenarios), 2),
    }


def format_table(results: list[ScenarioResult]) -> str:
    """Plain-text fixed-width table — copy/paste-able into the write-up."""
    rows: list[str] = []
    rows.append(f"{'id':<32} {'pass':>6} {'tools':>6}  {'status':<6}  description")
    rows.append("-" * 110)
    for r in results:
        status = "OK" if r.ok else ("ERR" if r.error else "FAIL")
        rows.append(f"{r.scenario_id:<32} {r.passed}/{r.total:<3}  "
                    f"{r.tool_calls:>5}  {status:<6}  {r.description}")
    s = summarize(results)
    rows.append("-" * 110)
    rows.append(f"  Scenarios passed: {s['scenarios']['passed']}/{s['scenarios']['total']} "
                f"({s['scenarios']['pct']}%)")
    rows.append(f"  Criteria passed:  {s['criteria']['passed']}/{s['criteria']['total']} "
                f"({s['criteria']['pct']}%)")
    rows.append(f"  Avg tool calls:   {s['avg_tool_calls']}")
    return "\n".join(rows)


def dump_jsonl(results: list[ScenarioResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r.to_json(), ensure_ascii=False) + "\n")
