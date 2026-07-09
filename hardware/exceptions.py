"""Custom exceptions for hardware profile loading and validation."""

from __future__ import annotations


class HardwareProfileError(Exception):
    """Base class for hardware profile subsystem failures."""


class HardwareLoadError(HardwareProfileError):
    """Raised when a hardware profile cannot be loaded or parsed."""


class HardwareValidationError(HardwareProfileError):
    """Raised when a hardware profile fails semantic validation."""
