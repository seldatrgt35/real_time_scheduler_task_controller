from pathlib import Path
import unittest

from task_admission_framework.analyzer.analyzer import StaticAnalyzer
from task_admission_framework.calibration.contextual_integer_execution import (
    estimate_contextual_integer,
)


class TorqueCoordinationWcetTest(unittest.TestCase):
    def test_frozen_wcet(self) -> None:
        source = (
            Path(__file__).parents[1]
            / "task_admission_framework"
            / "examples"
            / "automotive_feature_reference.c"
        )
        profile = next(
            item for item in StaticAnalyzer().analyze_file(source)
            if item.task_name == "AppTask_TorqueCoordination_20ms"
        )
        estimate = estimate_contextual_integer(profile.contextual_integer_counts)
        self.assertAlmostEqual(48.937, estimate.nominal_us)
        self.assertAlmostEqual(56.27755, estimate.safe_us)


if __name__ == "__main__":
    unittest.main()
