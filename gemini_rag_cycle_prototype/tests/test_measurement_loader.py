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
    def test_structural_summary_counts_operation_shape(self) -> None:
        from gemini_rag_cycle_prototype.rag.measurement_loader import structural_summary

        summary = structural_summary(
            "void Task(void){for(i=0;i<8;i++){x[i]=Helper(x[i]);"
            "if(x[i]>3){mask|=1U<<i;}}}"
        )
        self.assertEqual(1, summary.loop_count)
        self.assertEqual(1, summary.helper_call_count)
        self.assertEqual(1, summary.branch_count)
        self.assertGreaterEqual(summary.array_access_count, 3)
        self.assertGreater(summary.comparison_count, 0)
        self.assertGreater(summary.bitwise_operator_count, 0)

    def test_validated_learning_feedback_is_loaded(self) -> None:
        root = Path(__file__).resolve().parents[2]
        records = MeasurementLoader(root).load()
        feedback = {
            record.task_name: record
            for record in records
            if record.dataset_split == "learning_feedback"
        }
        self.assertEqual(
            {
                "BatteryBalancing_Task10ms",
                "EpsTorqueArbitration_Task5ms",
                "ThermalNetworkSupervision_Task20ms",
                "DcLinkRippleMonitor_Task1ms",
                "NetworkSignalSupervision_Task10ms",
                "InjectorPulseCompensation_Task5ms",
            },
            set(feedback),
        )
        self.assertEqual(82.333, feedback["BatteryBalancing_Task10ms"].measurement.maximum_us)
        self.assertEqual(40, feedback["BatteryBalancing_Task10ms"].measurement.sample_count)
        self.assertEqual(6, feedback["BatteryBalancing_Task10ms"].measurement.measurement_overhead_cycles)
        self.assertEqual(
            57.5, feedback["DcLinkRippleMonitor_Task1ms"].measurement.maximum_us
        )
        self.assertIn(
            "gemini_rag_holdout_v4",
            feedback["DcLinkRippleMonitor_Task1ms"].source_path,
        )
        serialized = feedback["BatteryBalancing_Task10ms"].model_dump_json()
        self.assertNotIn("gemini_prediction", serialized)
        self.assertNotIn("signed_error", serialized)

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

    def test_feedback_reference_contains_defines_helpers_and_initialization(self) -> None:
        records = MeasurementLoader(ROOT).load()
        injector = next(
            item for item in records
            if item.task_name == "InjectorPulseCompensation_Task5ms"
        )
        self.assertIn("#define INJECTOR_COUNT", injector.source_context)
        self.assertIn("AutomotiveHoldoutV4_Initialize", injector.source_context)
        self.assertIn("InterpolatePulseU16", injector.callee_source)
        self.assertIn("ApplyVoltageCorrectionU16", injector.callee_source)
        self.assertNotEqual("", injector.context_fingerprint)

    def test_function_extraction_and_path_independent_fingerprint(self) -> None:
        first = "/* x */ void Task(void) { unsigned x = 1U; }"
        second = "void Task(void)\n{ unsigned x=1U; } // y"
        self.assertIsNotNone(extract_function(first, "Task"))
        self.assertEqual(source_fingerprint(first), source_fingerprint(second))
        self.assertEqual(normalize_source(first), normalize_source(second))


if __name__ == "__main__":
    unittest.main()
