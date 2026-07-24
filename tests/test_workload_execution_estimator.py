from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from task_admission_framework.calibration.workload_cost_loader import (
    WorkloadCostLoader,
)
from task_admission_framework.calibration.workload_cost_profile import (
    WorkloadCostProfile,
)
from task_admission_framework.calibration.workload_execution_estimator import (
    WorkloadExecutionEstimator,
)
from task_admission_framework.taskset.taskset_analyzer import TaskSetAnalyzer
from task_admission_framework.taskset.taskset_entry import TaskSetEntry


class WorkloadExecutionEstimatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = WorkloadCostProfile(
            profile_id="test",
            reference_hardware="S32K148",
            clock_frequency_mhz=48.0,
            safety_limit_ratio=0.8,
            validated=True,
            cycles_per_work_unit={
                "integer_control": 155.0,
                "floating_point_iir": 600.0,
            },
        )

    def test_estimate_reports_cycles_time_and_safety_load(self) -> None:
        estimate = WorkloadExecutionEstimator().estimate(
            workload_class="integer-control",
            work_units=100,
            period_ms=1,
            profile=self.profile,
        )

        self.assertEqual(estimate.workload_class, "integer_control")
        self.assertEqual(estimate.estimated_cycles, 15500.0)
        self.assertAlmostEqual(estimate.estimated_execution_us, 322.9166667)
        self.assertEqual(estimate.safety_budget_cycles, 38400.0)
        self.assertAlmostEqual(estimate.safety_budget_used, 15500.0 / 38400.0)
        self.assertTrue(estimate.passes_safety_limit)

    def test_float_class_uses_separate_calibrated_cost(self) -> None:
        estimate = WorkloadExecutionEstimator().estimate(
            workload_class="floating_point_iir",
            work_units=100,
            period_ms=1,
            profile=self.profile,
        )

        self.assertEqual(estimate.estimated_cycles, 60000.0)
        self.assertFalse(estimate.passes_safety_limit)

    def test_rejects_unbounded_or_unknown_work(self) -> None:
        with self.assertRaisesRegex(ValueError, "work_units"):
            WorkloadExecutionEstimator().estimate(
                workload_class="integer_control",
                work_units=0,
                period_ms=1,
                profile=self.profile,
            )
        with self.assertRaisesRegex(ValueError, "Unknown workload class"):
            WorkloadExecutionEstimator().estimate(
                workload_class="unknown",
                work_units=1,
                period_ms=1,
                profile=self.profile,
            )

    def test_loader_validates_and_normalizes_profile(self) -> None:
        payload = {
            "profile_id": "test",
            "reference_hardware": "S32K148",
            "clock_frequency_mhz": 48,
            "safety_limit_ratio": 0.8,
            "validated": True,
            "cycles_per_work_unit": {"integer-control": 155},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            profile = WorkloadCostLoader().load(path)

        self.assertEqual(profile.coefficient_for("integer_control"), 155.0)
        self.assertTrue(profile.validated)

    def test_taskset_prefers_dynamic_workload_estimate(self) -> None:
        analyzer = TaskSetAnalyzer(
            pipeline=object(),
            workload_cost_profile=self.profile,
        )
        entry = self._entry(workload_class="integer_control", work_units=100)

        (
            estimate_us,
            cycles,
            load,
            safety_status,
            source,
            note,
        ) = analyzer._estimate_execution_time(
            entry,
            hardware_adjusted_score=999999.0,
        )

        self.assertAlmostEqual(estimate_us, 15500.0 / 48.0)
        self.assertEqual(cycles, 15500.0)
        self.assertAlmostEqual(load, 15500.0 / 38400.0)
        self.assertEqual(safety_status, "PASS")
        self.assertEqual(source, "workload_cost_profile")
        self.assertIn("100 work units", note or "")

    def test_taskset_does_not_invent_missing_dynamic_bound(self) -> None:
        analyzer = TaskSetAnalyzer(
            pipeline=object(),
            workload_cost_profile=self.profile,
        )

        result = analyzer._estimate_execution_time(
            self._entry(workload_class=None, work_units=None),
            hardware_adjusted_score=50.0,
        )

        self.assertEqual(result[:5], (None, None, None, "UNVERIFIED", None))
        self.assertIn("required", result[5] or "")

    @staticmethod
    def _entry(
        *,
        workload_class: str | None,
        work_units: int | None,
    ) -> TaskSetEntry:
        return TaskSetEntry(
            name="Task",
            source_file=Path("task.c"),
            entry_function="task",
            period_ms=1,
            deadline_ms=1,
            priority=1,
            criticality="HIGH",
            hardware_profile_file=Path("hardware.json"),
            rules_file=Path("rules.json"),
            workload_class=workload_class,
            work_units=work_units,
        )


if __name__ == "__main__":
    unittest.main()
