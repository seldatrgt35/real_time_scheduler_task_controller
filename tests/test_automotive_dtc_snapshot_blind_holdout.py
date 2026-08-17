from pathlib import Path
import unittest

from task_admission_framework.analyzer.analyzer import StaticAnalyzer
from task_admission_framework.calibration.contextual_integer_execution import (
    estimate_contextual_integer,
)


class AutomotiveDtcSnapshotBlindHoldoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = (
            Path(__file__).parents[1]
            / "task_admission_framework"
            / "examples"
            / "automotive_dtc_snapshot_blind_holdout.c"
        )
        cls.source_text = source.read_text(encoding="utf-8")
        cls.profile = {
            item.task_name: item for item in StaticAnalyzer().analyze_file(source)
        }["StarTask_DtcSnapshotPack_20ms"]

    def test_holdout_is_explicitly_excluded_from_training(self) -> None:
        self.assertIn("validation-only", self.source_text)
        self.assertIn(
            "never be used to fit execution-time coefficients",
            self.source_text,
        )

    def test_feature_description_is_frozen_before_board(self) -> None:
        counts = self.profile.contextual_integer_counts
        self.assertTrue(self.profile.dynamic_bound_verified)
        self.assertEqual(1, counts["atomic_fallback_region"])
        self.assertEqual(16, counts["atomic_region_bounded_iterations"])
        self.assertEqual(48, counts["branch_evaluation_u32"])
        self.assertEqual(64, counts["atomic_region_conditional_array_write"])
        self.assertEqual(32, counts["shift_right_u32"])

    def test_prediction_is_frozen_before_board(self) -> None:
        estimate = estimate_contextual_integer(
            self.profile.contextual_integer_counts
        )
        self.assertFalse(estimate.verified)
        self.assertAlmostEqual(40.67722685005926, estimate.nominal_us)
        self.assertAlmostEqual(46.77881087756815, estimate.safe_us)

    def test_sparse_board_result_exposes_path_occupancy_mismatch(self) -> None:
        board_us = 17.479
        estimate = estimate_contextual_integer(
            self.profile.contextual_integer_counts
        )
        self.assertGreater(
            abs(estimate.nominal_us - board_us) / board_us,
            1.0,
        )
        self.assertGreaterEqual(estimate.safe_us, board_us)


if __name__ == "__main__":
    unittest.main()
