"""Transforms analyzer task profiles into compact feature vectors."""

from __future__ import annotations

from task_admission_framework.feature.feature_vector import FeatureVector
from task_admission_framework.model.task_profile import TaskProfile


class FeatureExtractor:
    """Extracts aggregate software metrics from a TaskProfile.

    The extractor does not inspect AST nodes, apply weights, calculate
    complexity scores, or make admission decisions.
    """

    def extract(self, profile: TaskProfile) -> FeatureVector:
        return FeatureVector(
            total_function_calls=len(profile.function_calls),
            total_api_calls=sum(profile.api_usage.values()),
            total_loops=self._count_loops(profile),
            total_branches=profile.if_count,
            total_switches=profile.switch_count,
            total_returns=profile.return_count,
            floating_point_operations=self._count_floating_point_operations(profile),
            pointer_operations=profile.pointer_operations,
            blocking_calls=len(profile.blocking_calls),
            dynamic_memory_calls=self._count_dynamic_memory_calls(profile),
            recursion_detected=profile.recursion_detected,
        )

    @staticmethod
    def _count_loops(profile: TaskProfile) -> int:
        return profile.for_count + profile.while_count

    @staticmethod
    def _count_floating_point_operations(profile: TaskProfile) -> int:
        return 1 if profile.floating_point_usage else 0

    @staticmethod
    def _count_dynamic_memory_calls(profile: TaskProfile) -> int:
        return sum(
            profile.api_usage.get(api_name, 0)
            for api_name in ("malloc", "calloc", "realloc", "free")
        )
