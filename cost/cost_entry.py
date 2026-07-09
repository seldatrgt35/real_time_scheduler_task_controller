"""Cost database entry model."""

from __future__ import annotations

from dataclasses import dataclass

from task_admission_framework.cost.cost_category import CostCategory


@dataclass(frozen=True, slots=True)
class CostEntry:
    """Metadata describing one supported software operation.

    The base weight is an initial engineering estimate of relative software
    complexity. It is not an execution time and not a final complexity score.
    """

    name: str
    category: CostCategory
    base_weight: int
    description: str
    reference: str
    blocking: bool
