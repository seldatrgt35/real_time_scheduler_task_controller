"""One point in a complexity-to-time calibration curve."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ComplexityTimePoint:
    """Maps a STAR complexity score to an observed execution time."""

    complexity: float
    execution_time_ms: float

