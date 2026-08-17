from pathlib import Path
import unittest

from task_admission_framework.analyzer.analyzer import StaticAnalyzer
from task_admission_framework.calibration.contextual_integer_execution import (
    estimate_contextual_integer,
)


class Iso14229RealAutomotiveBlindSuiteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = Path(__file__).parents[1] / "task_admission_framework" / "examples" / "iso14229_real_automotive_blind_suite.c"
        cls.profiles = {p.task_name: p for p in StaticAnalyzer().analyze_file(source)}

    def test_predictions_are_frozen_before_board(self) -> None:
        expected = {
            "StarTask_UdsAddressLengthDecode_20ms": (14.848847899198256, 17.076175084077995, True),
            "StarTask_UdsTransferDataBlock_5ms": (14.7075000011, 16.913625001264997, True),
            "StarTask_UdsSecurityKeyValidate_20ms": (20.101307731195355, 23.116503890874657, True),
        }
        for task, (nominal, safe, verified) in expected.items():
            with self.subTest(task=task):
                estimate = estimate_contextual_integer(self.profiles[task].contextual_integer_counts)
                self.assertAlmostEqual(nominal, estimate.nominal_us)
                self.assertAlmostEqual(safe, estimate.safe_us)
                self.assertEqual(verified, estimate.verified)

    def test_new_read_did_shape_is_not_given_a_partial_estimate(self) -> None:
        estimate = estimate_contextual_integer(self.profiles["StarTask_UdsReadDidPack_10ms"].contextual_integer_counts)
        self.assertFalse(estimate.verified)
        self.assertIsNone(estimate.nominal_us)
        self.assertIsNone(estimate.safe_us)
        self.assertIn("unsupported_mixed_execution_region", estimate.unsupported_features)


if __name__ == "__main__":
    unittest.main()
