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

    def test_mixed_memory_regions_preserve_their_operations(self) -> None:
        expected = {
            "StarTask_UdsAddressLengthDecode_20ms": {
                "sequential_memory_u32": 6,
                "shift_left_u32": 6,
                "multiply_local_u32": 6,
                "bitwise_or_u32": 6,
            },
            "StarTask_UdsTransferDataBlock_5ms": {
                "bulk_memory_copy_u32": 32,
                "atomic_region_array_access": 64,
                "basic_add_expression_u32": 32,
            },
            "StarTask_UdsSecurityKeyValidate_20ms": {
                "sequential_memory_u32": 16,
                "bitwise_xor_u32": 16,
                "bitwise_or_u32": 16,
            },
        }
        for task, feature_counts in expected.items():
            with self.subTest(task=task):
                counts = self.profiles[task].contextual_integer_counts
                self.assertEqual(1 if "TransferData" in task or "Security" in task else 2,
                                 counts["atomic_fallback_region"])
                for feature, count in feature_counts.items():
                    self.assertEqual(count, counts[feature])
                self.assertFalse(estimate_contextual_integer(counts).verified)

    def test_read_did_mixed_memory_shape_remains_unsupported(self) -> None:
        estimate = estimate_contextual_integer(self.profiles["StarTask_UdsReadDidPack_10ms"].contextual_integer_counts)
        self.assertFalse(estimate.verified)
        self.assertIsNone(estimate.nominal_us)
        self.assertIsNone(estimate.safe_us)
        self.assertIn("unsupported_mixed_execution_region", estimate.unsupported_features)

    def test_transfer_data_board_holdout_is_now_covered(self) -> None:
        estimate = estimate_contextual_integer(
            self.profiles["StarTask_UdsTransferDataBlock_5ms"].contextual_integer_counts
        )
        self.assertAlmostEqual(27.517529177331586, estimate.nominal_us)
        self.assertLess(abs(estimate.nominal_us - 28.562) / 28.562, 0.04)
        self.assertGreaterEqual(estimate.safe_us, 28.562)


if __name__ == "__main__":
    unittest.main()
