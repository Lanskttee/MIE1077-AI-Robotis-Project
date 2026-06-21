"""Dynamic path tracking and replanning for a moving owner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ..planning.navigator import Coord

GoalKind = Literal["tile", "device", "owner", "room"]


@dataclass
class ActiveGoal:
    goal: Coord
    kind: GoalKind = "tile"
    label: str = ""


@dataclass
class PathTracker:
    """Tracks the robot's active navigation goal for mid-flight replanning."""

    active: ActiveGoal | None = None
    follow_owner: bool = False
    replan_count: int = 0
    last_owner_pos: Coord | None = None
    last_plan_turns: int = 0
    last_plan_cost: int = 0
    planner_used: str = "costmap_astar"
    history: list[dict[str, str | int]] = field(default_factory=list)

    def register(self, goal: Coord, *, kind: GoalKind = "tile", label: str = "") -> None:
        self.active = ActiveGoal(goal=goal, kind=kind, label=label)

    def clear(self) -> None:
        self.active = None
        self.follow_owner = False

    def enable_owner_tracking(self) -> None:
        self.follow_owner = True
        if self.last_owner_pos is not None:
            self.register(self.last_owner_pos, kind="owner", label="follow_owner")

    def observe_owner(self, owner_pos: Coord) -> str | None:
        """Return replan reason if owner moved while tracking."""
        if not self.follow_owner:
            self.last_owner_pos = owner_pos
            return None
        if self.last_owner_pos is None:
            self.last_owner_pos = owner_pos
            self.register(owner_pos, kind="owner", label="follow_owner")
            return None
        if owner_pos != self.last_owner_pos:
            self.last_owner_pos = owner_pos
            self.register(owner_pos, kind="owner", label="follow_owner")
            return "owner_moved"
        return None

    def check_path_blocked(self, owner_pos: Coord, pending: list[Coord]) -> str | None:
        """Detect imminent collision with the owner on the remaining path."""
        if not pending:
            return None
        if owner_pos == pending[0]:
            return "owner_on_next_tile"
        if owner_pos in pending[:3]:
            return "owner_in_path"
        return None

    def record_replan(self, reason: str, *, new_cost: int, turns: int,
                      planner: str) -> None:
        self.replan_count += 1
        self.last_plan_cost = new_cost
        self.last_plan_turns = turns
        self.planner_used = planner
        self.history.append({
            "reason": reason,
            "replan_index": self.replan_count,
            "new_cost": new_cost,
            "turns": turns,
            "planner": planner,
        })

    def snapshot(self) -> dict[str, object]:
        active = None
        if self.active is not None:
            active = {
                "goal": list(self.active.goal),
                "kind": self.active.kind,
                "label": self.active.label,
            }
        return {
            "active_goal": active,
            "follow_owner": self.follow_owner,
            "replan_count": self.replan_count,
            "last_plan_cost": self.last_plan_cost,
            "last_plan_turns": self.last_plan_turns,
            "planner_used": self.planner_used,
            "recent_replans": self.history[-5:],
        }
