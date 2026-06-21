"""Session recording and replay for the Pygame demo.

Each user turn is persisted as a :class:`TurnRecord` with world snapshots
(before/after), tool trace, and spoken lines. Sessions can be replayed in the
UI or exported for the course report.
"""

from __future__ import annotations

from .replay import ReplayController
from .store import SessionRecord, SessionStore, TurnRecord

__all__ = [
    "ReplayController",
    "SessionRecord",
    "SessionStore",
    "TurnRecord",
]
