import unittest

from task_admission_framework.model.task_profile import TaskProfile
from task_admission_framework.taskset.taskset_analyzer import TaskSetAnalyzer
from task_admission_framework.calibration.contextual_integer_execution import (
    estimate_contextual_integer,
)


class ContextualIntegerExecutionTest(unittest.TestCase):
    def test_validated_counts_produce_nominal_and_safe_estimate(self):
        estimate = estimate_contextual_integer({
            "loop_invocations": 1,
            "loop_iterations": 192,
            "add_index_u32": 192,
            "multiply_local_u32": 192,
            "index_before_multiply_u32": 192,
        })
        self.assertTrue(estimate.verified)
        self.assertAlmostEqual(105.27, estimate.nominal_us, places=2)
        self.assertAlmostEqual(estimate.nominal_us * 1.15, estimate.safe_us)

    def test_unknown_context_is_not_estimated(self):
        estimate = estimate_contextual_integer({"subtract_memory_u32": 8})
        self.assertFalse(estimate.verified)
        self.assertIsNone(estimate.nominal_us)
        self.assertEqual(("subtract_memory_u32",), estimate.unsupported_features)

    def test_powertrain_numeric_estimate_is_verified_by_independent_holdout(self):
        estimate = estimate_contextual_integer({
            "loop_invocations": 4,
            "loop_iterations": 272,
            "powertrain_group_loop_invocations": 4,
            "powertrain_group_loop_iterations": 272,
            "powertrain_signed_arithmetic_i32": 80,
            "powertrain_saturation_clamp_i32": 72,
            "powertrain_lookup_1d_i32": 64,
            "powertrain_linear_interpolation_i32": 56,
        })
        self.assertTrue(estimate.verified)
        self.assertAlmostEqual(315.83025, estimate.nominal_us, places=5)
        self.assertAlmostEqual(363.2047875, estimate.safe_us, places=5)
        self.assertIn("Validated for the S32K148", estimate.note)

    def test_mixed_add_context_correction_matches_board_calibration(self):
        estimate = estimate_contextual_integer({
            "loop_invocations": 1,
            "loop_iterations": 192,
            "add_constant_u32": 192,
            "add_local_u32": 192,
            "add_index_u32": 192,
            "add_memory_u32": 192,
            "mixed_add_context_u32": 192,
        })
        self.assertTrue(estimate.verified)
        self.assertAlmostEqual(177.479, estimate.nominal_us, places=3)

    def test_control_bitwise_board_features_are_supported(self):
        estimate = estimate_contextual_integer({
            "loop_invocations": 1,
            "loop_iterations": 192,
            "bitwise_and_u32": 192,
            "bitwise_or_u32": 192,
            "bitwise_xor_u32": 192,
            "shift_right_u32": 192,
            "mixed_bitwise_context_u32": 192,
        })
        self.assertTrue(estimate.verified)
        self.assertAlmostEqual(137.416, estimate.nominal_us, places=3)

    def test_taskset_prefers_board_validated_contextual_estimate(self):
        profile = TaskProfile(
            task_name="contextual",
            contextual_integer_counts={
                "loop_invocations": 1,
                "loop_iterations": 192,
                "add_index_u32": 192,
                "multiply_local_u32": 192,
                "index_before_multiply_u32": 192,
            },
            dynamic_bound_verified=True,
        )
        estimate = TaskSetAnalyzer()._estimate_execution_time(profile, 1, 0.0)
        self.assertAlmostEqual(105.27, estimate[0], places=2)
        self.assertEqual("PASS", estimate[2])
        self.assertEqual("contextual_integer_o0_board_model", estimate[3])

    def test_taskset_rejects_unproven_contextual_bound(self):
        profile = TaskProfile(
            task_name="unbounded",
            contextual_integer_counts={"add_index_u32": 1},
            dynamic_bound_verified=False,
        )
        estimate = TaskSetAnalyzer()._estimate_execution_time(profile, 1, 0.0)
        self.assertIsNone(estimate[0])
        self.assertEqual("UNVERIFIED", estimate[2])

    def test_taskset_uses_board_calibrated_can_send_cpu_cost(self):
        profile = TaskProfile(
            task_name="can_transmit",
            api_usage={"CAN_Send": 1},
            contextual_integer_counts={
                "loop_invocations": 1,
                "loop_iterations": 8,
                "communication_group_loop_invocations": 1,
                "communication_group_loop_iterations": 8,
                "checksum_processed_byte_u32": 8,
            },
            dynamic_bound_verified=True,
        )
        estimate = TaskSetAnalyzer()._estimate_execution_time(profile, 100, 0.0)
        self.assertIsNotNone(estimate[0])
        self.assertEqual("PASS", estimate[2])
        self.assertIn("31.812 us nominal", estimate[4])

    def test_mixed_memory_communication_is_verified_by_independent_holdout(self):
        estimate = estimate_contextual_integer({
            "loop_iterations": 44,
            "loop_invocations": 3,
            "memory_group_loop_iterations": 12,
            "memory_group_loop_invocations": 1,
            "communication_group_loop_iterations": 32,
            "communication_group_loop_invocations": 2,
            "bulk_memory_copy_u32": 12,
            "checksum_processed_byte_u32": 12,
            "switch_case_4_u32": 20,
            "bitwise_xor_u32": 1,
        })
        self.assertTrue(estimate.verified)
        self.assertAlmostEqual(28.7901, estimate.nominal_us, places=3)
        self.assertIn("Validated for the S32K148", estimate.note)

    def test_mixed_shape_inside_calibrated_range_is_verified(self):
        estimate = estimate_contextual_integer({
            "loop_iterations": 80,
            "loop_invocations": 1,
            "mixed_shape_group_loop_iterations": 80,
            "mixed_shape_group_loop_invocations": 1,
            "mixed_indexed_divide_bitwise_u32": 80,
            "mixed_indexed_divide_bitwise_u32_invocations": 1,
        })
        self.assertTrue(estimate.verified)
        self.assertAlmostEqual(108.973585, estimate.nominal_us, places=5)

    def test_mixed_shape_outside_calibrated_range_is_unverified(self):
        estimate = estimate_contextual_integer({
            "loop_iterations": 129,
            "loop_invocations": 1,
            "mixed_shape_group_loop_iterations": 129,
            "mixed_shape_group_loop_invocations": 1,
            "mixed_indexed_divide_bitwise_u32": 129,
            "mixed_indexed_divide_bitwise_u32_invocations": 1,
        })
        self.assertFalse(estimate.verified)
        self.assertIn("outside the validated 16-128", estimate.note)


if __name__ == "__main__": unittest.main()
