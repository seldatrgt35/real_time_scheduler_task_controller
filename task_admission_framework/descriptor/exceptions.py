"""Custom exceptions for task descriptor loading and validation."""

from __future__ import annotations


class DescriptorError(Exception):
    """Base class for descriptor subsystem failures."""


class DescriptorLoadError(DescriptorError):
    """Raised when a descriptor file cannot be loaded or parsed."""


class DescriptorValidationError(DescriptorError):
    """Raised when a descriptor fails semantic validation."""
