"""Task analysis result model."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TaskProfile:
    """Static profile extracted from one C task/function.

    This model intentionally stores raw facts only. Derived metrics such as
    complexity or admission decisions belong in later framework modules.
    """

    task_name: str
    function_calls: list[str] = field(default_factory=list)
    call_graph: dict[str, list[str]] = field(default_factory=dict)
    reachable_functions: list[str] = field(default_factory=list)
    api_usage: dict[str, int] = field(default_factory=dict)
    if_count: int = 0
    for_count: int = 0
    while_count: int = 0
    switch_count: int = 0
    return_count: int = 0
    recursion_detected: bool = False
    pointer_operations: int = 0
    dynamic_memory: bool = False
    floating_point_usage: bool = False
    floating_point_operations: int = 0
    inferred_workload_counts: dict[str, int] = field(default_factory=dict)
    inferred_operation_counts: dict[str, int] = field(default_factory=dict)
    catalog_operation_counts: dict[str, int] = field(default_factory=dict)
    contextual_integer_counts: dict[str, int] = field(default_factory=dict)
    dynamic_bound_verified: bool = False
    dynamic_bound_notes: list[str] = field(default_factory=list)
    # Blocking calls are stored per occurrence. Repeated calls to the same API
    # must keep contributing to structural complexity.
    blocking_calls: list[str] = field(default_factory=list)
