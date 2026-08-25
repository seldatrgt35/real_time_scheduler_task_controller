from pathlib import Path
import unittest

from task_admission_framework.analyzer.analyzer import StaticAnalyzer
from task_admission_framework.calibration.contextual_integer_execution import (
    estimate_contextual_integer,
)


class NestedLoopAutomotiveWcetTest(unittest.TestCase):
    def test_nested_bounds_and_prediction_are_frozen(self) -> None:
        source = (
            Path(__file__).parents[1]
            / "task_admission_framework"
            / "examples"
            / "nested_loop_automotive_holdout.c"
        )
        profile = next(
            item for item in StaticAnalyzer().analyze_file(source)
            if item.task_name == "NestedLoopAutomotive_SensorMatrixTask_10ms"
        )
        counts = profile.contextual_integer_counts
        self.assertEqual(40, counts["loop_iterations"])
        self.assertEqual(9, counts["loop_invocations"])
        self.assertEqual(32, counts["sequential_memory_u32"])
        estimate = estimate_contextual_integer(counts)
        self.assertAlmostEqual(33.70857679599071, estimate.nominal_us)
        self.assertAlmostEqual(38.76486331538931, estimate.safe_us)


if __name__ == "__main__":
    unittest.main()
