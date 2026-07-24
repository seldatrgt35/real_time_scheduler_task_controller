"""Input model for one task in a STAR task set."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TaskSetEntry:
    """One task to analyze as part of a task set."""

    name: str
    source_file: Path
    entry_function: str
    period_ms: int
    deadline_ms: int
    priority: int
    criticality: str
    hardware_profile_file: Path
    rules_file: Path
    workload_class: str | None = None
    work_units: int | None = None
