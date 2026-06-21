"""Robot motion, localization, and manipulation layer.

This package holds robotics-specific logic that sits between the apartment
world model and the LLM-facing :mod:`homemate.action.skills` surface:

* **kinematics** — device dock poses and interaction-range checks
* **belief** — probabilistic owner-room belief updated by observations
* **coverage** — boustrophedon room sweep waypoints for systematic search
* **motion** — path planning metrics and cumulative odometry
* **controller** — integrates the above for Skills
"""

from __future__ import annotations

from .belief import OwnerBelief
from .controller import RobotController
from .coverage import CoveragePlanner
from .kinematics import INTERACTION_RANGE, can_interact, device_tile, nearest_dock
from .motion import MotionMetrics

__all__ = [
    "CoveragePlanner",
    "INTERACTION_RANGE",
    "MotionMetrics",
    "OwnerBelief",
    "RobotController",
    "can_interact",
    "device_tile",
    "nearest_dock",
]
