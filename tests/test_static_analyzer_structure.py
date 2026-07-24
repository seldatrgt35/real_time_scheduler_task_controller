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
