from pathlib import Path
import re
import unittest

from task_admission_framework.analyzer.analyzer import StaticAnalyzer
from task_admission_framework.calibration.contextual_integer_execution import (
    estimate_contextual_integer,
)


class ConditionalMemoryWriteCalibrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        examples = (
            Path(__file__).parents[1]
            / "task_admission_framework"
            / "examples"
        )
        cls.kernel_source = (
            examples / "conditional_memory_write_calibration.c"
        ).read_text(encoding="utf-8")
        cls.harness_source = (
            examples / "s32k148_conditional_memory_write_calibration_main.c"
        ).read_text(encoding="utf-8")
        cls.profiles = {
            profile.task_name: profile
            for profile in StaticAnalyzer().analyze_file(
                examples / "conditional_memory_write_calibration.c"
            )
        }

    def test_training_source_does_not_import_holdouts(self) -> None:
        self.assertNotRegex(
            self.kernel_source,
            r'#include\s+"(?:github_isotp_c_blind|body_chassis_control)_holdout',
        )

    def test_frame_stride_matches_holdout_power_of_two_layout(self) -> None:
        self.assertIn("uint8_t payload[5U];", self.kernel_source)

    def test_matrix_has_three_write_counts_and_three_iteration_counts(self) -> None:
        descriptors = re.findall(
            r"\{ConditionalMemoryWriteCalibration_Write(\d+)_(\d+),"
            r"\s*(\d+)U,\s*(\d+)U\}",
            self.harness_source,
        )
        self.assertEqual(9, len(descriptors))
        observed = {
            (int(name_writes), int(name_iterations))
            for name_writes, name_iterations, field_writes, field_iterations
            in descriptors
            if name_writes == field_writes
            and name_iterations == field_iterations
        }
        self.assertEqual(
            {(writes, iterations) for writes in (1, 2, 4)
             for iterations in (8, 16, 32)},
            observed,
        )

    def test_only_debugger_interface_uses_external_g_prefix(self) -> None:
        self.assertNotRegex(self.kernel_source, r"\bg_[A-Za-z0-9_]+")
        exported = set(re.findall(r"\bg_star_[A-Za-z0-9_]+", self.harness_source))
        self.assertEqual(
            {
                "g_star_conditional_memory_write_complete",
                "g_star_conditional_memory_write_current",
                "g_star_conditional_memory_write_results",
            },
            exported,
        )

    def test_final_fit_covers_all_nine_training_points(self) -> None:
        board_us = {
            (1, 8): 15.770,
            (1, 16): 30.083,
            (1, 32): 58.750,
            (2, 8): 19.437,
            (2, 16): 37.437,
            (2, 32): 73.437,
            (4, 8): 25.958,
            (4, 16): 50.458,
            (4, 32): 99.479,
        }
        for (writes, iterations), measured_us in board_us.items():
            with self.subTest(writes=writes, iterations=iterations):
                task_name = (
                    "ConditionalMemoryWriteCalibration_"
                    f"Write{writes}_{iterations}"
                )
                estimate = estimate_contextual_integer(
                    self.profiles[task_name].contextual_integer_counts
                )
                self.assertFalse(estimate.verified)
                self.assertLess(
                    abs(estimate.nominal_us - measured_us) / measured_us,
                    0.01,
                )


if __name__ == "__main__":
    unittest.main()
