"""Custom exceptions for STAR rule loading, validation, and lookup."""

from __future__ import annotations


class RuleError(Exception):
    """Base class for rule subsystem failures."""


class RuleLoadError(RuleError):
    """Raised when a rule file cannot be loaded or parsed."""


class RuleValidationError(RuleError):
    """Raised when a rule fails schema or semantic validation."""


class RuleNotFoundError(RuleError):
    """Raised when no matching admission rule exists."""

