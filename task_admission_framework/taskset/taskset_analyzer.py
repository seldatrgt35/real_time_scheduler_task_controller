"""Task-set analyzer built on existing STAR single-task components."""

from __future__ import annotations

import tempfile
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from task_admission_framework.admission.admission_controller import AdmissionController
from task_admission_framework.calibration.complexity_time_profile import (
    ComplexityTimeProfile,
)
from task_admission_framework.calibration.execution_time_estimator import (
    ExecutionTimeEstimator,
)
from task_admission_framework.calibration.workload_cost_profile import (
    WorkloadCostProfile,
)
from task_admission_framework.calibration.workload_cost_loader import (
    WorkloadCostLoader,
)
from task_admission_framework.calibration.workload_execution_estimator import (
    WorkloadExecutionEstimator,
)
from task_admission_framework.rules.rule_database import RuleDatabase
from task_admission_framework.rules.rule_loader import RuleLoader
from task_admission_framework.scheduling.fixed_priority_analyzer import (
    FixedPriorityAnalyzer,
)
from task_admission_framework.scheduling.scheduler_result import SchedulerTaskInput
from task_admission_framework.scheduling.scheduler_simulator import SchedulerSimulator
from task_admission_framework.taskset.exceptions import TaskSetError
from task_admission_framework.taskset.taskset_entry import TaskSetEntry
from task_admission_framework.taskset.taskset_result import (
    TaskSetResult,
    TaskSetTaskResult,
)

if TYPE_CHECKING:
    from task_admission_framework.pipeline.analysis_pipeline import AnalysisPipeline


