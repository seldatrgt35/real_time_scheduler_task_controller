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
    hardware_adjusted_score: float
    estimated_execution_time_us: float | None
    rule_max_complexity: float
    task_load: float
    admission_status: str
    admission_reason: str
    scheduler_status: str
    scheduler_reason: str
    workload_class: str | None = None
    work_units: int | None = None
    estimated_execution_cycles: float | None = None
    execution_estimate_source: str | None = None
    safety_budget_used: float | None = None
    execution_safety_status: str = "UNVERIFIED"
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
    scheduler_timeline: list[str] = field(default_factory=list)
    scheduler_deadline_misses: list[str] = field(default_factory=list)
    scheduler_preemptions: list[str] = field(default_factory=list)
