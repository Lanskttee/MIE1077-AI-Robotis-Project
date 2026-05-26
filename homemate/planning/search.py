"""Room-by-room owner search policy.

The robot does not know the owner's position. The policy returns an ordered
list of rooms to check. The LLM (or a fallback heuristic) may reorder this
based on time-of-day priors.
"""

from __future__ import annotations

from datetime import datetime


# Time-of-day prior: which rooms the owner is most likely in, in order.
TIME_PRIORS: dict[str, list[str]] = {
    "morning":   ["kitchen", "bedroom", "bathroom", "living_room"],
    "afternoon": ["living_room", "kitchen", "bedroom", "bathroom"],
    "evening":   ["living_room", "kitchen", "bedroom", "bathroom"],
    "night":     ["bedroom", "bathroom", "living_room", "kitchen"],
}


def time_of_day(now: datetime | None = None) -> str:
    h = (now or datetime.now()).hour
    if 5 <= h < 11:
        return "morning"
    if 11 <= h < 17:
        return "afternoon"
    if 17 <= h < 22:
        return "evening"
    return "night"


class OwnerSearchPolicy:
    """Yields rooms in order of likely-owner-presence, skipping the current room."""

    def __init__(self, room_names: list[str]) -> None:
        self.all_rooms = list(room_names)

    def ordering(self, current_room: str | None = None,
                 now: datetime | None = None) -> list[str]:
        prior = TIME_PRIORS[time_of_day(now)]
        ordered = [r for r in prior if r in self.all_rooms]
        # append any rooms missing from the prior, in case the apartment changes
        for r in self.all_rooms:
            if r not in ordered:
                ordered.append(r)
        if current_room is not None:
            ordered = [r for r in ordered if r != current_room]
        return ordered
