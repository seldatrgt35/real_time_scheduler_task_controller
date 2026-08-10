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


if __name__ == "__main__": unittest.main()
