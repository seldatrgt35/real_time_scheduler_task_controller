from pathlib import Path
import unittest

from task_admission_framework.analyzer.analyzer import StaticAnalyzer
from task_admission_framework.calibration.contextual_integer_execution import (
    estimate_contextual_integer,
)


class BasicFeatureWcetSuiteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = (
            Path(__file__).parents[1]
            / "task_admission_framework"
            / "examples"
            / "basic_feature_wcet_suite.c"
        )
        cls.profiles = {
            profile.task_name: profile
            for profile in StaticAnalyzer().analyze_file(source)
            if profile.task_name.startswith("StarBasic_")
        }

    def test_all_measurement_points_have_an_estimate(self) -> None:
        self.assertEqual(27, len(self.profiles))
        for task_name, profile in self.profiles.items():
            with self.subTest(task=task_name):
                estimate = estimate_contextual_integer(
                    profile.contextual_integer_counts
                )
                self.assertIsNotNone(estimate.nominal_us)
                self.assertIsNotNone(estimate.safe_us)
                self.assertFalse(estimate.unsupported_features)

    def test_isolated_memory_families_are_not_confused(self) -> None:
        expected = {
            "StarBasic_SequentialMemory": "sequential_memory_u32",
            "StarBasic_RandomMemory": "random_indexed_memory_u32",
            "StarBasic_MemoryCopy": "bulk_memory_copy_u32",
            "StarBasic_MemorySet": "bulk_memory_set_u32",
        }
        for task_name, feature in expected.items():
            with self.subTest(task=task_name):
                counts = self.profiles[task_name].contextual_integer_counts
                self.assertEqual(32, counts[feature])

    def test_branch_limitation_is_explicit(self) -> None:
        estimate = estimate_contextual_integer(
            self.profiles["StarBasic_Branch"].contextual_integer_counts
        )
        self.assertFalse(estimate.verified)
        self.assertIn("failed the independent compound holdout", estimate.note)

    def test_extended_rotate_preserves_adjacent_bitwise_work(self) -> None:
        counts = self.profiles["StarBasic_BitwiseShift"].contextual_integer_counts
        self.assertEqual(1, counts["atomic_region_shape_extended_shift_rotate"])
        self.assertEqual(32, counts["shift_rotate_u32"])
        self.assertEqual(32, counts["bitwise_and_u32"])
        self.assertEqual(32, counts["bitwise_or_u32"])
        self.assertEqual(32, counts["bitwise_xor_u32"])
        estimate = estimate_contextual_integer(counts)
        self.assertFalse(estimate.verified)
        self.assertAlmostEqual(20.6033333344, estimate.nominal_us)
        self.assertLess(abs(estimate.nominal_us - 22.395) / 22.395, 0.09)
        self.assertGreaterEqual(estimate.safe_us, 22.395)

    def test_float_expression_preserves_add_and_multiply(self) -> None:
        counts = self.profiles["StarBasic_FloatingPoint"].contextual_integer_counts
        self.assertEqual(32, counts["float32_add_sub_u32"])
        self.assertEqual(32, counts["float32_multiply_u32"])
        self.assertEqual(1, counts["atomic_region_shape_mixed_floating_operations"])
        estimate = estimate_contextual_integer(counts)
        self.assertFalse(estimate.verified)
        self.assertAlmostEqual(104.0625, estimate.nominal_us)
        self.assertGreaterEqual(estimate.safe_us, 88.791)

    def test_extended_basic_families_are_isolated(self) -> None:
        expected = {
            "StarBasic_MaskedMultiply": "multiply_masked_index_u32",
            "StarBasic_MaskedDivide": "divide_masked_index_u32",
            "StarBasic_MaskedModulo": "modulo_masked_index_u32",
            "StarBasic_BitwiseNested": "bitwise_nested_u32",
            "StarBasic_Checksum": "checksum_processed_byte_u32",
            "StarBasic_Q15Multiply": "q15_multiply_u32",
            "StarBasic_Q31Multiply": "q31_multiply_u32",
            "StarBasic_Q31Mac": "q31_mac_u32",
            "StarBasic_Float32Add": "float32_add_sub_u32",
            "StarBasic_Float32Divide": "float32_divide_u32",
            "StarBasic_Float64Add": "float64_add_sub_u32",
            "StarBasic_Float64Multiply": "float64_multiply_u32",
            "StarBasic_Float64Divide": "float64_divide_u32",
            "StarBasic_IntToFloat": "int32_to_float32_u32",
        }
        for task_name, feature in expected.items():
            with self.subTest(task=task_name):
                self.assertEqual(
                    32, self.profiles[task_name].contextual_integer_counts[feature]
                )

    def test_masked_expressions_preserve_outer_accumulation(self) -> None:
        for task_name in (
            "StarBasic_MaskedMultiply",
            "StarBasic_MaskedDivide",
            "StarBasic_MaskedModulo",
        ):
            with self.subTest(task=task_name):
                counts = self.profiles[task_name].contextual_integer_counts
                self.assertEqual(1, counts["atomic_fallback_region"])
                self.assertEqual(32, counts["basic_add_expression_u32"])
                estimate = estimate_contextual_integer(counts)
                self.assertEqual(
                    task_name != "StarBasic_MaskedMultiply", estimate.verified
                )

    def test_integer_to_float_preserves_float_accumulation(self) -> None:
        counts = self.profiles["StarBasic_IntToFloat"].contextual_integer_counts
        self.assertEqual(32, counts["int32_to_float32_u32"])
        self.assertEqual(32, counts["float32_add_sub_u32"])
        estimate = estimate_contextual_integer(counts)
        self.assertFalse(estimate.verified)
        self.assertAlmostEqual(108.0, estimate.nominal_us)
        self.assertGreaterEqual(estimate.safe_us, 93.770)

    def test_basic_gap_models_pass_unseen_32_iteration_holdouts(self) -> None:
        expected = {
            "StarBasic_Arithmetic": (27.812232558139534, 28.479),
            "StarBasic_MaskedDivide": (20.013267441860467, 21.125),
            "StarBasic_MaskedModulo": (28.642627906976745, 27.375),
        }
        for task_name, (nominal, board_us) in expected.items():
            with self.subTest(task=task_name):
                estimate = estimate_contextual_integer(
                    self.profiles[task_name].contextual_integer_counts
                )
                self.assertTrue(estimate.verified)
                self.assertAlmostEqual(nominal, estimate.nominal_us)
                self.assertLess(abs(nominal - board_us) / board_us, 0.06)
                self.assertGreaterEqual(estimate.safe_us, board_us)
                self.assertAlmostEqual(
                    nominal, sum(estimate.breakdown_us.values())
                )

    def test_basic_memory_models_pass_unseen_32_iteration_holdouts(self) -> None:
        expected = {
            "StarBasic_SequentialMemory": (17.091488372093025, 17.062),
            "StarBasic_RandomMemory": (19.728534883720933, 19.750),
            "StarBasic_MemoryCopy": (18.619441860465116, 18.333),
            "StarBasic_MemorySet": (13.687232558139534, 13.708),
        }
        for task_name, (nominal, board_us) in expected.items():
            with self.subTest(task=task_name):
                estimate = estimate_contextual_integer(
                    self.profiles[task_name].contextual_integer_counts
                )
                self.assertTrue(estimate.verified)
                self.assertAlmostEqual(nominal, estimate.nominal_us)
                self.assertLess(abs(nominal - board_us) / board_us, 0.02)
                self.assertGreaterEqual(estimate.safe_us, board_us)
                self.assertAlmostEqual(
                    nominal, sum(estimate.breakdown_us.values())
                )


if __name__ == "__main__":
    unittest.main()
