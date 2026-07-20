"""Complexity-to-execution-time calibration profile."""

from __future__ import annotations

from dataclasses import dataclass

from task_admission_framework.calibration.complexity_time_point import (
    ComplexityTimePoint,
)


@dataclass(frozen=True, slots=True)
class ComplexityTimeProfile:
    """Task-independent mapping from complexity score to execution time."""

    profile_id: str
    reference_hardware: str
    source: str
    validated: bool
    points: list[ComplexityTimePoint]

