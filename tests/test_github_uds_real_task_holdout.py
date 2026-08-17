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
            "StarTask_UdsCanRxDispatch_5ms": (
                True, 15.051369627657897, 17.30907507180658
            ),
            "StarTask_ObdPidDecode_10ms": (
                False, 11.06675, 12.7267625
            ),
            "StarTask_UdsResponseValidation_20ms": (
                False, 9.9142896343, 11.401433079444999
            ),
            "StarTask_DtcAndSessionMaintenance_50ms": (
                True, 22.4367857144, 25.802303571559996
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
