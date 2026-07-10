"""Structural complexity calculation result."""

from __future__ import annotations

from dataclasses import dataclass, field

from task_admission_framework.complexity.cost_breakdown import CostBreakdown


@dataclass(frozen=True, slots=True)
class ComplexityResult:
    """Final structural score and its explainable breakdown."""

    total_score: int
    breakdown: list[CostBreakdown] = field(default_factory=list)
