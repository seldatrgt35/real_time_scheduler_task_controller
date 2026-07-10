"""Task criticality levels."""

from __future__ import annotations

from enum import Enum, auto


class Criticality(Enum):
    """Real-time and safety relevance of a task."""

    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    SAFETY_CRITICAL = auto()
