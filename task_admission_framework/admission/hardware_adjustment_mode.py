"""Hardware adjustment modes for static admission thresholds."""

from __future__ import annotations

from enum import Enum, auto


class HardwareAdjustmentMode(Enum):
    """How hardware metadata may adjust rule thresholds."""

    NONE = auto()
    PROTOTYPE_FREQUENCY_SCALING = auto()
    CALIBRATED = auto()

