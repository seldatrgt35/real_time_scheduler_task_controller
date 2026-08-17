from pathlib import Path
import unittest

from task_admission_framework.analyzer.analyzer import StaticAnalyzer
from task_admission_framework.calibration.contextual_integer_execution import (
    estimate_contextual_integer,
)


class GithubIsotpCBlindHoldoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = (
            Path(__file__).parents[1]
            / "task_admission_framework"
            / "examples"
            / "github_isotp_c_blind_holdout.c"
        )
        cls.profiles = {
            item.task_name: item for item in StaticAnalyzer().analyze_file(source)
        }

    def test_current_predictions_preserve_frozen_blind_comparison(self) -> None:
        expected = {
            "StarTask_IsotpConsecutiveFrameReassembly_10ms": (
                38.29452891156463,
                44.03870824829932,
            ),
            "StarTask_IsotpErrorAging_20ms": (
                28.2699999984,
                32.51049999816,
            ),
        }

        for task_name, (nominal_us, safe_us) in expected.items():
            with self.subTest(task=task_name):
                profile = self.profiles[task_name]
                estimate = estimate_contextual_integer(
                    profile.contextual_integer_counts
                )
                self.assertTrue(profile.dynamic_bound_verified)
                self.assertFalse(estimate.verified)
                self.assertAlmostEqual(nominal_us, estimate.nominal_us)
                self.assertAlmostEqual(safe_us, estimate.safe_us)

    def test_reassembly_no_longer_uses_incomplete_mixed_shape(self) -> None:
        counts = self.profiles[
            "StarTask_IsotpConsecutiveFrameReassembly_10ms"
        ].contextual_integer_counts
        self.assertNotIn("mixed_memory_branch_update_u32", counts)
        self.assertEqual(1, counts["atomic_fallback_region"])
        self.assertEqual(36, counts["branch_evaluation_u32"])
        self.assertEqual(60, counts["basic_add_expression_u32"])
        self.assertEqual(48, counts["atomic_region_conditional_array_write"])
        estimate = estimate_contextual_integer(counts)
        self.assertFalse(estimate.verified)
        self.assertLess(
            abs(estimate.nominal_us - 37.645) / 37.645,
            0.03,
        )

    def test_error_aging_exercises_atomic_fallback(self) -> None:
        counts = self.profiles[
            "StarTask_IsotpErrorAging_20ms"
        ].contextual_integer_counts
        self.assertEqual(1, counts["atomic_fallback_region"])
        self.assertEqual(1, counts["atomic_region_shape_debounce_state"])
        self.assertGreater(counts["branch_evaluation_u32"], 0)
        self.assertGreater(counts["bitwise_and_u32"], 0)
        self.assertGreater(counts["shift_left_u32"], 0)


if __name__ == "__main__":
    unittest.main()
