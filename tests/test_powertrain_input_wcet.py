from pathlib import Path
import unittest

from task_admission_framework.analyzer.analyzer import StaticAnalyzer
from task_admission_framework.calibration.contextual_integer_execution import (
    estimate_contextual_integer,
)


class PowertrainInputWcetTest(unittest.TestCase):
    BOARD_MAX_US = 16.500

    def test_frozen_wcet(self) -> None:
        source = (
            Path(__file__).parents[1]
            / "task_admission_framework"
            / "examples"
            / "automotive_feature_reference.c"
        )
        profile = next(
            item for item in StaticAnalyzer().analyze_file(source)
            if item.task_name == "AppTask_PowertrainInput_5ms"
        )
        estimate = estimate_contextual_integer(profile.contextual_integer_counts)
        self.assertAlmostEqual(19.812, estimate.nominal_us)
        self.assertAlmostEqual(22.7838, estimate.safe_us)

    def test_frozen_wcet_covers_board_maximum(self) -> None:
        frozen_nominal_us = 19.812
        frozen_wcet_us = 22.7838
        nominal_error = abs(frozen_nominal_us - self.BOARD_MAX_US) / self.BOARD_MAX_US

        self.assertGreaterEqual(frozen_wcet_us, self.BOARD_MAX_US)
        self.assertLess(nominal_error, 0.21)


if __name__ == "__main__":
    unittest.main()
