"""STAR analysis pipeline orchestration."""

from __future__ import annotations

from pathlib import Path

from task_admission_framework.analyzer.analyzer import StaticAnalyzer
from task_admission_framework.complexity.complexity_calculator import ComplexityCalculator
from task_admission_framework.complexity.complexity_result import ComplexityResult
from task_admission_framework.cost.cost_database import CostDatabase
from task_admission_framework.descriptor.descriptor_loader import YamlDescriptorLoader
from task_admission_framework.descriptor.descriptor_validator import DescriptorValidator
from task_admission_framework.descriptor.exceptions import DescriptorError
from task_admission_framework.descriptor.task_descriptor import TaskDescriptor
from task_admission_framework.feature.feature_extractor import FeatureExtractor
from task_admission_framework.feature.feature_vector import FeatureVector
from task_admission_framework.hardware.exceptions import HardwareProfileError
from task_admission_framework.hardware.hardware_loader import HardwareLoader
from task_admission_framework.hardware.hardware_profile import HardwareProfile
from task_admission_framework.hardware.hardware_validator import HardwareValidator
from task_admission_framework.model.task_profile import TaskProfile
from task_admission_framework.pipeline.analysis_session import AnalysisSession
from task_admission_framework.pipeline.exceptions import PipelineStageError
from task_admission_framework.report.complexity_report import ComplexityReport
from task_admission_framework.report.report_generator import ReportGenerator


class AnalysisPipeline:
    """Coordinates existing STAR modules into one analysis session."""

    def __init__(
        self,
        analyzer: StaticAnalyzer | None = None,
        feature_extractor: FeatureExtractor | None = None,
        complexity_calculator: ComplexityCalculator | None = None,
        report_generator: ReportGenerator | None = None,
        cost_database: CostDatabase | None = None,
        descriptor_loader: YamlDescriptorLoader | None = None,
        descriptor_validator: DescriptorValidator | None = None,
        hardware_loader: HardwareLoader | None = None,
        hardware_validator: HardwareValidator | None = None,
    ) -> None:
        self._analyzer = analyzer or StaticAnalyzer()
        self._feature_extractor = feature_extractor or FeatureExtractor()
        self._complexity_calculator = complexity_calculator or ComplexityCalculator()
        self._report_generator = report_generator or ReportGenerator()
        self._cost_database = cost_database or CostDatabase()
        self._descriptor_loader = descriptor_loader or YamlDescriptorLoader()
        self._descriptor_validator = descriptor_validator or DescriptorValidator()
        self._hardware_loader = hardware_loader or HardwareLoader()
        self._hardware_validator = hardware_validator or HardwareValidator()

    def analyze(
        self,
        source_file: str | Path,
        descriptor_file: str | Path,
        hardware_profile_file: str | Path,
    ) -> AnalysisSession:
        profiles = self._analyze_source(source_file)
        task_descriptor = self._load_and_validate_descriptor(descriptor_file, profiles)
        task_profile = self._select_task_profile(profiles, task_descriptor.entry_function)
        feature_vector = self._extract_features(task_profile)
        complexity_result = self._calculate_complexity(feature_vector)
        complexity_report = self._generate_report(
            task_profile,
            feature_vector,
            complexity_result,
        )
        hardware_profile = self._load_and_validate_hardware(hardware_profile_file)

        return AnalysisSession(
            task_profile=task_profile,
            feature_vector=feature_vector,
            complexity_result=complexity_result,
            complexity_report=complexity_report,
            task_descriptor=task_descriptor,
            hardware_profile=hardware_profile,
        )

    def _analyze_source(self, source_file: str | Path) -> list[TaskProfile]:
        try:
            profiles = self._analyzer.analyze_file(source_file)
        except Exception as exc:
            raise PipelineStageError("Source analysis", str(exc)) from exc

        if not profiles:
            raise PipelineStageError(
                "Source analysis",
                f"No function definitions found in {Path(source_file)}",
            )

        return profiles

    def _load_and_validate_descriptor(
        self,
        descriptor_file: str | Path,
        profiles: list[TaskProfile],
    ) -> TaskDescriptor:
        try:
            descriptor = self._descriptor_loader.load(descriptor_file)
            self._descriptor_validator.validate(
                descriptor,
                available_functions={profile.task_name for profile in profiles},
            )
        except DescriptorError as exc:
            raise PipelineStageError("Task descriptor", str(exc)) from exc

        return descriptor

    def _extract_features(self, task_profile: TaskProfile) -> FeatureVector:
        try:
            return self._feature_extractor.extract(task_profile)
        except Exception as exc:
            raise PipelineStageError("Feature extraction", str(exc)) from exc

    def _calculate_complexity(self, feature_vector: FeatureVector) -> ComplexityResult:
        try:
            return self._complexity_calculator.calculate(
                feature_vector,
                self._cost_database,
            )
        except Exception as exc:
            raise PipelineStageError("Complexity calculation", str(exc)) from exc

    def _generate_report(
        self,
        task_profile: TaskProfile,
        feature_vector: FeatureVector,
        complexity_result: ComplexityResult,
    ) -> ComplexityReport:
        try:
            return self._report_generator.generate(
                complexity_result,
                feature_vector,
                task_name=task_profile.task_name,
            )
        except Exception as exc:
            raise PipelineStageError("Report generation", str(exc)) from exc

    @staticmethod
    def _select_task_profile(
        profiles: list[TaskProfile],
        entry_function: str,
    ) -> TaskProfile:
        for profile in profiles:
            if profile.task_name == entry_function:
                return profile

        raise PipelineStageError(
            "Task selection",
            f"No TaskProfile found for entry function: {entry_function}",
        )

    def _load_and_validate_hardware(
        self,
        hardware_profile_file: str | Path,
    ) -> HardwareProfile:
        try:
            hardware_profile = self._hardware_loader.load(hardware_profile_file)
            self._hardware_validator.validate(hardware_profile)
        except HardwareProfileError as exc:
            raise PipelineStageError("Hardware profile", str(exc)) from exc

        return hardware_profile
