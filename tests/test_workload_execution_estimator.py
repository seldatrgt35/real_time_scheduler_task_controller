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

    def test_s32k148_profile_contains_board_validated_memory_cost(self) -> None:
        profile_path = (
            Path(__file__).parents[1]
            / "task_admission_framework"
            / "calibration"
            / "profiles"
            / "S32K148_workload_costs.json"
        )
        profile = WorkloadCostLoader().load(profile_path)

        self.assertAlmostEqual(
            profile.coefficient_for("sequential_memory_access"),
            0.8976245990,
        )

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

    def test_admission_adds_supported_branch_operation(self) -> None:
        profile = replace(
            self.profile,
            execution_time_us_per_work_unit={
                **self.profile.execution_time_us_per_work_unit,
                "branch_evaluation": 0.5,
            },
        )
        result = evaluate_execution_admission(
            SimpleNamespace(
                task_name="BranchTask",
                dynamic_bound_verified=True,
                dynamic_bound_notes=[],
                inferred_workload_counts={"integer_control": 10},
                inferred_operation_counts={
                    "branch_evaluation": 8,
                    "integer_compare": 9,
                },
            ),
            period_ms=1,
            profile=profile,
        )

        self.assertEqual(
            result.workload_counts,
            {"integer_control": 10, "branch_evaluation": 8},
        )
        self.assertAlmostEqual(result.estimated_execution_us or 0.0, 34.0)

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

        self.assertAlmostEqual(estimate.nominal_execution_us, 7.0 + 10 * 3.0)
        self.assertAlmostEqual(
            estimate.admission_execution_us,
            (7.0 + 10 * 3.0) * 1.1,
        )
        self.assertEqual(estimate.estimated_execution_us, estimate.nominal_execution_us)
        self.assertIn("10% engineering margin", estimate.note)

    def test_s32k148_profile_reproduces_calibration_value_but_is_unvalidated(self) -> None:
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

        self.assertFalse(profile.validated)
        self.assertAlmostEqual(estimate.estimated_execution_us, 209.7436, places=3)
        self.assertAlmostEqual(estimate.admission_execution_us, 230.7180, places=3)
        self.assertTrue(estimate.passes_safety_limit)

    def test_composite_loop_classes_are_not_primitive_double_counted(self) -> None:
        from task_admission_framework.analyzer.dynamic_operations import (
            DynamicOperationAnalyzer,
        )

        self.assertTrue(
            {
                "checksum_processed_bytes",
                "bulk_memory_copy_bytes",
                "q15_multiply",
                "gpio_read",
            }.issubset(DynamicOperationAnalyzer._COMPOSITE_LOOP_WORKLOADS)
        )

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

    def test_taskset_merges_supported_dynamic_operation_counts(self) -> None:
        analyzer = TaskSetAnalyzer(
            pipeline=object(),
            workload_cost_profile=self.profile,
        )
        task_profile = SimpleNamespace(
            task_name="MixedTask",
            dynamic_bound_verified=True,
            dynamic_bound_notes=[],
            inferred_workload_counts={"integer_control": 10},
            inferred_operation_counts={
                "floating_point_iir": 2,
                "unsupported_operation": 999,
            },
        )

        result = analyzer._estimate_execution_time(task_profile, 1, 0.0)

        self.assertEqual(result[0], 50.0)
        self.assertIn("10 integer_control", result[4] or "")
        self.assertIn("2 floating_point_iir", result[4] or "")
        self.assertNotIn("unsupported_operation", result[4] or "")
        self.assertEqual(
            analyzer._supported_execution_counts(task_profile),
            {"integer_control": 10, "floating_point_iir": 2},
        )

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
            classify(["destination_buffer", "[", "i", "]", "=", "source_buffer", "[", "i", "]"]),
            "sequential_memory_access",
        )
        self.assertEqual(
            classify(["value", "=", "value", "%", "integer_modulo_variable"]),
            "integer_modulo_variable",
        )
        self.assertEqual(
            classify(["value", "=", "value", "/", "integer_divide_variable"]),
            "integer_divide_variable",
        )
        self.assertEqual(
            classify(["value", "=", "value", "*", "integer_multiply_variable"]),
            "integer_multiply_variable",
        )
        self.assertEqual(
            classify(["value", "=", "value", "+", "basic_integer_add_sub"]),
            "basic_integer_add_sub",
        )
        self.assertEqual(
            classify(["if", "(", "branch_evaluation", "!=", "0", ")"]),
            "branch_evaluation",
        )
        self.assertEqual(
            classify(["value", "=", "value", "^", "bitwise_logic"]),
            "bitwise_logic",
        )
        self.assertEqual(
            classify(["value", "=", "value", ">>", "shift_rotate"]),
            "shift_rotate",
        )
        self.assertEqual(
            classify(["value", "=", "random_indexed_memory", "[", "index", "]"]),
            "random_indexed_memory_access",
        )
        self.assertEqual(
            classify(["bulk_memory_copy", "[", "index", "]"]),
            "bulk_memory_copy_bytes",
        )
        self.assertEqual(
            classify(["bulk_memory_set", "[", "index", "]"]),
            "bulk_memory_set_bytes",
        )
        floating_markers = (
            "float32_add_sub",
            "float32_multiply",
            "float32_divide",
            "float64_add_sub",
            "float64_multiply",
            "float64_divide",
            "int32_to_float32",
            "float32_to_int32",
            "int32_to_float64",
            "float64_to_int32",
        )
        for marker in floating_markers:
            self.assertEqual(
                classify(["value", "=", marker, "+", "1.0"]),
                marker,
            )
        feature_markers = (
            "q15_multiply", "q15_mac", "q31_multiply", "q31_mac",
            "fixed_point_saturation", "sqrtf_call", "fabsf_call",
            "sinf_call", "cosf_call", "checksum_processed_bytes",
            "direct_function_call", "indirect_function_call",
            "switch_case_4", "switch_case_8", "switch_case_16",
            "volatile_read", "volatile_write", "mmio_read", "mmio_write",
            "gpio_read", "gpio_write",
        )
        for marker in feature_markers:
            self.assertEqual(classify([marker, "=", "value"]), marker)
        self.assertEqual(
            classify(["if", "(", "speed", ">", "limit", ")"]),
            "integer_control",
        )


if __name__ == "__main__":
    unittest.main()
