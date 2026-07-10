"""Transforms complexity results into explainable reports."""

from __future__ import annotations

from collections import defaultdict

from task_admission_framework.complexity.complexity_result import ComplexityResult
from task_admission_framework.complexity.cost_breakdown import CostBreakdown
from task_admission_framework.cost.cost_category import CostCategory
from task_admission_framework.feature.feature_vector import FeatureVector
from task_admission_framework.report.complexity_report import ComplexityReport


class ReportGenerator:
    """Builds human-readable complexity reports from existing results."""

    _CATEGORY_BY_BREAKDOWN_NAME: dict[str, CostCategory] = {
        "Function Calls": CostCategory.COMPUTATION,
        "Loops": CostCategory.CONTROL_FLOW,
        "Branches": CostCategory.CONTROL_FLOW,
        "Switches": CostCategory.CONTROL_FLOW,
        "Returns": CostCategory.CONTROL_FLOW,
        "Floating Point Operations": CostCategory.FLOATING_POINT,
        "Pointer Operations": CostCategory.MEMORY,
        "Blocking Calls": CostCategory.RTOS,
        "Dynamic Memory Calls": CostCategory.MEMORY,
        "Recursion Detected": CostCategory.CONTROL_FLOW,
    }

    _RTOS_PREFIXES = ("xQueue", "xSemaphore", "vTask")
    _PERIPHERAL_PREFIXES = (
        "ADC_",
        "CAN_",
        "GPIO_",
        "I2C_",
        "SPI_",
        "UART_",
    )
    _MEMORY_NAMES = {"malloc", "calloc", "realloc", "free"}
    _FLOATING_POINT_NAMES = {"Floating Point Operations"}
    _STRUCTURAL_BREAKDOWN_NAMES = set(_CATEGORY_BY_BREAKDOWN_NAME)

    def generate(
        self,
        complexity_result: ComplexityResult,
        feature_vector: FeatureVector,
        task_name: str = "Unknown",
    ) -> ComplexityReport:
        category_costs = self._aggregate_by_category(complexity_result.breakdown)
        api_cost = self._aggregate_api_cost(complexity_result.breakdown)

        return ComplexityReport(
            task_name=task_name,
            total_score=complexity_result.total_score,
            total_features=self._count_total_features(feature_vector),
            api_cost=api_cost,
            control_flow_cost=category_costs[CostCategory.CONTROL_FLOW],
            memory_cost=category_costs[CostCategory.MEMORY],
            rtos_cost=category_costs[CostCategory.RTOS],
            peripheral_cost=category_costs[CostCategory.PERIPHERAL],
            floating_point_cost=category_costs[CostCategory.FLOATING_POINT],
            computation_cost=category_costs[CostCategory.COMPUTATION],
            other_cost=category_costs[CostCategory.OTHER] - api_cost,
            breakdown=list(complexity_result.breakdown),
        )

    def _aggregate_by_category(
        self,
        breakdown: list[CostBreakdown],
    ) -> defaultdict[CostCategory, int]:
        category_costs: defaultdict[CostCategory, int] = defaultdict(int)

        for item in breakdown:
            category = self._classify_breakdown_item(item.name)
            category_costs[category] += item.subtotal

        return category_costs

    def _classify_breakdown_item(self, name: str) -> CostCategory:
        if name in self._CATEGORY_BY_BREAKDOWN_NAME:
            return self._CATEGORY_BY_BREAKDOWN_NAME[name]

        if name in self._MEMORY_NAMES:
            return CostCategory.MEMORY

        if name in self._FLOATING_POINT_NAMES:
            return CostCategory.FLOATING_POINT

        if name.startswith(self._RTOS_PREFIXES):
            return CostCategory.RTOS

        if name.startswith(self._PERIPHERAL_PREFIXES):
            return CostCategory.PERIPHERAL

        return CostCategory.OTHER

    @staticmethod
    def _aggregate_api_cost(breakdown: list[CostBreakdown]) -> int:
        return sum(
            item.subtotal
            for item in breakdown
            if item.name not in ReportGenerator._STRUCTURAL_BREAKDOWN_NAMES
        )

    @staticmethod
    def _count_total_features(feature_vector: FeatureVector) -> int:
        return (
            feature_vector.total_function_calls
            + feature_vector.total_api_calls
            + feature_vector.total_loops
            + feature_vector.total_branches
            + feature_vector.total_switches
            + feature_vector.total_returns
            + feature_vector.floating_point_operations
            + feature_vector.pointer_operations
            + feature_vector.blocking_calls
            + feature_vector.dynamic_memory_calls
            + (1 if feature_vector.recursion_detected else 0)
        )
