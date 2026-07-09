"""Explainable subtotal entry for complexity calculation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    """One line item in the structural complexity result."""

    name: str
    occurrences: int
    base_cost: int
    subtotal: int
