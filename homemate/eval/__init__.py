"""Evaluation suite for HomeMate.

A scripted, scenario-driven benchmark. Each scenario sets up a deterministic
world (apartment, owner room, injected emotion, prior memory) and asks the
agent to act on one free-text request. A list of ``Criterion`` callables is
then evaluated against the resulting world state, tool trace, and dialogue.

The default runner is offline (MockLLM, no API key); pass ``--use-llm`` on
the CLI to exercise real Claude instead. Three ablation flags
(``--no-planner``, ``--no-memory``, ``--no-emotion``) reproduce the
deliverable ablation tables for the final report.
"""

from __future__ import annotations

from .criteria import (
    Criterion,
    Ctx,
    device_state_eq,
    emotion_detected,
    robot_in_room,
    spoken_contains,
    tool_was_called,
)
from .runner import EvalRunner, ScenarioResult, run_all
from .scenarios import SCENARIOS, Scenario

__all__ = [
    "Criterion",
    "Ctx",
    "device_state_eq",
    "emotion_detected",
    "robot_in_room",
    "spoken_contains",
    "tool_was_called",
    "EvalRunner",
    "ScenarioResult",
    "run_all",
    "SCENARIOS",
    "Scenario",
]
