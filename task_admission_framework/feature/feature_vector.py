"""Compact software metric representation for future complexity analysis."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class FeatureVector:
    """Aggregated software metrics independent from Clang and the AST."""

    total_function_calls: int
    total_api_calls: int
    total_loops: int
    total_branches: int
    total_switches: int
    total_returns: int
    floating_point_operations: int
    pointer_operations: int
    blocking_calls: int
    dynamic_memory_calls: int
    recursion_detected: bool
    api_call_counts: dict[str, int] = field(default_factory=dict)
