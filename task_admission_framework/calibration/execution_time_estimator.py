"""Estimate execution time from task-independent complexity calibration."""

from __future__ import annotations

from task_admission_framework.calibration.complexity_time_point import (
    ComplexityTimePoint,
)
from task_admission_framework.calibration.complexity_time_profile import (
    ComplexityTimeProfile,
)
from task_admission_framework.calibration.exceptions import CalibrationEstimateError


class ExecutionTimeEstimator:
    """Interpolates execution time from hardware-adjusted complexity score."""

    def estimate_us(
        self,
        complexity_score: float,
        profile: ComplexityTimeProfile,
    ) -> tuple[float, str | None]:
        """Return estimated execution budget in microseconds and an optional note."""

        if complexity_score <= 0:
            return 0.0, None

        points = profile.points
        if len(points) == 1:
            point = points[0]
            return (
                (complexity_score / point.complexity) * point.execution_time_ms * 1000.0,
                "Execution estimate uses a single-point linear calibration.",
            )

        lower, upper, note = self._find_bounds(complexity_score, points)
        estimate_ms = self._interpolate(complexity_score, lower, upper)
        return estimate_ms * 1000.0, note

    @staticmethod
    def _find_bounds(
        complexity_score: float,
        points: list[ComplexityTimePoint],
    ) -> tuple[ComplexityTimePoint, ComplexityTimePoint, str | None]:
        if complexity_score < points[0].complexity:
            return (
                points[0],
                points[1],
                "Execution estimate is extrapolated below the calibrated range.",
            )

        for index in range(len(points) - 1):
            lower = points[index]
            upper = points[index + 1]
            if lower.complexity <= complexity_score <= upper.complexity:
                return lower, upper, None

        return (
            points[-2],
            points[-1],
            "Execution estimate is extrapolated above the calibrated range.",
        )

    @staticmethod
    def _interpolate(
        complexity_score: float,
        lower: ComplexityTimePoint,
        upper: ComplexityTimePoint,
    ) -> float:
        complexity_span = upper.complexity - lower.complexity
        time_span = upper.execution_time_ms - lower.execution_time_ms
        if complexity_span <= 0:
            raise CalibrationEstimateError("Calibration points must be increasing.")

        ratio = (complexity_score - lower.complexity) / complexity_span
        return lower.execution_time_ms + ratio * time_span

