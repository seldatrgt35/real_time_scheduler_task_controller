from pathlib import Path
import unittest

from task_admission_framework.analyzer.analyzer import StaticAnalyzer
from task_admission_framework.calibration.contextual_integer_execution import (
    estimate_contextual_integer,
)


class GithubUdsRealTaskHoldoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = (
            Path(__file__).parents[1]
            / "task_admission_framework"
            / "examples"
            / "github_uds_ecu_blind_holdout.c"
        )
        cls.profiles = {
            item.task_name: item for item in StaticAnalyzer().analyze_file(source)
        }

    def test_unaffected_prediction_remains_stable(self) -> None:
        estimate = estimate_contextual_integer(
            self.profiles[
                "StarTask_ObdPidDecode_10ms"
            ].contextual_integer_counts
        )
        self.assertFalse(estimate.verified)
        self.assertAlmostEqual(11.06675, estimate.nominal_us)
        self.assertAlmostEqual(12.7267625, estimate.safe_us)

    def test_response_validation_rejects_incomplete_mixed_shape(self) -> None:
        profile = self.profiles["StarTask_UdsResponseValidation_20ms"]
        counts = profile.contextual_integer_counts
        self.assertNotIn("mixed_memory_branch_update_u32", counts)
        self.assertEqual(1, counts["atomic_fallback_region"])
        estimate = estimate_contextual_integer(counts)
        self.assertFalse(estimate.verified)
        self.assertAlmostEqual(16.6033333328, estimate.nominal_us)
        self.assertAlmostEqual(19.09383333272, estimate.safe_us)
        self.assertGreaterEqual(estimate.safe_us, 12.625)

    def test_atomic_fallback_repairs_first_match_estimates(self) -> None:
        expected = {
            "StarTask_UdsCanRxDispatch_5ms": (
                "conditional_memory", 25.34700797474832, 26.145
            ),
            "StarTask_DtcAndSessionMaintenance_50ms": (
                "debounce_state", 14.2699999992, 14.770
            ),
        }
        for task_name, (shape, nominal, board_us) in expected.items():
            with self.subTest(task=task_name):
                profile = self.profiles[task_name]
                counts = profile.contextual_integer_counts
                self.assertTrue(profile.dynamic_bound_verified)
                self.assertEqual(1, counts["atomic_fallback_region"])
                self.assertEqual(1, counts[f"atomic_region_shape_{shape}"])
                self.assertGreater(counts["atomic_region_array_access"], 0)
                self.assertGreater(counts["atomic_region_branch"], 0)
                estimate = estimate_contextual_integer(counts)
                self.assertFalse(estimate.verified)
                self.assertAlmostEqual(nominal, estimate.nominal_us)
                self.assertGreaterEqual(estimate.safe_us, board_us)
                if shape == "conditional_memory":
                    self.assertEqual(
                        32,
                        counts["atomic_region_conditional_array_write"],
                    )
                    self.assertLess(
                        abs(estimate.nominal_us - board_us) / board_us,
                        0.04,
                    )

    def test_unsupported_real_mixed_task_has_no_partial_estimate(self) -> None:
        profile = self.profiles["StarTask_ObdRequestAndCanTx_100ms"]
        counts = profile.contextual_integer_counts
        self.assertFalse(profile.dynamic_bound_verified)
        self.assertEqual(1, counts["unsupported_mixed_execution_region"])
        estimate = estimate_contextual_integer(counts)
        self.assertFalse(estimate.verified)
        self.assertIsNone(estimate.nominal_us)
        self.assertIsNone(estimate.safe_us)


if __name__ == "__main__":
    unittest.main()
