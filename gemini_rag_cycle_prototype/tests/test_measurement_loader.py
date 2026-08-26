from pathlib import Path
import tempfile
import unittest

from gemini_rag_cycle_prototype.rag.measurement_loader import (
    MeasurementLoader,
    _measurement,
    extract_function,
    normalize_source,
    source_fingerprint,
)


ROOT = Path(__file__).resolve().parents[2]


class MeasurementLoaderTest(unittest.TestCase):
    def test_us_x1000_is_divided_by_one_thousand(self) -> None:
        measurement = _measurement(
            {
                "mean_execution_us_x1000": "28187",
                "max_execution_us_x1000": "28208",
                "completed_samples": "40",
                "measurement_overhead_cycles": "8",
            },
            Path("board.csv"),
        )
        self.assertAlmostEqual(28.187, measurement.mean_us)
        self.assertAlmostEqual(28.208, measurement.maximum_us)
        self.assertEqual(40, measurement.sample_count)
        self.assertEqual(8, measurement.measurement_overhead_cycles)

    def test_repository_task_is_matched_to_real_source(self) -> None:
        loader = MeasurementLoader(ROOT)
        records = loader.load()
        torque = next(
            item for item in records
            if item.task_name == "AppTask_TorqueCoordination_20ms"
        )
        self.assertIn("void AppTask_TorqueCoordination_20ms", torque.source_code)
        self.assertAlmostEqual(48.041, torque.measurement.maximum_us)
        self.assertEqual("holdout", torque.dataset_split)

    def test_function_extraction_and_path_independent_fingerprint(self) -> None:
        first = "/* x */ void Task(void) { unsigned x = 1U; }"
        second = "void Task(void)\n{ unsigned x=1U; } // y"
        self.assertIsNotNone(extract_function(first, "Task"))
        self.assertEqual(source_fingerprint(first), source_fingerprint(second))
        self.assertEqual(normalize_source(first), normalize_source(second))


if __name__ == "__main__":
    unittest.main()
