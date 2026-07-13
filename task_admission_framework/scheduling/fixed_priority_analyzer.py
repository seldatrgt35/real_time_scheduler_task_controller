"""Fixed-priority response-time analysis."""

from __future__ import annotations

import math

from task_admission_framework.scheduling.scheduler_result import (
    SchedulerSetResult,
    SchedulerTaskInput,
    SchedulerTaskResult,
)
from task_admission_framework.scheduling.scheduler_status import SchedulerStatus


class FixedPriorityAnalyzer:
    """Runs response-time analysis for validated execution budgets.

    Assumptions: single-core, preemptive fixed-priority scheduling, higher
    numeric FreeRTOS priority means higher scheduling priority, and tasks are
    periodic or sporadic.
    """

    _MAX_ITERATIONS = 100

    def analyze(self, tasks: list[SchedulerTaskInput]) -> SchedulerSetResult:
        """Analyze a task set or return UNVERIFIED if budgets are missing."""

        if not tasks:
            return SchedulerSetResult(
                task_results=[],
                overall_status=SchedulerStatus.UNVERIFIED,
                reason="No scheduler tasks were provided.",
            )

        if any(task.execution_budget_us is None for task in tasks):
            return self._unverified(tasks)

        results = [self._analyze_task(task, tasks) for task in tasks]
        if any(result.status is SchedulerStatus.NOT_FEASIBLE for result in results):
            return SchedulerSetResult(
                task_results=results,
                overall_status=SchedulerStatus.NOT_FEASIBLE,
                reason="At least one task response time exceeds its deadline.",
            )

        if any(result.status is SchedulerStatus.UNVERIFIED for result in results):
            return SchedulerSetResult(
                task_results=results,
                overall_status=SchedulerStatus.UNVERIFIED,
                reason="At least one response-time calculation did not converge.",
            )

        return SchedulerSetResult(
            task_results=results,
            overall_status=SchedulerStatus.FEASIBLE,
            reason="All synthetic response-time calculations meet their deadlines.",
        )

    def _analyze_task(
        self,
        task: SchedulerTaskInput,
        tasks: list[SchedulerTaskInput],
    ) -> SchedulerTaskResult:
        execution_budget_us = self._require_budget(task)
        blocking_budget_us = task.blocking_budget_us
        deadline_us = task.deadline_ms * 1000.0
        higher_priority_tasks = [
            other for other in tasks if other.priority > task.priority
        ]

        response_time_us = execution_budget_us + blocking_budget_us
        for _ in range(self._MAX_ITERATIONS):
            interference_us = sum(
                math.ceil(response_time_us / (other.period_ms * 1000.0))
                * self._require_budget(other)
                for other in higher_priority_tasks
            )
            next_response_time_us = (
                execution_budget_us + blocking_budget_us + interference_us
            )

            if next_response_time_us > deadline_us:
                return SchedulerTaskResult(
                    task_name=task.task_name,
                    priority=task.priority,
                    response_time_us=next_response_time_us,
                    deadline_us=deadline_us,
                    status=SchedulerStatus.NOT_FEASIBLE,
                    reason="Response time exceeds deadline.",
                )

            if math.isclose(next_response_time_us, response_time_us):
                return SchedulerTaskResult(
                    task_name=task.task_name,
                    priority=task.priority,
                    response_time_us=next_response_time_us,
                    deadline_us=deadline_us,
                    status=SchedulerStatus.FEASIBLE,
                    reason="Response time converged within deadline.",
                )

            response_time_us = next_response_time_us

        return SchedulerTaskResult(
            task_name=task.task_name,
            priority=task.priority,
            response_time_us=response_time_us,
            deadline_us=deadline_us,
            status=SchedulerStatus.UNVERIFIED,
            reason="Response-time iteration limit reached before convergence.",
        )

    @staticmethod
    def _require_budget(task: SchedulerTaskInput) -> float:
        if task.execution_budget_us is None:
            raise ValueError("Execution budget is required for response-time analysis.")
        return task.execution_budget_us

    @staticmethod
    def _unverified(tasks: list[SchedulerTaskInput]) -> SchedulerSetResult:
        results = [
            SchedulerTaskResult(
                task_name=task.task_name,
                priority=task.priority,
                response_time_us=None,
                deadline_us=task.deadline_ms * 1000.0,
                status=SchedulerStatus.UNVERIFIED,
                reason="Validated execution-budget calibration is missing.",
            )
            for task in tasks
        ]
        return SchedulerSetResult(
            task_results=results,
            overall_status=SchedulerStatus.UNVERIFIED,
            reason="Validated execution-budget calibration is missing.",
        )

