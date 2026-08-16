import unittest
from pathlib import Path

from task_admission_framework.analyzer.analyzer import StaticAnalyzer
from task_admission_framework.calibration.contextual_integer_execution import (
    estimate_contextual_integer,
)


class MisraAutomotiveComplexTaskTest(unittest.TestCase):
    def test_all_calibrated_feature_groups_are_extracted(self) -> None:
        source = (
            Path(__file__).parents[1]
            / "task_admission_framework"
            / "examples"
            / "misra_automotive_complex_task.c"
        )
        profiles = StaticAnalyzer().analyze_file(source)
        profile = next(
            item
            for item in profiles
            if item.task_name == "StarTask_20ms_MisraAutomotiveComplex"
        )
        counts = profile.contextual_integer_counts

        expected = {
            "dense_integer_control_correction_u32",
            "sequential_memory_u32",
            "random_indexed_memory_u32",
            "bulk_memory_copy_u32",
            "bulk_memory_set_u32",
            "q31_mac_u32",
            "float32_multiply_u32",
            "checksum_processed_byte_u32",
            "component_callback_empty_u32",
            "component_callback_rotate_body_u32",
            "switch_case_4_u32",
        }
        self.assertTrue(expected.issubset(counts))
        self.assertTrue(profile.dynamic_bound_verified)

        estimate = estimate_contextual_integer(counts)
        # Isolated component costs are numerically available, but a realistic
        # compound holdout did not satisfy the admission margin.  Keep the
        # estimate visible while withholding an acceptance decision.
        self.assertFalse(estimate.verified)
        self.assertIn("compound holdout", estimate.note)
        self.assertAlmostEqual(387.931, estimate.nominal_us, places=3)
        self.assertAlmostEqual(446.121, estimate.safe_us, places=3)


if __name__ == "__main__":
    unittest.main()
