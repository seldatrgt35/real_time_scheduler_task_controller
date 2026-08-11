from pathlib import Path
import unittest

from task_admission_framework.analyzer.analyzer import StaticAnalyzer
from task_admission_framework.calibration.contextual_integer_execution import estimate_contextual_integer


class PowertrainCpuTasksTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).parents[1] / "task_admission_framework" / "examples" / "powertrain_cpu_tasks.c"
        cls.profiles = {profile.task_name: profile for profile in StaticAnalyzer().analyze_file(source)}

    def test_three_powertrain_tasks_use_verified_numeric_groups(self):
        expected = {
            "PowertrainFastControlTask_5ms": (114.734, 88),
            "PowertrainSensorTask_10ms": (116.296, 80),
            "PowertrainTorqueSafetyTask_20ms": (117.081, 104),
        }
        for name, (nominal_us, iterations) in expected.items():
            counts = self.profiles[name].contextual_integer_counts
            estimate = estimate_contextual_integer(counts)
            self.assertEqual(iterations, counts["powertrain_group_loop_iterations"])
            self.assertTrue(estimate.verified)
            self.assertAlmostEqual(nominal_us, estimate.nominal_us, places=3)


if __name__ == "__main__":
    unittest.main()
