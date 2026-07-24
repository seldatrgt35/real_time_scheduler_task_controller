"""Task-set analyzer built on existing STAR single-task components."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from task_admission_framework.admission.admission_controller import AdmissionController
from task_admission_framework.admission.admission_decision import AdmissionStatus
from task_admission_framework.calibration.complexity_time_profile import (
    ComplexityTimeProfile,
)
from task_admission_framework.calibration.execution_time_estimator import (
    ExecutionTimeEstimator,
)
from task_admission_framework.calibration.workload_cost_profile import (
    WorkloadCostProfile,
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
        simulation_window_ms: int = 100,
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
        self._workload_cost_profile = workload_cost_profile
        self._workload_execution_estimator = WorkloadExecutionEstimator()
        self._simulation_window_ms = simulation_window_ms

    def analyze(self, entries: list[TaskSetEntry]) -> TaskSetResult:
        if not entries:
            raise TaskSetError("Task set must contain at least one task.")

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
                    estimated_execution_cycles,
                    safety_budget_used,
                    execution_safety_status,
                    estimate_source,
                    estimate_note,
                ) = self._estimate_execution_time(
                    entry,
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
                        workload_class=entry.workload_class,
                        work_units=entry.work_units,
                        estimated_execution_cycles=estimated_execution_cycles,
                        execution_estimate_source=estimate_source,
                        safety_budget_used=safety_budget_used,
                        execution_safety_status=execution_safety_status,
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
        system_status, system_reason = self._evaluate_system(
            task_results,
            total_star_load,
        )
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
        )

    def _estimate_execution_time(
        self,
        entry: TaskSetEntry,
        hardware_adjusted_score: float,
    ) -> tuple[
        float | None,
        float | None,
        float | None,
        str,
        str | None,
        str | None,
    ]:
        if self._workload_cost_profile is not None:
            if entry.workload_class is None or entry.work_units is None:
                return (
                    None,
                    None,
                    None,
                    "UNVERIFIED",
                    None,
                    "Dynamic execution estimate unavailable: workload_class and "
                    "bounded work_units are required.",
                )
            estimate = self._workload_execution_estimator.estimate(
                workload_class=entry.workload_class,
                work_units=entry.work_units,
                period_ms=entry.period_ms,
                profile=self._workload_cost_profile,
            )
            return (
                estimate.estimated_execution_us,
                estimate.estimated_cycles,
                estimate.safety_budget_used,
                "PASS" if estimate.passes_safety_limit else "FAIL",
                "workload_cost_profile",
                estimate.note,
            )

        if self._calibration_profile is None:
            return None, None, None, "UNVERIFIED", None, None
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
                    f"criticality: {entry.criticality}",
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

    @staticmethod
    def _evaluate_system(
        task_results: list[TaskSetTaskResult],
        total_star_load: float,
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
            result.admission_status == AdmissionStatus.REJECT.name
            for result in task_results
        ):
            return (
                "SYSTEM_REJECT",
                "At least one task is individually rejected by admission rules.",
            )

        if total_star_load <= 1.0:
            return (
                "FEASIBLE",
                "Total STAR load is less than or equal to 1.0.",
            )

        if total_star_load <= 1.2:
            return (
                "RISK",
                "Total STAR load is above 1.0 but below or equal to 1.2.",
            )

        return (
            "NOT_FEASIBLE",
            "Total STAR load is above 1.2.",
        )
