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
