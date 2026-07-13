"""Result models for STAR task-set analysis."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TaskSetTaskResult:
    """Analysis and admission result for one task in a task set."""

    task_name: str
    entry_function: str
    period_ms: int
    deadline_ms: int
    priority: int
    criticality: str
    hardware: str
    complexity_score: float
    rule_max_complexity: float
    task_load: float
    admission_status: str
    admission_reason: str
    scheduler_status: str
    scheduler_reason: str
    complexity_breakdown: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TaskSetResult:
    """Aggregated STAR task-set result."""

    task_results: list[TaskSetTaskResult]
    total_star_load: float
    system_status: str
    system_reason: str
    scheduler_status: str
    scheduler_reason: str
