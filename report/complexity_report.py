"""Explainable software complexity report model."""

from __future__ import annotations

from dataclasses import dataclass, field

from task_admission_framework.complexity.cost_breakdown import CostBreakdown


@dataclass(frozen=True, slots=True)
class ComplexityReport:
    """Human-readable summary of structural software complexity."""

    task_name: str
    total_score: int
    total_features: int
    api_cost: int
    control_flow_cost: int
    memory_cost: int
    rtos_cost: int
    peripheral_cost: int
    floating_point_cost: int
    computation_cost: int = 0
    other_cost: int = 0
    breakdown: list[CostBreakdown] = field(default_factory=list)
