"""Scheduler feasibility status values."""

from __future__ import annotations

from enum import Enum, auto


class SchedulerStatus(Enum):
    """Outcome of scheduler feasibility analysis."""

    UNVERIFIED = auto()
    FEASIBLE = auto()
    NOT_FEASIBLE = auto()

