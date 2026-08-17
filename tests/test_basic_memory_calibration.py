from pathlib import Path
import unittest

from task_admission_framework.analyzer.analyzer import StaticAnalyzer


class BasicMemoryCalibrationTest(unittest.TestCase):
    def test_twelve_memory_training_points_are_isolated(self) -> None:
        source = (
            Path(__file__).parents[1]
            / "task_admission_framework"
            / "examples"
            / "basic_memory_calibration.c"
        )
        profiles = {
            profile.task_name: profile
            for profile in StaticAnalyzer().analyze_file(source)
            if profile.task_name.startswith("StarMemory_")
            and profile.task_name != "StarMemory_Initialize"
        }
        expected = {
            "Sequential": "sequential_memory_u32",
            "Random": "random_indexed_memory_u32",
            "Copy": "bulk_memory_copy_u32",
            "Set": "bulk_memory_set_u32",
        }
        self.assertEqual(12, len(profiles))
        for family, feature in expected.items():
            for iterations in (8, 16, 64):
                with self.subTest(family=family, iterations=iterations):
                    counts = profiles[
                        f"StarMemory_{family}{iterations}"
                    ].contextual_integer_counts
                    self.assertEqual(iterations, counts[feature])


if __name__ == "__main__":
    unittest.main()
