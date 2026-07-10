"""Admission threshold rule model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AdmissionRule:
    """Stored threshold rule for a hardware, period, and optional criticality."""

    hardware: str
    period_ms: int
    criticality: str | None
    max_complexity: float
    description: str
    source: str
    validated: bool

