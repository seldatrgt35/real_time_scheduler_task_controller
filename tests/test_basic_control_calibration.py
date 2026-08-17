from pathlib import Path
import unittest

from task_admission_framework.analyzer.analyzer import StaticAnalyzer


class BasicControlCalibrationTest(unittest.TestCase):
    def test_twelve_control_training_points_are_analyzable(self) -> None:
        source = (
            Path(__file__).parents[1]
            / "task_admission_framework"
            / "examples"
            / "basic_control_calibration.c"
        )
        profiles = {
            profile.task_name: profile
            for profile in StaticAnalyzer().analyze_file(source)
            if profile.task_name.startswith("StarControl_")
            and profile.task_name != "StarControl_Initialize"
        }
        expected = {
            "Branch": "component_branch_bitwise_u32",
            "Callback": "mixed_region_callback_i32",
            "Switch": "switch_case_4_u32",
            "Checksum": "checksum_processed_byte_u32",
        }
        self.assertEqual(12, len(profiles))
        for family, feature in expected.items():
            for iterations in (8, 16, 64):
                with self.subTest(family=family, iterations=iterations):
                    counts = profiles[
                        f"StarControl_{family}{iterations}"
                    ].contextual_integer_counts
                    self.assertEqual(iterations, counts[feature])


if __name__ == "__main__":
    unittest.main()
