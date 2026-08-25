from pathlib import Path
import unittest

from task_admission_framework.analyzer.analyzer import StaticAnalyzer
from task_admission_framework.calibration.contextual_integer_execution import (
    estimate_contextual_integer,
)


class BodyChassisWcetTest(unittest.TestCase):
    def test_three_holdout_predictions_are_frozen(self) -> None:
        source = (
            Path(__file__).parents[1]
            / "task_admission_framework"
            / "examples"
            / "body_chassis_control_holdout.c"
        )
        profiles = {
            item.task_name: item for item in StaticAnalyzer().analyze_file(source)
        }
        expected = {
            "BccTask_WheelSpeedAndBrake_5ms": (28.812, 33.1338),
            "BccTask_ThermalActuator_10ms": (22.288392857142856, 25.631651785714283),
            "BccTask_StabilityRequest_20ms": (33.958, 39.0517),
        }
        for task, (nominal_us, wcet_us) in expected.items():
            with self.subTest(task=task):
                estimate = estimate_contextual_integer(
                    profiles[task].contextual_integer_counts
                )
                self.assertAlmostEqual(nominal_us, estimate.nominal_us)
                self.assertAlmostEqual(wcet_us, estimate.safe_us)

    def test_frozen_wcet_covers_all_board_maxima(self) -> None:
        board_maxima_us = (29.020, 23.020, 34.791)
        frozen_wcet_us = (33.1338, 25.6316517857, 39.0517)
        for task_id, (measured, wcet) in enumerate(
            zip(board_maxima_us, frozen_wcet_us)
        ):
            with self.subTest(task_id=task_id):
                self.assertGreaterEqual(wcet, measured)


if __name__ == "__main__":
    unittest.main()
