from pathlib import Path
import unittest

from task_admission_framework.analyzer.analyzer import StaticAnalyzer
from task_admission_framework.calibration.contextual_integer_execution import (
    estimate_contextual_integer,
)


class MixedIntegerFloatCalibrationTest(unittest.TestCase):
    def test_nine_explicit_measurement_functions_preserve_both_domains(self) -> None:
        source = (
            Path(__file__).parents[1]
            / "task_admission_framework"
            / "examples"
            / "mixed_integer_float_calibration.c"
        )
        profiles = {
            item.task_name: item.contextual_integer_counts
            for item in StaticAnalyzer().analyze_file(source)
            if item.task_name != "StarMixedIntegerFloat_Initialize"
        }
        self.assertEqual(9, len(profiles))
        for family in ("Add", "Multiply", "Memory"):
            for iterations in (8, 16, 32):
                counts = profiles[f"StarMixedIntegerFloat_{family}{iterations}"]
                self.assertEqual(iterations, counts["loop_iterations"])
                self.assertGreater(counts.get("float32_add_sub_u32", 0), 0)
                if family == "Add":
                    self.assertEqual(iterations, counts["add_local_u32"])
                elif family == "Multiply":
                    self.assertEqual(iterations, counts["multiply_local_u32"])
                else:
                    self.assertEqual(iterations, counts["add_memory_u32"])

    def test_fitted_models_cover_all_nine_board_points(self) -> None:
        source = (
            Path(__file__).parents[1]
            / "task_admission_framework"
            / "examples"
            / "mixed_integer_float_calibration.c"
        )
        profiles = {
            item.task_name: item.contextual_integer_counts
            for item in StaticAnalyzer().analyze_file(source)
        }
        measured_us = {
            "Add8": 24.854, "Add16": 48.729, "Add32": 94.104,
            "Multiply8": 34.291, "Multiply16": 67.333,
            "Multiply32": 134.083,
            "Memory8": 35.166, "Memory16": 67.937,
            "Memory32": 136.062,
        }
        for suffix, board_max_us in measured_us.items():
            with self.subTest(suffix=suffix):
                estimate = estimate_contextual_integer(
                    profiles[f"StarMixedIntegerFloat_{suffix}"]
                )
                self.assertGreaterEqual(estimate.safe_us, board_max_us)

    def test_calibration_source_does_not_import_real_task_holdouts(self) -> None:
        source = (
            Path(__file__).parents[1]
            / "task_admission_framework"
            / "examples"
            / "mixed_integer_float_calibration.c"
        ).read_text(encoding="utf-8")
        self.assertNotIn("deterministic_automotive_task", source)
        self.assertNotIn("body_chassis_control_holdout", source)


if __name__ == "__main__":
    unittest.main()