class TaskSetAnalyzer:
    """Computes static complexity-based task-set feasibility indicators."""

    def __init__(
        self,
        pipeline: "AnalysisPipeline | None" = None,
        admission_controller: AdmissionController | None = None,
        calibration_profile: ComplexityTimeProfile | None = None,
        workload_cost_profile: WorkloadCostProfile | None = None,
        simulation_window_ms: int = 200,
    ) -> None:
        if pipeline is None:
            from task_admission_framework.pipeline.analysis_pipeline import (
                AnalysisPipeline,
            )

            pipeline = AnalysisPipeline()

        self._pipeline = pipeline
        self._admission_controller = admission_controller or AdmissionController()
        self._calibration_profile = calibration_profile
        self._execution_time_estimator = ExecutionTimeEstimator()
        self._workload_cost_profile = (
            workload_cost_profile
            if workload_cost_profile is not None
            else (
                None
                if calibration_profile is not None
                else self._load_default_workload_profile()
            )
        )
        self._workload_execution_estimator = WorkloadExecutionEstimator()
        self._simulation_window_ms = simulation_window_ms

    @staticmethod
    def _load_default_workload_profile() -> WorkloadCostProfile:
        profile_path = (
            Path(__file__).parents[1]
            / "calibration"
            / "profiles"
            / "S32K148_workload_costs.json"
        )
        return WorkloadCostLoader().load(profile_path)

    def analyze(self, entries: list[TaskSetEntry]) -> TaskSetResult:
        if not entries:
            raise TaskSetError("Task set must contain at least one task.")
        task_names = [entry.name for entry in entries]
        if len(task_names) != len(set(task_names)):
            raise TaskSetError(
                "Task instance names must be unique. Use separate names such as "
                "VehicleHealth, VehicleHealth#2, and VehicleHealth#3."
            )

        task_results: list[TaskSetTaskResult] = []

        with tempfile.TemporaryDirectory(prefix="star_taskset_") as temp_dir:
            descriptor_dir = Path(temp_dir)
            for index, entry in enumerate(entries):
                descriptor_file = self._write_descriptor(descriptor_dir, index, entry)
                session = self._pipeline.analyze(
                    source_file=entry.source_file,
                    descriptor_file=descriptor_file,
                    hardware_profile_file=entry.hardware_profile_file,
                )
                rules = RuleLoader().load(entry.rules_file)
                rule_database = RuleDatabase(rules)
                decision = self._admission_controller.evaluate(session, rule_database)
                task_load = decision.star_load_indicator
                (
                    estimated_execution_time_us,
                    safety_budget_used,
                    execution_safety_status,
                    estimate_source,
                    estimate_note,
                ) = self._estimate_execution_time(
                    session.task_profile,
                    entry.period_ms,
                    decision.hardware_adjusted_score,
                )
                task_results.append(
                    TaskSetTaskResult(
                        task_name=entry.name,
                        entry_function=entry.entry_function,
                        period_ms=entry.period_ms,
                        deadline_ms=entry.deadline_ms,
                        priority=entry.priority,
                        criticality=entry.criticality,
                        hardware=decision.hardware,
                        complexity_score=decision.complexity_score,
                        hardware_adjusted_score=decision.hardware_adjusted_score,
                        estimated_execution_time_us=estimated_execution_time_us,
                        rule_max_complexity=decision.hardware_adjusted_max_complexity,
                        task_load=task_load,
                        admission_status=decision.status.name,
                        admission_reason=self._append_estimate_note(
                            decision.reason,
                            estimate_note,
                        ),
                        scheduler_status=decision.scheduler_status,
                        scheduler_reason=decision.scheduler_reason,
                        workload_class=(
                            next(iter(session.task_profile.inferred_workload_counts))
                            if len(session.task_profile.inferred_workload_counts) == 1
                            else (
                                "mixed"
                                if session.task_profile.inferred_workload_counts
                                else None
                            )
                        ),
                        work_units=sum(
                            session.task_profile.inferred_workload_counts.values()
                        ) or None,
                        execution_estimate_source=estimate_source,
                        safety_budget_used=safety_budget_used,
                        execution_safety_status=execution_safety_status,
                        workload_breakdown=dict(
                            session.task_profile.inferred_workload_counts
                        ),
                        time_breakdown_us=self._time_breakdown(
                            session.task_profile.inferred_workload_counts
                        ),
                        safety_budget_us=self._safety_budget_us(entry.period_ms),
                        dynamic_bound_notes=list(
                            session.task_profile.dynamic_bound_notes
                        ),
                        complexity_breakdown=[
                            (
                                f"{item.name}: "
                                f"{item.occurrences} x {item.base_cost} = {item.subtotal}"
                            )
                            for item in session.complexity_report.breakdown
                        ],
                    )
                )

        total_star_load = sum(result.task_load for result in task_results)
        scheduler_inputs = [
            SchedulerTaskInput(
                task_name=result.task_name,
                period_ms=result.period_ms,
                deadline_ms=result.deadline_ms,
                priority=result.priority,
                execution_budget_us=result.estimated_execution_time_us,
            )
            for result in task_results
        ]
        scheduler_result = FixedPriorityAnalyzer().analyze(scheduler_inputs)
        scheduler_by_task = {
            item.task_name: item for item in scheduler_result.task_results
        }
        task_results = [
            replace(
                result,
                scheduler_status=scheduler_by_task[result.task_name].status.name,
                scheduler_reason=scheduler_by_task[result.task_name].reason,
                response_time_us=scheduler_by_task[result.task_name].response_time_us,
            )
            for result in task_results
        ]
        system_status, system_reason = self._evaluate_system(
            task_results,
            scheduler_result.overall_status.name,
        )
        simulation_result = SchedulerSimulator().simulate(
            scheduler_inputs,
            self._simulation_window_ms,
        )
        return TaskSetResult(
            task_results=task_results,
            total_star_load=total_star_load,
            system_status=system_status,
            system_reason=system_reason,
            scheduler_status=scheduler_result.overall_status.name,
            scheduler_reason=scheduler_result.reason,
            scheduler_timeline=[
                (
                    f"{event.start_us / 1000.0:.3f}-"
                    f"{event.end_us / 1000.0:.3f} ms "
                    f"{event.task_name} ({event.note})"
                )
                for event in simulation_result.events[:40]
            ],
            scheduler_deadline_misses=simulation_result.deadline_misses[:40],
            scheduler_preemptions=simulation_result.preemptions[:40],
            simulation_window_ms=self._simulation_window_ms,
            simulation_idle_time_us=simulation_result.idle_time_us,
            simulation_task_stats=simulation_result.task_stats,
            simulation_interference_counts=simulation_result.interference_counts,
            simulation_interference_time_us=simulation_result.interference_time_us,
        )

    def _estimate_execution_time(
        self,
        task_profile,
        period_ms: int,
        hardware_adjusted_score: float,
    ) -> tuple[
        float | None,
        float | None,
        str,
        str | None,
        str | None,
    ]:
        if self._workload_cost_profile is not None:
            if not task_profile.dynamic_bound_verified:
                return (
                    None,
                    None,
                    "UNVERIFIED",
                    None,
                    "Dynamic execution estimate unavailable: "
                    + " ".join(task_profile.dynamic_bound_notes),
                )
            if not task_profile.inferred_workload_counts:
                return (
                    None,
                    None,
                    "UNVERIFIED",
                    None,
                    "Dynamic execution estimate unavailable: no bounded workload "
                    "could be inferred from the source.",
                )
            estimate = self._workload_execution_estimator.estimate_breakdown(
                workload_counts=task_profile.inferred_workload_counts,
                period_ms=period_ms,
                profile=self._workload_cost_profile,
            )
            return (
                estimate.estimated_execution_us,
                estimate.safety_budget_used,
                (
                    "PASS" if estimate.passes_safety_limit else "FAIL"
                )
                if self._workload_cost_profile.validated
                else "UNVERIFIED",
                (
                    "static_feature_time_model"
                    if self._workload_cost_profile.validated
                    else "unvalidated_static_feature_time_model"
                ),
                estimate.note,
            )

        if self._calibration_profile is None:
            return None, None, "UNVERIFIED", None, None
        estimate_us, note = self._execution_time_estimator.estimate_us(
            hardware_adjusted_score,
            self._calibration_profile,
        )
        legacy_note = (
            "Legacy structural-complexity interpolation was used. "
            "Prefer workload_class/work_units calibration. "
            + (note or "")
        ).strip()
        return (
            estimate_us,
            None,
            "UNVERIFIED",
            "legacy_complexity_profile",
            legacy_note,
        )

    @staticmethod
    def _append_estimate_note(reason: str, estimate_note: str | None) -> str:
        if estimate_note is None:
            return reason
        return f"{reason} {estimate_note}"

    @staticmethod
    def _write_descriptor(
        descriptor_dir: Path,
        index: int,
        entry: TaskSetEntry,
    ) -> Path:
        descriptor_file = descriptor_dir / f"task_{index}.yaml"
        descriptor_file.write_text(
            "\n".join(
                [
                    f"task_name: {entry.name}",
                    f"entry_function: {entry.entry_function}",
                    f"period_ms: {entry.period_ms}",
                    f"deadline_ms: {entry.deadline_ms}",
                    f"priority: {entry.priority}",
                    "stack_size: 512",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return descriptor_file

    @staticmethod
    def _calculate_task_load(
        complexity_score: float,
        max_complexity: float,
    ) -> float:
        if max_complexity <= 0:
            raise TaskSetError("Adjusted maximum complexity must be greater than 0.")
        return complexity_score / max_complexity

    def _time_breakdown(self, counts: dict[str, int]) -> dict[str, float]:
        if self._workload_cost_profile is None:
            return {}
        breakdown = {
            name: count * self._workload_cost_profile.coefficient_for(name)
            for name, count in counts.items()
        }
        breakdown["model_intercept"] = self._workload_cost_profile.intercept_us
        breakdown["engineering_margin"] = (
            sum(breakdown.values())
            * self._workload_cost_profile.estimate_margin_ratio
        )
        return breakdown

    def _safety_budget_us(self, period_ms: int) -> float | None:
        if self._workload_cost_profile is None:
            return None
        return period_ms * 1000.0 * self._workload_cost_profile.safety_limit_ratio

    @staticmethod
    def _evaluate_system(
        task_results: list[TaskSetTaskResult],
        scheduler_status: str,
    ) -> tuple[str, str]:
        if any(
            result.execution_safety_status == "FAIL"
            for result in task_results
        ):
            return (
                "SYSTEM_REJECT",
                "At least one calibrated dynamic workload exceeds the configured "
                "execution safety budget.",
            )

        if any(
            result.execution_safety_status == "UNVERIFIED"
            for result in task_results
        ):
            if any(
                result.execution_estimate_source
                == "unvalidated_static_feature_time_model"
                for result in task_results
            ):
                return (
                    "UNVERIFIED",
                    "The available board sweeps calibrated kernel repetitions, "
                    "not STAR AST feature counts. The microsecond feature model "
                    "must be calibrated with feature-aligned measurements before "
                    "it can accept or reject tasks.",
                )
            return (
                "UNVERIFIED",
                "At least one task has no statically proven dynamic execution "
                "bound; schedulability cannot be concluded.",
            )

        if scheduler_status == "NOT_FEASIBLE":
            return (
                "NOT_FEASIBLE",
                "Fixed-priority response-time analysis found a deadline miss.",
            )

        return (
            "FEASIBLE",
            "Board-calibrated execution-time budgets pass their period limits and the "
            "fixed-priority task set is schedulable.",
        )
