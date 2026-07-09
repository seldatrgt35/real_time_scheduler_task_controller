"""Unified STAR analysis session result."""

from __future__ import annotations

from dataclasses import dataclass

from task_admission_framework.complexity.complexity_result import ComplexityResult
from task_admission_framework.descriptor.task_descriptor import TaskDescriptor
from task_admission_framework.feature.feature_vector import FeatureVector
from task_admission_framework.hardware.hardware_profile import HardwareProfile
from task_admission_framework.model.task_profile import TaskProfile
from task_admission_framework.report.complexity_report import ComplexityReport


@dataclass(frozen=True, slots=True)
class AnalysisSession:
    """Container for all outputs produced by the STAR analysis core."""

    task_profile: TaskProfile
    feature_vector: FeatureVector
    complexity_result: ComplexityResult
    complexity_report: ComplexityReport
    task_descriptor: TaskDescriptor
    hardware_profile: HardwareProfile
