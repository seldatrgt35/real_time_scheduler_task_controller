"""Scheduler simulation result models."""

from __future__ import annotations

from dataclasses import dataclass, field

from task_admission_framework.scheduling.schedule_event import ScheduleEvent
from task_admission_framework.scheduling.scheduler_status import SchedulerStatus


@dataclass(frozen=True, slots=True)
class SchedulerSimulationResult:
    """Timeline and summary from a fixed-priority scheduler simulation."""

    events: list[ScheduleEvent]
    deadline_misses: list[str] = field(default_factory=list)
    preemptions: list[str] = field(default_factory=list)
    idle_time_us: float = 0.0
    status: SchedulerStatus = SchedulerStatus.UNVERIFIED
    reason: str = ""

