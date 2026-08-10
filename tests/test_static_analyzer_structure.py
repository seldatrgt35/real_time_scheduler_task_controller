"""Structural-analysis regression tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from task_admission_framework.feature.feature_extractor import FeatureExtractor

try:
    from task_admission_framework.analyzer.analyzer import StaticAnalyzer
except ModuleNotFoundError as exc:
    if exc.name != "clang":
        raise
    StaticAnalyzer = None


class StaticAnalyzerStructureTests(unittest.TestCase):
    def setUp(self) -> None:
        if StaticAnalyzer is None:
            self.skipTest("clang Python bindings are not installed")

    def test_repeated_calls_count_call_sites_but_helper_body_once(self) -> None:
        source = """
        static int helper(int *value)
        {
            if (*value > 0) {
                *value += 1;
            }
            return *value;
        }

        void task(void)
        {
            int value = 1;
            helper(&value);
            helper(&value);
        }
        """
        profile = self._profile(source, "task")
        features = FeatureExtractor().extract(profile)

        self.assertEqual(["task", "helper"], profile.reachable_functions)
        self.assertEqual(["helper"], profile.call_graph["task"])
        self.assertEqual(2, features.total_function_calls)
        self.assertEqual(1, features.total_branches)
        self.assertEqual(1, features.total_returns)

    def test_float_operations_are_counted_as_operations(self) -> None:
        source = """
        float task(float a, float b, float c)
        {
            return a * b + c;
        }
        """
        profile = self._profile(source, "task")
        features = FeatureExtractor().extract(profile)

        self.assertEqual(2, features.floating_point_operations)

    def test_bounded_loop_workload_is_inferred_automatically(self) -> None:
        source = """
        static int fixed_filter_step(int sample, int gain)
        {
            return (sample * gain) >> 8;
        }

        void task(void)
        {
            int output = 0;
            for (int i = 0; i < 10; ++i) {
                output += fixed_filter_step(i, 7);
            }
        }
        """
        profile = self._profile(source, "task")

        self.assertTrue(profile.dynamic_bound_verified)
        self.assertEqual(
            {"fixed_point_filter": 10},
            profile.inferred_workload_counts,
        )

    def test_data_dependent_loop_makes_execution_unverified(self) -> None:
        source = """
        void task(volatile int *ready)
        {
            while (*ready == 0) {
            }
        }
        """
        profile = self._profile(source, "task")

        self.assertFalse(profile.dynamic_bound_verified)
        self.assertEqual({}, profile.inferred_workload_counts)
        self.assertIn("no statically proven bound", profile.dynamic_bound_notes[0])

    def test_constant_call_argument_proves_helper_loop_bound(self) -> None:
        source = """
        static unsigned checksum(const unsigned char *bytes, unsigned length)
        {
            unsigned value = 0;
            for (unsigned i = 0; i < length; ++i) {
                value ^= bytes[i];
            }
            return value;
        }

        void task(void)
        {
            unsigned char payload[8] = {0};
            (void)checksum(payload, sizeof(payload));
        }
        """
        profile = self._profile(source, "task")

        self.assertTrue(profile.dynamic_bound_verified)
        self.assertEqual({"can_checksum": 8}, profile.inferred_workload_counts)

    def test_sequential_memory_loop_is_inferred_automatically(self) -> None:
        source = """
        static unsigned char source_buffer[256];
        static unsigned char destination_buffer[256];

        void task(void)
        {
            for (unsigned i = 0; i < 256; ++i) {
                destination_buffer[i] = source_buffer[i];
            }
        }
        """
        profile = self._profile(source, "task")

        self.assertTrue(profile.dynamic_bound_verified)
        self.assertEqual(
            {"sequential_memory_access": 256},
            profile.inferred_workload_counts,
        )

    def test_primitive_operations_are_scaled_by_loop_bound(self) -> None:
        source = """
        void task(void)
        {
            unsigned value = 1;
            for (unsigned i = 0; i < 8; ++i) {
                value += i * 3U;
                if ((value % 5U) == 0U) {
                    value += 1U;
                } else {
                    value -= 1U;
                }
            }
        }
        """
        profile = self._profile(source, "task")
        operations = profile.inferred_operation_counts

        self.assertTrue(profile.dynamic_bound_verified)
        self.assertEqual(8, operations["integer_multiply_constant"])
        self.assertEqual(8, operations["integer_modulo_constant"])
        self.assertEqual(8, operations["branch_evaluation"])
        self.assertEqual(17, operations["integer_compare"])
        self.assertEqual(
            24,
            operations["integer_add_sub"],
            "Mutually exclusive branch bodies must not be summed.",
        )

    def test_float_operations_and_conversion_are_distinguished(self) -> None:
        source = """
        float task(unsigned sample)
        {
            float value = (float)sample;
            value = value * 0.5F + 1.0F;
            if (value > 10.0F) {
                value /= 2.0F;
            }
            return value;
        }
        """
        profile = self._profile(source, "task")
        operations = profile.inferred_operation_counts

        self.assertEqual(1, operations["numeric_conversion"])
        self.assertEqual(1, operations["floating_multiply"])
        self.assertEqual(1, operations["floating_add_sub"])
        self.assertEqual(1, operations["floating_compare"])
        self.assertEqual(1, operations["floating_divide"])

    def test_constant_and_variable_integer_costs_are_separate(self) -> None:
        source = """
        unsigned task(unsigned value, unsigned divisor)
        {
            value = value * 7U;
            value = value * divisor;
            value = value % 11U;
            return value / divisor;
        }
        """
        profile = self._profile(source, "task")
        operations = profile.inferred_operation_counts

        self.assertEqual(1, operations["integer_multiply_constant"])
        self.assertEqual(1, operations["integer_multiply_variable"])
        self.assertEqual(1, operations["integer_modulo_constant"])
        self.assertEqual(1, operations["integer_divide_variable"])

    def test_o0_catalog_counts_typed_32_bit_integer_arithmetic(self) -> None:
        source = """
        unsigned task(unsigned value, unsigned divisor)
        {
            for (unsigned i = 0; i < 4; ++i) {
                value += 3U;
                value = value * divisor;
                value = value / 2U;
                value = value % divisor;
            }
            return value;
        }
        """
        profile = self._profile(source, "task")

        self.assertEqual(
            {
                "integer_arithmetic.increment.unsigned32.variable": 4,
                "integer_arithmetic.add.unsigned32.constant": 4,
                "integer_arithmetic.multiply.unsigned32.variable": 4,
                "integer_arithmetic.divide.unsigned32.constant": 4,
                "integer_arithmetic.modulo.unsigned32.variable": 4,
            },
            profile.catalog_operation_counts,
        )

    def test_contextual_integer_patterns_and_chain_order(self) -> None:
        source = """
        static unsigned memory[16];
        void task(unsigned multiplier, unsigned divisor)
        {
            unsigned value = 1U;
            for (unsigned index = 0U; index < 8U; ++index) {
                value += 3U;
                value += index;
                value += memory[index];
                value *= multiplier;
                value += index;
                value += 31U / divisor;
                value += 0xf3579bdfU % divisor;
            }
        }
        """
        profile = self._profile(source, "task")
        counts = profile.contextual_integer_counts

        self.assertEqual(8, counts["loop_iterations"])
        self.assertEqual(1, counts["loop_invocations"])
        self.assertEqual(8, counts["add_constant_u32"])
        self.assertEqual(16, counts["add_index_u32"])
        self.assertEqual(8, counts["add_memory_u32"])
        self.assertEqual(8, counts["multiply_local_u32"])
        self.assertEqual(8, counts["index_before_multiply_u32"])
        self.assertEqual(8, counts["multiply_before_index_u32"])
        self.assertEqual(8, counts["divide_small_u32"])
        self.assertEqual(8, counts["modulo_large_u32"])
        self.assertEqual(8, counts["mixed_add_context_u32"])

    def test_explicit_calibrated_kernel_is_not_double_counted(self) -> None:
        source = """
        static unsigned int bitwise_logic(unsigned int count)
        {
            unsigned int value = 1U;
            unsigned int index;
            for (index = 0U; index < count; ++index) {
                value = (value ^ index) | 1U;
            }
            return value;
        }

        void task(void)
        {
            (void)bitwise_logic(128U);
        }
        """
        profile = self._profile(source, "task")

        self.assertEqual({"bitwise_logic": 128}, profile.inferred_workload_counts)
        self.assertNotIn("bitwise_logic", profile.inferred_operation_counts)

    def test_control_and_bitwise_contexts(self) -> None:
        source = """
        void task(void) {
            unsigned value = 7U;
            unsigned operand = 3U;
            for (unsigned index = 0U; index < 16U; ++index) {
                value -= operand;
                value &= operand;
                value |= operand;
                value ^= operand;
                value <<= 1U;
                value >>= 1U;
                if (value != 0U) { value += index; }
            }
        }
        """
        counts = self._profile(source, "task").contextual_integer_counts
        self.assertEqual(16, counts["subtract_local_u32"])
        self.assertEqual(16, counts["bitwise_and_u32"])
        self.assertEqual(16, counts["bitwise_or_u32"])
        self.assertEqual(16, counts["bitwise_xor_u32"])
        self.assertEqual(16, counts["shift_left_u32"])
        self.assertEqual(16, counts["shift_right_u32"])
        self.assertEqual(16, counts["branch_evaluation_u32"])
        self.assertEqual(16, counts["mixed_bitwise_context_u32"])

    def test_nested_expressions_are_grouped_without_double_counting(self) -> None:
        source = """
        void task(void) {
            unsigned v = 1U;
            for (unsigned i = 0U; i < 32U; ++i) {
                v = (v << 1U) | (v >> 31U);
            }
        }
        """
        counts = self._profile(source, "task").contextual_integer_counts
        self.assertEqual(32, counts["shift_rotate_u32"])
        self.assertNotIn("shift_left_u32", counts)
        self.assertNotIn("shift_right_u32", counts)

    def test_floating_loop_is_grouped(self) -> None:
        source = """
        void task(void) {
            float value = 1.0F;
            for (unsigned index = 0U; index < 32U; ++index) {
                value = value * 0.875F;
            }
        }
        """
        counts = self._profile(source, "task").contextual_integer_counts
        self.assertEqual(32, counts["float32_multiply_u32"])
        self.assertEqual(32, counts["floating_group_loop_iterations"])

    def test_dense_integer_control_correction_is_pattern_based(self) -> None:
        source = """
        void task(void) {
            unsigned v = 1U;
            for (unsigned i = 0U; i < 8U; ++i) {
                v *= ((i & 7U) + 1U);
                v ^= (i | 0x55U);
                v = (v << 1U) | (v >> 31U);
                if ((i & 1U) != 0U) { v += i; } else { v ^= i; }
            }
        }
        """
        counts = self._profile(source, "task").contextual_integer_counts
        self.assertEqual(8, counts["dense_integer_control_correction_u32"])

    @staticmethod
    def _profile(source: str, function_name: str):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.c"
            path.write_text(source, encoding="utf-8")
            profiles = StaticAnalyzer().analyze_file(path)
        return next(
            profile for profile in profiles if profile.task_name == function_name
        )


if __name__ == "__main__":
    unittest.main()
