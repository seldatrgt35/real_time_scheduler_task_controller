from pathlib import Path
import re
import unittest


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

    def test_training_source_does_not_import_holdouts(self) -> None:
        self.assertNotRegex(
            self.kernel_source,
            r'#include\s+"(?:github_isotp_c_blind|body_chassis_control)_holdout',
        )

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


if __name__ == "__main__":
    unittest.main()
