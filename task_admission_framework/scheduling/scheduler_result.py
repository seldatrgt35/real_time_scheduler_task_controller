"""Result models for fixed-priority scheduler analysis."""

from __future__ import annotations

from dataclasses import dataclass

from task_admission_framework.scheduling.scheduler_status import SchedulerStatus


@dataclass(frozen=True, slots=True)
class SchedulerTaskInput:
    """Validated timing input for one task."""

    task_name: str
    period_ms: int
    deadline_ms: int
    priority: int
    execution_budget_us: float | None
    blocking_budget_us: float = 0.0


@dataclass(frozen=True, slots=True)
class SchedulerTaskResult:
    """Response-time result for one task."""

    task_name: str
    priority: int
    response_time_us: float | None
    deadline_us: float
    status: SchedulerStatus
    reason: str


@dataclass(frozen=True, slots=True)
class SchedulerSetResult:
    """Aggregate scheduler feasibility result."""

    task_results: list[SchedulerTaskResult]
    overall_status: SchedulerStatus
    reason: str

