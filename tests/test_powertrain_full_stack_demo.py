from pathlib import Path
import unittest

from task_admission_framework.analyzer.analyzer import StaticAnalyzer
from task_admission_framework.calibration.contextual_integer_execution import (
    estimate_contextual_integer,
)


class PowertrainFullStackDemoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (
            Path(__file__).parents[1]
            / "task_admission_framework"
            / "examples"
            / "powertrain_full_stack_demo.c"
        )
        cls.profiles = {
            profile.task_name: profile
            for profile in StaticAnalyzer().analyze_file(source)
        }

    def test_compound_holdout_predictions_are_stable(self):
        expected = {
            "StarTask_TorqueLimiterAndTraction_20ms": 27.833,
            "StarTask_DiagnosticsAndPlausibility_50ms": 22.437,
            "StarTask_CanObdAndNetworkManagement_100ms": 44.463,
        }
        for function, nominal_us in expected.items():
            estimate = estimate_contextual_integer(
                self.profiles[function].contextual_integer_counts
            )
            self.assertTrue(estimate.verified)
            self.assertAlmostEqual(nominal_us, estimate.nominal_us, places=3)


if __name__ == "__main__":
    unittest.main()
