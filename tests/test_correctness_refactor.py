"""Correctness tests for STAR admission and scheduler refactoring."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from task_admission_framework.admission.admission_controller import (
    AdmissionController,
)
from task_admission_framework.admission.hardware_adjustment_mode import (
    HardwareAdjustmentMode,
)
from task_admission_framework.complexity.complexity_result import ComplexityResult
from task_admission_framework.feature.feature_vector import FeatureVector
from task_admission_framework.hardware.hardware_profile import HardwareProfile
from task_admission_framework.rules.admission_rule import AdmissionRule
from task_admission_framework.rules.rule_database import RuleDatabase
from task_admission_framework.scheduling.fixed_priority_analyzer import (
    FixedPriorityAnalyzer,
)
from task_admission_framework.scheduling.scheduler_result import SchedulerTaskInput
from task_admission_framework.scheduling.scheduler_status import SchedulerStatus
from task_admission_framework.taskset import taskset_analyzer as taskset_analyzer_module
from task_admission_framework.taskset.taskset_analyzer import TaskSetAnalyzer
from task_admission_framework.taskset.taskset_entry import TaskSetEntry


class CorrectnessRefactorTests(unittest.TestCase):
    """Tests for hardware adjustment and scheduler separation."""

    def test_raw_complexity_unchanged_across_hardware_profiles(self) -> None:
        rule_database = self._rule_database()
        slow_decision = AdmissionController().evaluate(
            self._session(cpu_frequency_mhz=80, score=50),
            rule_database,
        )
        fast_decision = AdmissionController().evaluate(
            self._session(cpu_frequency_mhz=170, score=50),
            rule_database,
        )

        self.assertEqual(slow_decision.complexity_score, 50.0)
        self.assertEqual(fast_decision.complexity_score, 50.0)
        self.assertNotEqual(
            slow_decision.hardware_adjusted_max_complexity,
            fast_decision.hardware_adjusted_max_complexity,
        )

    def test_none_adjustment_mode_uses_rule_maximum(self) -> None:
        decision = AdmissionController(
            hardware_adjustment_mode=HardwareAdjustmentMode.NONE,
        ).evaluate(self._session(cpu_frequency_mhz=80, score=50), self._rule_database())

        self.assertEqual(decision.hardware_scaling_factor, 1.0)
        self.assertEqual(decision.hardware_adjusted_max_complexity, 60.0)
        self.assertIsNone(decision.warning)

    def test_prototype_frequency_scaling_warning(self) -> None:
        decision = AdmissionController(
            hardware_adjustment_mode=HardwareAdjustmentMode.PROTOTYPE_FREQUENCY_SCALING,
        ).evaluate(
            self._session(cpu_frequency_mhz=80, score=50),
            self._rule_database(),
        )

        self.assertEqual(
            decision.hardware_adjustment_mode,
            HardwareAdjustmentMode.PROTOTYPE_FREQUENCY_SCALING,
        )
        self.assertIsNotNone(decision.warning)
        self.assertIn("unvalidated prototype heuristic", decision.warning or "")

    def test_calibrated_mode_uses_reference_rule_scaling(self) -> None:
        decision = AdmissionController().evaluate(
            self._session(cpu_frequency_mhz=80, score=50),
            self._rule_database(),
        )

        self.assertEqual(decision.hardware_adjustment_mode, HardwareAdjustmentMode.CALIBRATED)
        self.assertAlmostEqual(decision.hardware_scaling_factor, 80 / 112)
        self.assertAlmostEqual(decision.hardware_adjusted_max_complexity, 60 * 80 / 112)
        self.assertIn("reference rule thresholds are not validated", decision.warning or "")

    def test_priority_ordering_uses_higher_numeric_freertos_priority(self) -> None:
        result = FixedPriorityAnalyzer().analyze(
            [
                SchedulerTaskInput(
                    task_name="low",
                    period_ms=10,
                    deadline_ms=10,
                    priority=1,
                    execution_budget_us=1000.0,
                ),
                SchedulerTaskInput(
                    task_name="high",
                    period_ms=5,
                    deadline_ms=5,
                    priority=3,
                    execution_budget_us=500.0,
                ),
            ]
        )

        by_name = {task.task_name: task for task in result.task_results}
        self.assertEqual(by_name["high"].response_time_us, 500.0)
        self.assertEqual(by_name["low"].response_time_us, 1500.0)

    def test_scheduler_unverified_without_execution_budgets(self) -> None:
        result = FixedPriorityAnalyzer().analyze(
            [
                SchedulerTaskInput(
                    task_name="task",
                    period_ms=5,
                    deadline_ms=5,
                    priority=2,
                    execution_budget_us=None,
                )
            ]
        )

        self.assertEqual(result.overall_status, SchedulerStatus.UNVERIFIED)
        self.assertIn("calibration is missing", result.reason)

    def test_fixed_priority_response_time_with_synthetic_budgets(self) -> None:
        result = FixedPriorityAnalyzer().analyze(
            [
                SchedulerTaskInput(
                    task_name="fast",
                    period_ms=5,
                    deadline_ms=5,
                    priority=3,
                    execution_budget_us=500.0,
                ),
                SchedulerTaskInput(
                    task_name="medium",
                    period_ms=10,
                    deadline_ms=10,
                    priority=2,
                    execution_budget_us=1000.0,
                ),
                SchedulerTaskInput(
                    task_name="slow",
                    period_ms=20,
                    deadline_ms=20,
                    priority=1,
                    execution_budget_us=2000.0,
                ),
            ]
        )

        self.assertEqual(result.overall_status, SchedulerStatus.FEASIBLE)
        by_name = {task.task_name: task for task in result.task_results}
        self.assertEqual(by_name["slow"].response_time_us, 3500.0)

    def test_taskset_flow_remains_functional_with_unverified_scheduler(self) -> None:
        original_temp_directory = taskset_analyzer_module.tempfile.TemporaryDirectory
        taskset_analyzer_module.tempfile.TemporaryDirectory = _FakeTemporaryDirectory
        try:
            analyzer = _NoWriteTaskSetAnalyzer(pipeline=_FakePipeline())
            result = analyzer.analyze(
                [
                    TaskSetEntry(
                        name="SyntheticTask",
                        source_file="synthetic.c",
                        entry_function="SyntheticTask",
                        period_ms=5,
                        deadline_ms=5,
                        priority=2,
                        criticality="HIGH",
                        hardware_profile_file="synthetic.json",
                        rules_file=(
                            "task_admission_framework/rules/profiles/"
                            "S32K148_rules.json"
                        ),
                    )
                ]
            )
        finally:
            taskset_analyzer_module.tempfile.TemporaryDirectory = (
                original_temp_directory
            )

        self.assertEqual(len(result.task_results), 1)
        self.assertEqual(result.scheduler_status, SchedulerStatus.UNVERIFIED.name)

    @staticmethod
    def _rule_database() -> RuleDatabase:
        return RuleDatabase(
            [
                AdmissionRule(
                    hardware="S32K148",
                    period_ms=5,
                    criticality="HIGH",
                    max_complexity=60.0,
                    description="Synthetic reference rule",
                    source="synthetic test",
                    validated=False,
                )
            ]
        )

    @staticmethod
    def _session(cpu_frequency_mhz: int, score: int):
        return SimpleNamespace(
            hardware_profile=HardwareProfile(
                name="SYNTHETIC",
                vendor="Synthetic",
                family="Synthetic",
                architecture="Synthetic",
                core="Synthetic",
                cpu_frequency_mhz=cpu_frequency_mhz,
                flash_kb=1,
                ram_kb=1,
                fpu=False,
                dma=False,
                mpu=False,
                cache=False,
                adc_units=0,
                can_units=0,
                uart_units=0,
                spi_units=0,
                i2c_units=0,
            ),
            task_descriptor=SimpleNamespace(
                task_name="SyntheticTask",
                period_ms=5,
                criticality=SimpleNamespace(name="HIGH"),
            ),
            complexity_result=ComplexityResult(total_score=score),
            feature_vector=FeatureVector(
                total_function_calls=0,
                total_api_calls=0,
                total_loops=0,
                total_branches=0,
                total_switches=0,
                total_returns=0,
                floating_point_operations=0,
                pointer_operations=0,
                blocking_calls=0,
                dynamic_memory_calls=0,
                recursion_detected=False,
            ),
        )


class _FakePipeline:
    def analyze(self, source_file, descriptor_file, hardware_profile_file):
        del source_file, descriptor_file, hardware_profile_file
        session = CorrectnessRefactorTests._session(cpu_frequency_mhz=112, score=10)
        session.complexity_report = SimpleNamespace(breakdown=[])
        return session


class _FakeTemporaryDirectory:
    def __init__(self, prefix: str):
        del prefix

    def __enter__(self) -> str:
        return "."

    def __exit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback


class _NoWriteTaskSetAnalyzer(TaskSetAnalyzer):
    @staticmethod
    def _write_descriptor(descriptor_dir, index, entry):
        del descriptor_dir, index, entry
        return "synthetic.yaml"


if __name__ == "__main__":
    unittest.main()
