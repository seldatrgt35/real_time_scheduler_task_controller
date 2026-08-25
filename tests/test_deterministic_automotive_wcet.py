from pathlib import Path
import unittest

from task_admission_framework.analyzer.analyzer import StaticAnalyzer
from task_admission_framework.calibration.contextual_integer_execution import (
    estimate_contextual_integer,
)


class DeterministicAutomotiveWcetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = (
            Path(__file__).parents[1]
            / "task_admission_framework"
            / "examples"
            / "deterministic_automotive_task.c"
        )
        cls.profile = next(
            item for item in StaticAnalyzer().analyze_file(source)
            if item.task_name == "StarAutomotiveTask_10ms"
        )

    def test_complete_task_retains_supported_automotive_features(self) -> None:
        counts = self.profile.contextual_integer_counts
        self.assertEqual(64, counts["loop_iterations"])
        self.assertEqual(16, counts["sequential_memory_u32"])
        self.assertEqual(16, counts["component_branch_bitwise_u32"])
        self.assertEqual(16, counts["powertrain_linear_interpolation_i32"])
        self.assertEqual(16, counts["int32_to_float32_u32"])
        self.assertEqual(16, counts["float32_add_sub_u32"])
        self.assertEqual(16, counts["float32_multiply_u32"])
        self.assertEqual(16, counts["mixed_region_direct_call"])
        self.assertEqual(32, counts["mixed_region_array_access"])
        self.assertEqual(3, counts["bitwise_and_u32"])
        self.assertNotIn("unsupported_mixed_execution_region", counts)

    def test_corrected_prediction_covers_frozen_board_measurement(self) -> None:
        estimate = estimate_contextual_integer(self.profile.contextual_integer_counts)
        self.assertAlmostEqual(124.73730773119534, estimate.nominal_us)
        self.assertAlmostEqual(143.44790389087464, estimate.safe_us)
        self.assertGreaterEqual(estimate.safe_us, 134.166)


if __name__ == "__main__":
    unittest.main()
