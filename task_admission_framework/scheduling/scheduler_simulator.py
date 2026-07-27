"""Discrete fixed-priority scheduler simulator."""

from __future__ import annotations

from dataclasses import dataclass

from task_admission_framework.scheduling.schedule_event import ScheduleEvent
from task_admission_framework.scheduling.scheduler_result import SchedulerTaskInput
from task_admission_framework.scheduling.scheduler_status import SchedulerStatus
from task_admission_framework.scheduling.simulation_result import (
    SchedulerSimulationResult,
)


@dataclass(slots=True)
class _Job:
    task_name: str
    release_us: float
    deadline_us: float
    priority: int
    remaining_us: float
    sequence: int


class SchedulerSimulator:
    """Simulates READY/RUNNING/IDLE behavior for fixed-priority tasks."""

    _TIME_EPSILON_US = 1e-9

    def simulate(
        self,
        tasks: list[SchedulerTaskInput],
        simulation_window_ms: int,
    ) -> SchedulerSimulationResult:
        """Run a simple event-driven simulation over the requested window."""

        if not tasks:
            return SchedulerSimulationResult(
                events=[],
                status=SchedulerStatus.UNVERIFIED,
                reason="No scheduler tasks were provided.",
            )

        if any(task.execution_budget_us is None for task in tasks):
            return SchedulerSimulationResult(
                events=[],
                status=SchedulerStatus.UNVERIFIED,
                reason="Execution budgets are required for scheduler simulation.",
            )

        window_us = simulation_window_ms * 1000.0
        next_release_us = {task.task_name: 0.0 for task in tasks}
        sequence_counter = 0
        ready_jobs: list[_Job] = []
        running_job: _Job | None = None
        now_us = 0.0
        events: list[ScheduleEvent] = []
        preemptions: list[str] = []
        deadline_misses: list[str] = []
        idle_time_us = 0.0

        while now_us < window_us:
            sequence_counter = self._release_jobs(
                tasks,
                next_release_us,
                ready_jobs,
                now_us,
                sequence_counter,
            )

            selected_job = self._select_job(ready_jobs, running_job)
            if running_job is not None and selected_job is not running_job:
                preemptions.append(
                    f"{selected_job.task_name} preempted {running_job.task_name} "
                    f"at {now_us / 1000.0:.3f} ms."
                )
                ready_jobs.append(running_job)
                running_job = None

            if running_job is None and selected_job is not None:
                ready_jobs.remove(selected_job)
                running_job = selected_job

            if (
                running_job is not None
                and running_job.remaining_us <= self._TIME_EPSILON_US
            ):
                running_job = None
                continue

            next_release = min(next_release_us.values())
            if running_job is None:
                interval_end = min(next_release, window_us)
                if interval_end <= now_us:
                    interval_end = window_us
                idle_time_us += interval_end - now_us
                self._append_event(events, now_us, interval_end, "IDLE", "idle")
                now_us = interval_end
                continue

            completion_us = now_us + running_job.remaining_us
            interval_end = min(completion_us, next_release, window_us)
            ran_us = interval_end - now_us
            running_job.remaining_us -= ran_us
            self._append_event(events, now_us, interval_end, running_job.task_name, "run")
            now_us = interval_end

            if running_job.remaining_us <= self._TIME_EPSILON_US:
                if now_us > running_job.deadline_us:
                    deadline_misses.append(
                        f"{running_job.task_name} missed deadline at "
                        f"{now_us / 1000.0:.3f} ms."
                    )
                running_job = None

        status = SchedulerStatus.FEASIBLE
        reason = "Simulation completed without deadline misses."
        if deadline_misses:
            status = SchedulerStatus.NOT_FEASIBLE
            reason = "At least one simulated job missed its deadline."

        return SchedulerSimulationResult(
            events=events,
            deadline_misses=deadline_misses,
            preemptions=preemptions,
            idle_time_us=idle_time_us,
            status=status,
            reason=reason,
        )

    @staticmethod
    def _release_jobs(
        tasks: list[SchedulerTaskInput],
        next_release_us: dict[str, float],
        ready_jobs: list[_Job],
        now_us: float,
        sequence_counter: int,
    ) -> int:
        for task in tasks:
            while (
                next_release_us[task.task_name]
                <= now_us + SchedulerSimulator._TIME_EPSILON_US
            ):
                execution_budget_us = task.execution_budget_us
                if execution_budget_us is None:
                    continue
                ready_jobs.append(
                    _Job(
                        task_name=task.task_name,
                        release_us=next_release_us[task.task_name],
                        deadline_us=(
                            next_release_us[task.task_name]
                            + task.deadline_ms * 1000.0
                        ),
                        priority=task.priority,
                        remaining_us=execution_budget_us,
                        sequence=sequence_counter,
                    )
                )
                sequence_counter += 1
                next_release_us[task.task_name] += task.period_ms * 1000.0
        return sequence_counter

    @staticmethod
    def _select_job(
        ready_jobs: list[_Job],
        running_job: _Job | None,
    ) -> _Job | None:
        candidates = list(ready_jobs)
        if running_job is not None:
            candidates.append(running_job)
        if not candidates:
            return None
        return max(candidates, key=lambda job: (job.priority, -job.sequence))

    @staticmethod
    def _append_event(
        events: list[ScheduleEvent],
        start_us: float,
        end_us: float,
        task_name: str,
        note: str,
    ) -> None:
        if end_us <= start_us:
            return
        if events and events[-1].task_name == task_name and events[-1].note == note:
            previous = events[-1]
            events[-1] = ScheduleEvent(
                start_us=previous.start_us,
                end_us=end_us,
                task_name=task_name,
                note=note,
            )
            return
        events.append(
            ScheduleEvent(
                start_us=start_us,
                end_us=end_us,
                task_name=task_name,
                note=note,
            )
        )
