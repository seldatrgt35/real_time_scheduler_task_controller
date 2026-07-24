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
    cycles_per_work_unit: float
    estimated_cycles: float
    estimated_execution_us: float
    safety_budget_cycles: float
    safety_budget_used: float
    passes_safety_limit: bool
    note: str


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
        estimated_cycles = work_units * coefficient
        cycles_per_us = profile.clock_frequency_mhz
        estimated_us = estimated_cycles / cycles_per_us
        period_cycles = period_ms * 1000.0 * cycles_per_us
        safety_budget = period_cycles * profile.safety_limit_ratio
        budget_used = estimated_cycles / safety_budget

        validation = "validated" if profile.validated else "unvalidated"
        note = (
            f"{validation} workload estimate: {work_units} work units x "
            f"{coefficient:g} cycles/unit on {profile.reference_hardware}. "
            "This is a calibrated engineering estimate, not a measured WCET."
        )
        return WorkloadExecutionEstimate(
            workload_class=workload_class.strip().lower().replace("-", "_"),
            work_units=work_units,
            cycles_per_work_unit=coefficient,
            estimated_cycles=estimated_cycles,
            estimated_execution_us=estimated_us,
            safety_budget_cycles=safety_budget,
            safety_budget_used=budget_used,
            passes_safety_limit=estimated_cycles <= safety_budget,
            note=note,
        )
