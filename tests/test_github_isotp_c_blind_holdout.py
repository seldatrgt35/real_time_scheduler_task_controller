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

    def test_predictions_are_frozen_before_board_measurement(self) -> None:
        expected = {
            "StarTask_IsotpConsecutiveFrameReassembly_10ms": (
                14.506486280699999,
                16.682459222804997,
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
