from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from task_admission_framework.analyzer.workload_classifier import WorkloadClassifier
from task_admission_framework.calibration.workload_cost_loader import (
    WorkloadCostLoader,
)
from task_admission_framework.calibration.execution_admission import (
    evaluate_execution_admission,
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
            safety_limit_ratio=0.8,
            validated=True,
            execution_time_us_per_work_unit={
                "integer_control": 3.0,
                "fixed_point_filter": 4.0,
                "can_checksum": 5.0,
                "floating_point_iir": 10.0,
            },
        )

    def test_estimate_reports_time_and_safety_load(self) -> None:
        estimate = WorkloadExecutionEstimator().estimate(
            workload_class="integer-control",
            work_units=100,
            period_ms=1,
            profile=self.profile,
        )

        self.assertEqual(estimate.workload_class, "integer_control")
        self.assertEqual(estimate.estimated_execution_us, 300.0)
        self.assertEqual(estimate.safety_budget_us, 800.0)
        self.assertAlmostEqual(estimate.safety_budget_used, 300.0 / 800.0)
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

        expected_us = 100 * 3.0 + 2 * 10.0
        self.assertEqual(estimate.workload_class, "mixed")
        self.assertEqual(estimate.estimated_execution_us, expected_us)
        self.assertEqual(
            estimate.workload_breakdown,
            {"integer_control": 100, "floating_point_iir": 2},
        )
        self.assertEqual(
            estimate.time_breakdown_us,
            {"integer_control": 300.0, "floating_point_iir": 20.0},
        )

    def test_mixed_admission_uses_measured_period_limit(self) -> None:
        result = evaluate_execution_admission(
            SimpleNamespace(
                task_name="UnknownTask",
                dynamic_bound_verified=True,
                dynamic_bound_notes=[],
                inferred_workload_counts={
                    "integer_control": 100,
                    "fixed_point_filter": 50,
                    "floating_point_iir": 10,
                    "can_checksum": 20,
                },
            ),
            period_ms=5,
            profile=self.profile,
        )

        self.assertEqual(result.status, "PASS")
        expected_us = 100 * 3 + 50 * 4 + 10 * 10 + 20 * 5
        self.assertEqual(result.safety_budget_us, 4000.0)
        self.assertAlmostEqual(result.estimated_execution_us or 0.0, expected_us)
        self.assertAlmostEqual(result.safety_budget_used or 0.0, expected_us / 4000)

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
            "safety_limit_ratio": 0.8,
            "validated": True,
            "intercept_us": 7.0,
            "estimate_margin_ratio": 0.1,
            "execution_time_us_per_work_unit": {"integer-control": 3.0},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            profile = WorkloadCostLoader().load(path)

        self.assertEqual(profile.coefficient_for("integer_control"), 3.0)
        self.assertEqual(profile.intercept_us, 7.0)
        self.assertEqual(profile.estimate_margin_ratio, 0.1)
        self.assertTrue(profile.validated)

    def test_estimate_applies_intercept_and_engineering_margin(self) -> None:
        profile = replace(
            self.profile,
            intercept_us=7.0,
            estimate_margin_ratio=0.1,
        )

        estimate = WorkloadExecutionEstimator().estimate_breakdown(
            workload_counts={"integer_control": 10},
            period_ms=1,
            profile=profile,
        )

        self.assertAlmostEqual(
            estimate.estimated_execution_us,
            (7.0 + 10 * 3.0) * 1.1,
        )
        self.assertIn("10% engineering margin", estimate.note)

    def test_s32k148_profile_reproduces_board_validated_brake_model(self) -> None:
        profile_path = (
            Path(__file__).parents[1]
            / "task_admission_framework"
            / "calibration"
            / "profiles"
            / "S32K148_workload_costs.json"
        )
        profile = WorkloadCostLoader().load(profile_path)

        estimate = WorkloadExecutionEstimator().estimate_breakdown(
            workload_counts={
                "integer_control": 48,
                "fixed_point_filter": 96,
                "floating_point_iir": 12,
            },
            period_ms=10,
            profile=profile,
        )

        self.assertTrue(profile.validated)
        self.assertAlmostEqual(estimate.estimated_execution_us, 238.3788, places=3)
        self.assertTrue(estimate.passes_safety_limit)

    def test_taskset_uses_automatic_workload_breakdown(self) -> None:
        analyzer = TaskSetAnalyzer(
            pipeline=object(),
            workload_cost_profile=self.profile,
        )
        task_profile = SimpleNamespace(
            task_name="UnknownTask",
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

        expected_us = 100 * 3.0 + 2 * 10.0
        self.assertAlmostEqual(result[0] or 0.0, expected_us)
        self.assertEqual(result[2], "PASS")
        self.assertEqual(result[3], "static_feature_time_model")
        self.assertIn("100 integer_control", result[4] or "")

    def test_taskset_does_not_invent_missing_dynamic_bound(self) -> None:
        analyzer = TaskSetAnalyzer(
            pipeline=object(),
            workload_cost_profile=self.profile,
        )

        result = analyzer._estimate_execution_time(
            SimpleNamespace(
                task_name="UnknownTask",
                dynamic_bound_verified=False,
                dynamic_bound_notes=[
                    "Loop at line 12 has no statically proven bound."
                ],
                inferred_workload_counts={},
            ),
            1,
            hardware_adjusted_score=50.0,
        )

        self.assertEqual(result[:4], (None, None, "UNVERIFIED", None))
        self.assertIn("line 12", result[4] or "")

    def test_unvalidated_feature_model_cannot_accept_task(self) -> None:
        analyzer = TaskSetAnalyzer(
            pipeline=object(),
            workload_cost_profile=replace(self.profile, validated=False),
        )
        task_profile = SimpleNamespace(
            task_name="UnknownTask",
            dynamic_bound_verified=True,
            dynamic_bound_notes=[],
            inferred_workload_counts={"integer_control": 10},
        )

        result = analyzer._estimate_execution_time(task_profile, 1, 0.0)

        self.assertEqual(result[0], 30.0)
        self.assertEqual(result[2], "UNVERIFIED")
        self.assertEqual(result[3], "unvalidated_static_feature_time_model")


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
