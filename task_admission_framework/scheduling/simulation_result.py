"""Scheduler simulation result models."""

from __future__ import annotations

from dataclasses import dataclass, field

from task_admission_framework.scheduling.schedule_event import ScheduleEvent
from task_admission_framework.scheduling.scheduler_status import SchedulerStatus


@dataclass(slots=True)
class SchedulerTaskSimulationStats:
    """Per-task observations collected during a bounded simulation."""

    task_name: str
    releases: int = 0
    completions: int = 0
    cpu_time_us: float = 0.0
    preemptions_suffered: int = 0
    preemptions_caused: int = 0
    deadline_misses: int = 0
    max_response_time_us: float = 0.0
    max_wait_time_us: float = 0.0


@dataclass(frozen=True, slots=True)
class SchedulerSimulationResult:
    """Timeline and summary from a fixed-priority scheduler simulation."""

    events: list[ScheduleEvent]
    deadline_misses: list[str] = field(default_factory=list)
    preemptions: list[str] = field(default_factory=list)
    idle_time_us: float = 0.0
    task_stats: list[SchedulerTaskSimulationStats] = field(default_factory=list)
    interference_counts: dict[str, int] = field(default_factory=dict)
    interference_time_us: dict[str, float] = field(default_factory=dict)
    status: SchedulerStatus = SchedulerStatus.UNVERIFIED
    reason: str = ""
