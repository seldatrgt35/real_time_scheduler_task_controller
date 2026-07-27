"""Measurement-calibrated execution admission for one analyzed task."""

from __future__ import annotations

from dataclasses import dataclass, field

from task_admission_framework.calibration.workload_cost_profile import (
    WorkloadCostProfile,
)
from task_admission_framework.calibration.workload_execution_estimator import (
    WorkloadExecutionEstimator,
)


@dataclass(frozen=True, slots=True)
class ExecutionAdmissionResult:
    """Explainable PASS/FAIL/UNVERIFIED result derived from board measurements."""

    status: str
    estimated_cycles: float | None
    estimated_execution_us: float | None
    safety_budget_cycles: float
    safety_budget_us: float
    safety_budget_used: float | None
    workload_counts: dict[str, int] = field(default_factory=dict)
    cycle_breakdown: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def evaluate_execution_admission(
    task_profile,
    period_ms: int,
    profile: WorkloadCostProfile,
) -> ExecutionAdmissionResult:
    """Evaluate a mixed task against its measured S32K148 period budget."""

    budget_cycles = (
        period_ms
        * 1000.0
        * profile.clock_frequency_mhz
        * profile.safety_limit_ratio
    )
    budget_us = period_ms * 1000.0 * profile.safety_limit_ratio
    counts = dict(task_profile.inferred_workload_counts)

    if not task_profile.dynamic_bound_verified:
        return ExecutionAdmissionResult(
            status="UNVERIFIED",
            estimated_cycles=None,
            estimated_execution_us=None,
            safety_budget_cycles=budget_cycles,
            safety_budget_us=budget_us,
            safety_budget_used=None,
            workload_counts=counts,
            notes=list(task_profile.dynamic_bound_notes),
        )
    if not counts:
        return ExecutionAdmissionResult(
            status="UNVERIFIED",
            estimated_cycles=None,
            estimated_execution_us=None,
            safety_budget_cycles=budget_cycles,
            safety_budget_us=budget_us,
            safety_budget_used=None,
            notes=["No bounded dynamic workload could be inferred from the source."],
        )

    estimate = WorkloadExecutionEstimator().estimate_breakdown(
        workload_counts=counts,
        period_ms=period_ms,
        profile=profile,
    )
    return ExecutionAdmissionResult(
        status="PASS" if estimate.passes_safety_limit else "FAIL",
        estimated_cycles=estimate.estimated_cycles,
        estimated_execution_us=estimate.estimated_execution_us,
        safety_budget_cycles=estimate.safety_budget_cycles,
        safety_budget_us=budget_us,
        safety_budget_used=estimate.safety_budget_used,
        workload_counts=counts,
        cycle_breakdown=dict(estimate.cycle_breakdown or {}),
        notes=[estimate.note],
    )
