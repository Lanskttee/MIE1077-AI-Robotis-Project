"""Replay controller — step through recorded session turns in the UI."""

from __future__ import annotations

from typing import Any, Literal

from ..world.entities import Owner, Robot
from ..world.iot import IoTNetwork
from ..world_snapshot import restore_world
from .store import SessionRecord, TurnRecord

WorldPhase = Literal["before", "after"]


class ReplayController:
    """Drive world state + UI from a loaded :class:`SessionRecord`."""

    def __init__(self, session: SessionRecord, *, start_index: int = 0) -> None:
        self.session = session
        self.index = max(0, min(start_index, max(0, len(session.turns) - 1)))

    @property
    def turn_count(self) -> int:
        return len(self.session.turns)

    @property
    def current(self) -> TurnRecord | None:
        if not self.session.turns:
            return None
        return self.session.turns[self.index]

    def step(self, delta: int) -> TurnRecord | None:
        if not self.session.turns:
            return None
        self.index = max(0, min(self.index + delta, len(self.session.turns) - 1))
        return self.current

    def goto(self, index: int) -> TurnRecord | None:
        if not self.session.turns:
            return None
        self.index = max(0, min(index, len(self.session.turns) - 1))
        return self.current

    def apply_world(self, *, robot: Robot, owner: Owner, iot: IoTNetwork,
                    phase: WorldPhase = "after") -> None:
        turn = self.current
        if turn is None:
            return
        payload = turn.world_before if phase == "before" else turn.world_after
        restore_world(payload, robot=robot, owner=owner, iot=iot)

    def dialogue_upto_current(self) -> list[tuple[str, str]]:
        """Rebuild the dialogue panel up to and including the current turn."""
        lines: list[tuple[str, str]] = []
        for i, turn in enumerate(self.session.turns):
            lines.append(("you", turn.user_message))
            for line in turn.spoken:
                lines.append(("robot", line))
            if i >= self.index:
                break
        return lines

    def summary_line(self) -> str:
        if not self.session.turns:
            return f"Session {self.session.session_id}: no turns recorded"
        turn = self.current
        assert turn is not None
        return (
            f"Replay {self.index + 1}/{self.turn_count}: "
            f"{turn.user_message[:40]}{'...' if len(turn.user_message) > 40 else ''}"
        )

    def turn_meta(self) -> dict[str, Any]:
        turn = self.current
        if turn is None:
            return {}
        n_ok = sum(1 for s in turn.tool_trace if (s.get("output") or {}).get("ok"))
        return {
            "index": self.index,
            "total": self.turn_count,
            "user_message": turn.user_message,
            "tool_calls": len(turn.tool_trace),
            "tools_ok": n_ok,
            "spoken_lines": len(turn.spoken),
            "emotion": turn.emotion_label,
            "final_text": turn.final_text,
        }
