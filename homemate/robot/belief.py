"""Probabilistic belief over which room the owner occupies.

The robot never reads the owner's coordinates directly except through
room-local observations (same-room visibility). Belief is updated with a
simple Bayesian-style filter and fused with the time-of-day search prior.
"""

from __future__ import annotations

from typing import Any

from ..planning.search import OwnerSearchPolicy


class OwnerBelief:
    """Maintains a discrete distribution over room names."""

    def __init__(self, rooms: list[str]) -> None:
        self.rooms = list(rooms)
        n = len(self.rooms) or 1
        self.probs: dict[str, float] = {r: 1.0 / n for r in self.rooms}
        self.last_seen_room: str | None = None
        self.observation_count = 0

    def observe(self, room: str, owner_visible: bool) -> None:
        """Update belief after checking ``room``."""
        if room not in self.probs:
            return
        self.observation_count += 1
        if owner_visible:
            self.last_seen_room = room
            for r in self.rooms:
                self.probs[r] = 0.92 if r == room else 0.08 / max(1, len(self.rooms) - 1)
        else:
            # Owner not seen: down-weight this room, redistribute mass.
            absent_weight = 0.15
            present_weight = 0.85 / max(1, len(self.rooms) - 1)
            for r in self.rooms:
                self.probs[r] = absent_weight if r == room else present_weight
        self._normalize()

    def rank_rooms(self) -> list[str]:
        return sorted(self.rooms, key=lambda r: -self.probs[r])

    def merge_search_order(self, policy: OwnerSearchPolicy,
                           current_room: str | None) -> list[str]:
        """Fuse belief ranking with time-of-day prior (belief-first)."""
        prior = policy.ordering(current_room=current_room)
        belief = self.rank_rooms()
        merged: list[str] = []
        for r in belief + prior:
            if r not in merged and r != current_room:
                merged.append(r)
        return merged

    def snapshot(self) -> dict[str, Any]:
        ranked = self.rank_rooms()[:3]
        return {
            "room_probabilities": {r: round(self.probs[r], 3) for r in self.rooms},
            "most_likely_room": ranked[0] if ranked else None,
            "last_seen_room": self.last_seen_room,
            "observations": self.observation_count,
        }

    def _normalize(self) -> None:
        total = sum(self.probs.values()) or 1.0
        self.probs = {r: v / total for r, v in self.probs.items()}
