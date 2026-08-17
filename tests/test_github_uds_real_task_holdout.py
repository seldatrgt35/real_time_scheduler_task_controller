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

    def test_predictions_are_frozen_before_board_measurement(self) -> None:
        expected = {
            "StarTask_ObdPidDecode_10ms": (
                False, 11.06675, 12.7267625
            ),
            "StarTask_UdsResponseValidation_20ms": (
                False, 9.9142896343, 11.401433079444999
            ),
        }
        for task_name, (verified, nominal, safe) in expected.items():
            with self.subTest(task=task_name):
                estimate = estimate_contextual_integer(
                    self.profiles[task_name].contextual_integer_counts
                )
                self.assertEqual(verified, estimate.verified)
                self.assertAlmostEqual(nominal, estimate.nominal_us)
                self.assertAlmostEqual(safe, estimate.safe_us)

    def test_unsupported_real_mixed_task_has_no_partial_estimate(self) -> None:
        expected_shapes = {
            "StarTask_UdsCanRxDispatch_5ms": "conditional_memory",
            "StarTask_DtcAndSessionMaintenance_50ms": "debounce_state",
            "StarTask_ObdRequestAndCanTx_100ms": None,
        }
        for task_name, shape in expected_shapes.items():
            with self.subTest(task=task_name):
                profile = self.profiles[task_name]
                counts = profile.contextual_integer_counts
                self.assertFalse(profile.dynamic_bound_verified)
                self.assertEqual(1, counts["unsupported_mixed_execution_region"])
                if shape is not None:
                    self.assertEqual(1, counts[f"mixed_region_shape_{shape}"])
                    self.assertGreater(counts.get("mixed_region_branch", 0), 0)
                self.assertGreater(counts["mixed_region_array_access"], 0)
                estimate = estimate_contextual_integer(counts)
                self.assertFalse(estimate.verified)
                self.assertIsNone(estimate.nominal_us)
                self.assertIsNone(estimate.safe_us)


if __name__ == "__main__":
    unittest.main()
