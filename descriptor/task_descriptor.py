"""Real-time task descriptor model."""

from __future__ import annotations

from dataclasses import dataclass

from task_admission_framework.descriptor.criticality import Criticality


@dataclass(frozen=True, slots=True)
class TaskDescriptor:
    """Source-independent real-time requirements for one task."""

    task_name: str
    entry_function: str
    period_ms: int
    deadline_ms: int
    priority: int
    stack_size: int
    criticality: Criticality
