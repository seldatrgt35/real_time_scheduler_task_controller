"""Admission decision model."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from task_admission_framework.admission.hardware_adjustment_mode import (
    HardwareAdjustmentMode,
)


class AdmissionStatus(Enum):
    """Possible STAR admission outcomes."""

    ACCEPT = auto()
    REJECT = auto()


@dataclass(frozen=True, slots=True)
class HardwareAdjustmentBreakdown:
    """One category contribution after target-hardware adjustment."""

    category: str
    raw_score: float
    factor: float
    adjusted_score: float


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    """Result produced by the Admission Controller."""

    task_name: str
    hardware: str
    period_ms: int
    criticality: str | None
    complexity_score: float
    hardware_adjusted_score: float
    max_complexity: float
    hardware_adjusted_max_complexity: float
    hardware_scaling_factor: float
    hardware_adjustment_breakdown: list[HardwareAdjustmentBreakdown]
    hardware_adjustment_mode: HardwareAdjustmentMode
    warning: str | None
    star_load_indicator: float
    scheduler_status: str
    scheduler_reason: str
    status: AdmissionStatus
    reason: str
    rule_source: str
    rule_validated: bool
