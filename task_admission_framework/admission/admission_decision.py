"""Admission decision model."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class AdmissionStatus(Enum):
    """Possible STAR admission outcomes."""

    ACCEPT = auto()
    REJECT = auto()


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    """Result produced by the Admission Controller."""

    task_name: str
    hardware: str
    period_ms: int
    criticality: str | None
    complexity_score: float
    max_complexity: float
    status: AdmissionStatus
    reason: str
    rule_source: str
    rule_validated: bool

