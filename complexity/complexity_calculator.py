"""Deterministic structural complexity calculator."""

from __future__ import annotations

from collections.abc import Iterable

from task_admission_framework.complexity.complexity_result import ComplexityResult
from task_admission_framework.complexity.cost_breakdown import CostBreakdown
from task_admission_framework.cost.cost_database import CostDatabase
from task_admission_framework.feature.feature_vector import FeatureVector


class ComplexityCalculator:
    """Calculates structural software complexity from extracted features.

    This calculator does not estimate execution time, normalize scores, inspect
    hardware, or make admission decisions.
    """

    _FEATURE_BASE_COSTS: dict[str, int] = {
        "Function Calls": 1,
        "Loops": 3,
        "Branches": 2,
        "Switches": 3,
        "Returns": 1,
        "Floating Point Operations": 4,
        "Pointer Operations": 2,
        "Blocking Calls": 5,
        "Dynamic Memory Calls": 8,
        "Recursion Detected": 10,
    }

    def calculate(
        self,
        feature_vector: FeatureVector,
        cost_database: CostDatabase,
    ) -> ComplexityResult:
        """Calculate CS = sum(occurrences x base cost)."""

        breakdown = list(self._build_breakdown(feature_vector, cost_database))
        total_score = sum(item.subtotal for item in breakdown)
        return ComplexityResult(total_score=total_score, breakdown=breakdown)

    def _build_breakdown(
        self,
        feature_vector: FeatureVector,
        cost_database: CostDatabase,
    ) -> Iterable[CostBreakdown]:
        feature_occurrences = {
            "Function Calls": feature_vector.total_function_calls,
            "API Calls": feature_vector.total_api_calls,
            "Loops": feature_vector.total_loops,
            "Branches": feature_vector.total_branches,
            "Switches": feature_vector.total_switches,
            "Returns": feature_vector.total_returns,
            "Floating Point Operations": feature_vector.floating_point_operations,
            "Pointer Operations": feature_vector.pointer_operations,
            "Blocking Calls": feature_vector.blocking_calls,
            "Dynamic Memory Calls": feature_vector.dynamic_memory_calls,
            "Recursion Detected": 1 if feature_vector.recursion_detected else 0,
        }

        for name, occurrences in feature_occurrences.items():
            if occurrences <= 0:
                continue

            base_cost = self._resolve_base_cost(name, cost_database)
            yield CostBreakdown(
                name=name,
                occurrences=occurrences,
                base_cost=base_cost,
                subtotal=occurrences * base_cost,
            )

    def _resolve_base_cost(self, feature_name: str, cost_database: CostDatabase) -> int:
        if feature_name == "API Calls":
            return self._aggregate_api_base_cost(cost_database)
        return self._FEATURE_BASE_COSTS[feature_name]

    @staticmethod
    def _aggregate_api_base_cost(cost_database: CostDatabase) -> int:
        entries = cost_database.list_entries()
        if not entries:
            return 0

        total_weight = sum(entry.base_weight for entry in entries)
        return round(total_weight / len(entries))
