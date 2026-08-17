from pathlib import Path
import unittest

from task_admission_framework.analyzer.analyzer import StaticAnalyzer


class BasicGapCalibrationTest(unittest.TestCase):
    def test_nine_explicit_calibration_functions_are_analyzable(self) -> None:
        source = (
            Path(__file__).parents[1]
            / "task_admission_framework"
            / "examples"
            / "basic_gap_calibration.c"
        )
        profiles = {
            profile.task_name: profile
            for profile in StaticAnalyzer().analyze_file(source)
            if profile.task_name.startswith("StarGap_")
            and profile.task_name != "StarGap_Initialize"
        }
        self.assertEqual(9, len(profiles))
        for family in ("Arithmetic", "MaskedDivide", "MaskedModulo"):
            for iterations in (8, 16, 64):
                with self.subTest(family=family, iterations=iterations):
                    counts = profiles[
                        f"StarGap_{family}{iterations}"
                    ].contextual_integer_counts
                    self.assertEqual(iterations, counts["loop_iterations"])
                    self.assertTrue(counts)


if __name__ == "__main__":
    unittest.main()
