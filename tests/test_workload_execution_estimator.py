from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from task_admission_framework.analyzer.workload_classifier import WorkloadClassifier
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
                "fixed_point_filter": 160.0,
                "can_checksum": 160.0,
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

    def test_mixed_breakdown_uses_separate_costs(self) -> None:
        estimate = WorkloadExecutionEstimator().estimate_breakdown(
            workload_counts={
                "integer_control": 100,
                "floating_point_iir": 2,
            },
            period_ms=1,
            profile=self.profile,
        )

        expected_cycles = 100 * 155.0 + 2 * 600.0
        self.assertEqual(estimate.workload_class, "mixed")
        self.assertEqual(estimate.estimated_cycles, expected_cycles)
        self.assertEqual(
            estimate.workload_breakdown,
            {"integer_control": 100, "floating_point_iir": 2},
        )

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

    def test_taskset_uses_automatic_workload_breakdown(self) -> None:
        analyzer = TaskSetAnalyzer(
            pipeline=object(),
            workload_cost_profile=self.profile,
        )
        task_profile = SimpleNamespace(
            dynamic_bound_verified=True,
            dynamic_bound_notes=[],
            inferred_workload_counts={
                "integer_control": 100,
                "floating_point_iir": 2,
            },
        )

        result = analyzer._estimate_execution_time(
            task_profile,
            1,
            hardware_adjusted_score=999999.0,
        )

        expected_cycles = 100 * 155.0 + 2 * 600.0
        self.assertAlmostEqual(result[0] or 0.0, expected_cycles / 48.0)
        self.assertEqual(result[1], expected_cycles)
        self.assertEqual(result[3], "PASS")
        self.assertEqual(result[4], "workload_cost_profile")
        self.assertIn("100 integer_control", result[5] or "")

    def test_taskset_does_not_invent_missing_dynamic_bound(self) -> None:
        analyzer = TaskSetAnalyzer(
            pipeline=object(),
            workload_cost_profile=self.profile,
        )

        result = analyzer._estimate_execution_time(
            SimpleNamespace(
                dynamic_bound_verified=False,
                dynamic_bound_notes=[
                    "Loop at line 12 has no statically proven bound."
                ],
                inferred_workload_counts={},
            ),
            1,
            hardware_adjusted_score=50.0,
        )

        self.assertEqual(result[:5], (None, None, None, "UNVERIFIED", None))
        self.assertIn("line 12", result[5] or "")

    def test_automatic_workload_classification(self) -> None:
        classify = WorkloadClassifier.classify

        self.assertEqual(
            classify(["output", "=", "a", "*", "b", "+", "0.5f"]),
            "floating_point_iir",
        )
        self.assertEqual(
            classify(["crc", "^", "payload", "[", "i", "]"]),
            "can_checksum",
        )
        self.assertEqual(
            classify(["result", "=", "input", "*", "gain", ">>", "8"]),
            "fixed_point_filter",
        )
        self.assertEqual(
            classify(["if", "(", "speed", ">", "limit", ")"]),
            "integer_control",
        )


if __name__ == "__main__":
    unittest.main()
