"""Result models for STAR task-set analysis."""

from __future__ import annotations

from dataclasses import dataclass, field

from task_admission_framework.scheduling.simulation_result import (
    SchedulerTaskSimulationStats,
)


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
    admission_execution_time_us: float | None
    rule_max_complexity: float
    task_load: float
    admission_status: str
    admission_reason: str
    scheduler_status: str
    scheduler_reason: str
    workload_class: str | None = None
    work_units: int | None = None
    execution_estimate_source: str | None = None
    safety_budget_used: float | None = None
    execution_safety_status: str = "UNVERIFIED"
    workload_breakdown: dict[str, int] = field(default_factory=dict)
    time_breakdown_us: dict[str, float] = field(default_factory=dict)
    contextual_integer_counts: dict[str, int] = field(default_factory=dict)
    contextual_time_breakdown_us: dict[str, float] = field(default_factory=dict)
    safety_budget_us: float | None = None
    response_time_us: float | None = None
    dynamic_bound_notes: list[str] = field(default_factory=list)
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
    simulation_window_ms: int = 0
    simulation_idle_time_us: float = 0.0
    simulation_task_stats: list[SchedulerTaskSimulationStats] = field(
        default_factory=list
    )
    simulation_interference_counts: dict[str, int] = field(default_factory=dict)
    simulation_interference_time_us: dict[str, float] = field(default_factory=dict)
