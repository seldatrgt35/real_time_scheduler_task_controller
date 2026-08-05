"""Estimate execution cost from bounded dynamic work and workload class."""

from __future__ import annotations

from dataclasses import dataclass

from task_admission_framework.calibration.workload_cost_profile import (
    WorkloadCostProfile,
)


@dataclass(frozen=True, slots=True)
class WorkloadExecutionEstimate:
    """Explainable target-specific execution estimate."""

    workload_class: str
    work_units: int
    execution_time_us_per_work_unit: float
    nominal_execution_us: float
    admission_execution_us: float
    estimated_execution_us: float
    safety_budget_us: float
    safety_budget_used: float
    passes_safety_limit: bool
    note: str
    workload_breakdown: dict[str, int] | None = None
    time_breakdown_us: dict[str, float] | None = None


class WorkloadExecutionEstimator:
    """Apply conservative board-calibrated coefficients to bounded work."""

    def estimate(
        self,
        *,
        workload_class: str,
        work_units: int,
        period_ms: int,
        profile: WorkloadCostProfile,
    ) -> WorkloadExecutionEstimate:
        if work_units <= 0:
            raise ValueError("work_units must be greater than 0.")
        if period_ms <= 0:
            raise ValueError("period_ms must be greater than 0.")

        coefficient = profile.coefficient_for(workload_class)
        model_us = profile.intercept_us + work_units * coefficient
        admission_us = model_us * (1.0 + profile.estimate_margin_ratio)
        safety_budget = period_ms * 1000.0 * profile.safety_limit_ratio
        budget_used = admission_us / safety_budget

        validation = "validated" if profile.validated else "unvalidated"
        note = (
            f"{validation} workload estimate: {work_units} work units x "
            f"{coefficient:g} us/unit + {profile.intercept_us:g} us intercept "
            f"with {profile.estimate_margin_ratio:.0%} margin on "
            f"{profile.reference_hardware}. This is a calibrated engineering "
            "estimate, not a measured WCET."
        )
        return WorkloadExecutionEstimate(
            workload_class=workload_class.strip().lower().replace("-", "_"),
            work_units=work_units,
            execution_time_us_per_work_unit=coefficient,
            nominal_execution_us=model_us,
            admission_execution_us=admission_us,
            estimated_execution_us=model_us,
            safety_budget_us=safety_budget,
            safety_budget_used=budget_used,
            passes_safety_limit=admission_us <= safety_budget,
            note=note,
            workload_breakdown={
                workload_class.strip().lower().replace("-", "_"): work_units
            },
            time_breakdown_us={
                workload_class.strip().lower().replace("-", "_"): work_units * coefficient
            },
        )

    def estimate_breakdown(
        self,
        *,
        workload_counts: dict[str, int],
        period_ms: int,
        profile: WorkloadCostProfile,
    ) -> WorkloadExecutionEstimate:
        """Estimate a mixed task from automatically inferred bounded work."""

        if not workload_counts:
            raise ValueError("workload_counts must not be empty.")
        if period_ms <= 0:
            raise ValueError("period_ms must be greater than 0.")

        normalized: dict[str, int] = {}
        model_us = profile.intercept_us
        details: list[str] = []
        time_breakdown: dict[str, float] = {}
        for raw_class, raw_count in workload_counts.items():
            count = int(raw_count)
            if count <= 0:
                raise ValueError("All inferred workload counts must be positive.")
            workload_class = raw_class.strip().lower().replace("-", "_")
            coefficient = profile.coefficient_for(workload_class)
            normalized[workload_class] = normalized.get(workload_class, 0) + count
            subtotal = count * coefficient
            model_us += subtotal
            time_breakdown[workload_class] = (
                time_breakdown.get(workload_class, 0.0) + subtotal
            )
            details.append(f"{count} {workload_class} x {coefficient:g}")

        admission_us = model_us * (1.0 + profile.estimate_margin_ratio)
        safety_budget = period_ms * 1000.0 * profile.safety_limit_ratio
        budget_used = admission_us / safety_budget
        total_units = sum(normalized.values())
        effective_coefficient = model_us / total_units
        validation = "validated" if profile.validated else "unvalidated"
        note = (
            f"{validation} automatic workload estimate: "
            + "; ".join(details)
            + f"; {profile.intercept_us:g} us intercept; "
            + f"{profile.estimate_margin_ratio:.0%} engineering margin on "
            + f"{profile.reference_hardware}. "
            "Loop bounds and workload classes were inferred from source. "
            "This is a calibrated engineering estimate, not a measured WCET."
        )
        return WorkloadExecutionEstimate(
            workload_class="mixed" if len(normalized) > 1 else next(iter(normalized)),
            work_units=total_units,
            execution_time_us_per_work_unit=effective_coefficient,
            nominal_execution_us=model_us,
            admission_execution_us=admission_us,
            estimated_execution_us=model_us,
            safety_budget_us=safety_budget,
            safety_budget_used=budget_used,
            passes_safety_limit=admission_us <= safety_budget,
            note=note,
            workload_breakdown=normalized,
            time_breakdown_us=time_breakdown,
        )
