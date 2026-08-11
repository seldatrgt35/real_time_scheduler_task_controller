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
    model_validated: bool = False


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

        return self.estimate_breakdown(
            workload_counts={workload_class: work_units},
            period_ms=period_ms,
            profile=profile,
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
        raw_model_us = profile.intercept_us
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
            raw_model_us += subtotal
            time_breakdown[workload_class] = (
                time_breakdown.get(workload_class, 0.0) + subtotal
            )
            details.append(f"{count} {workload_class} x {coefficient:g}")

        model_us = raw_model_us
        covered: set[str] = set()
        correction_notes: list[str] = []
        for correction in profile.group_corrections:
            present = correction.workload_classes.intersection(normalized)
            if not present:
                continue
            if correction.require_all_classes and present != correction.workload_classes:
                continue
            if not correction.required_workload_classes.issubset(present):
                continue
            raw_group_us = sum(time_breakdown[name] for name in present)
            corrected_group_us = (
                correction.intercept_us + correction.scale * raw_group_us
            )
            model_us += corrected_group_us - raw_group_us
            time_breakdown[f"{correction.name}_group_correction"] = (
                corrected_group_us - raw_group_us
            )
            if correction.validated:
                covered.update(present)
            correction_notes.append(
                f"{correction.name}: {raw_group_us:.3f} us -> "
                f"{corrected_group_us:.3f} us"
            )

        model_validated = profile.validated or set(normalized).issubset(covered)
        admission_us = model_us * (1.0 + profile.estimate_margin_ratio)
        safety_budget = period_ms * 1000.0 * profile.safety_limit_ratio
        budget_used = admission_us / safety_budget
        total_units = sum(normalized.values())
        effective_coefficient = model_us / total_units
        validation = "validated" if model_validated else "unvalidated"
        note = (
            f"{validation} automatic workload estimate: "
            + "; ".join(details)
            + f"; {profile.intercept_us:g} us intercept; "
            + ("; ".join(correction_notes) + "; " if correction_notes else "")
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
            model_validated=model_validated,
        )
