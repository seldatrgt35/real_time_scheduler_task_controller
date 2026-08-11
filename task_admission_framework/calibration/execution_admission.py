"""Measurement-calibrated execution admission for one analyzed task."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

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
    estimated_execution_us: float | None
    admission_execution_us: float | None
    safety_budget_us: float
    safety_budget_used: float | None
    workload_counts: dict[str, int] = field(default_factory=dict)
    time_breakdown_us: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def evaluate_execution_admission(
    task_profile,
    period_ms: int,
    profile: WorkloadCostProfile,
) -> ExecutionAdmissionResult:
    """Evaluate a mixed task against its measured S32K148 period budget."""

    budget_us = period_ms * 1000.0 * profile.safety_limit_ratio
    supported_costs = profile.execution_time_us_per_work_unit
    counts = {
        workload.strip().lower().replace("-", "_"): count
        for workload, count in task_profile.inferred_workload_counts.items()
        if workload.strip().lower().replace("-", "_") in supported_costs
    }
    for operation, count in getattr(
        task_profile, "inferred_operation_counts", {}
    ).items():
        normalized = operation.strip().lower().replace("-", "_")
        if normalized in supported_costs:
            counts[normalized] = max(counts.get(normalized, 0), count)
    can_send_count = getattr(task_profile, "api_usage", {}).get("CAN_Send", 0)
    if can_send_count > 0 and "can_send_driver" in supported_costs:
        counts["can_send_driver"] = can_send_count

    if not task_profile.dynamic_bound_verified:
        return ExecutionAdmissionResult(
            status="UNVERIFIED",
            estimated_execution_us=None,
            admission_execution_us=None,
            safety_budget_us=budget_us,
            safety_budget_used=None,
            workload_counts=counts,
            notes=list(task_profile.dynamic_bound_notes),
        )
    if not counts:
        return ExecutionAdmissionResult(
            status="UNVERIFIED",
            estimated_execution_us=None,
            admission_execution_us=None,
            safety_budget_us=budget_us,
            safety_budget_used=None,
            notes=["No bounded dynamic workload could be inferred from the source."],
        )

    effective_profile = (
        replace(profile, estimate_margin_ratio=0.15)
        if can_send_count > 0
        else profile
    )
    estimate = WorkloadExecutionEstimator().estimate_breakdown(
        workload_counts=counts,
        period_ms=period_ms,
        profile=effective_profile,
    )
    status = (
        ("PASS" if estimate.passes_safety_limit else "FAIL")
        if estimate.model_validated
        else "UNVERIFIED"
    )
    return ExecutionAdmissionResult(
        status=status,
        estimated_execution_us=estimate.estimated_execution_us,
        admission_execution_us=estimate.admission_execution_us,
        safety_budget_us=budget_us,
        safety_budget_used=estimate.safety_budget_used,
        workload_counts=counts,
        time_breakdown_us=dict(estimate.time_breakdown_us or {}),
        notes=[estimate.note],
    )
