"""Input model for one task in a STAR task set."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    hardware_profile_file: Path
    rules_file: Path
    # Internal compatibility value for the legacy rule database. It is not a
    # second user-controlled scheduling input; priority is the sole urgency
    # input in the task-set API.
    criticality: str = field(default="HIGH", init=False, repr=False)
