"""Timeline event emitted by the scheduler simulator."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScheduleEvent:
    """One contiguous runtime interval in a simulated schedule."""

    start_us: float
    end_us: float
    task_name: str
    note: str

