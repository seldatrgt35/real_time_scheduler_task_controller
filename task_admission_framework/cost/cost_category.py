"""Cost categories for supported software operations."""

from __future__ import annotations

from enum import Enum, auto


class CostCategory(Enum):
    """High-level operation categories used by the cost knowledge base."""

    COMPUTATION = auto()
    CONTROL_FLOW = auto()
    MEMORY = auto()
    RTOS = auto()
    PERIPHERAL = auto()
    FLOATING_POINT = auto()
    OTHER = auto()
