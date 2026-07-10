"""Validation for STAR admission threshold rules."""

from __future__ import annotations

from task_admission_framework.rules.admission_rule import AdmissionRule
from task_admission_framework.rules.exceptions import RuleValidationError


class RuleValidator:
    """Validates rule schema and semantics without making decisions."""

    _ALLOWED_CRITICALITIES = {"LOW", "MEDIUM", "HIGH", "SAFETY_CRITICAL"}

    def validate(self, rule: AdmissionRule) -> None:
        self._validate_not_empty("hardware", rule.hardware)
        self._validate_positive("period_ms", rule.period_ms)
        self._validate_positive("max_complexity", rule.max_complexity)
        self._validate_not_empty("description", rule.description)
        self._validate_not_empty("source", rule.source)

        if not isinstance(rule.validated, bool):
            raise RuleValidationError("validated must be a boolean.")

        if rule.criticality is None:
            return

        if rule.criticality not in self._ALLOWED_CRITICALITIES:
            raise RuleValidationError(
                "criticality must be LOW, MEDIUM, HIGH, SAFETY_CRITICAL, or None."
            )

    @staticmethod
    def _validate_not_empty(field_name: str, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise RuleValidationError(f"{field_name} must not be empty.")

    @staticmethod
    def _validate_positive(field_name: str, value: int | float) -> None:
        if not isinstance(value, int | float) or isinstance(value, bool) or value <= 0:
            raise RuleValidationError(f"{field_name} must be greater than 0.")

