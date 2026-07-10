"""In-memory rule knowledge base for STAR."""

from __future__ import annotations

from collections.abc import Iterable

from task_admission_framework.rules.admission_rule import AdmissionRule
from task_admission_framework.rules.exceptions import RuleNotFoundError
from task_admission_framework.rules.rule_validator import RuleValidator


class RuleDatabase:
    """Stores admission rules and retrieves matching thresholds.

    This class is a repository only. It does not compare complexity scores or
    make ACCEPT / REJECT decisions.
    """

    def __init__(
        self,
        rules: Iterable[AdmissionRule],
        validator: RuleValidator | None = None,
    ) -> None:
        self._validator = validator or RuleValidator()
        self._rules = list(rules)

        for rule in self._rules:
            self._validator.validate(rule)

    def list_rules(self) -> list[AdmissionRule]:
        """Return all stored rules in insertion order."""

        return list(self._rules)

    def find_rule(
        self,
        hardware: str,
        period_ms: int,
        criticality: str | None = None,
    ) -> AdmissionRule:
        """Find a rule by hardware, period, and optional criticality."""

        normalized_hardware = hardware.strip()
        normalized_criticality = self._normalize_criticality(criticality)

        exact_match = self._find_exact(
            normalized_hardware,
            period_ms,
            normalized_criticality,
        )
        if exact_match is not None:
            return exact_match

        if normalized_criticality is not None:
            fallback_match = self._find_exact(normalized_hardware, period_ms, None)
            if fallback_match is not None:
                return fallback_match

        raise RuleNotFoundError(
            "No admission rule found for "
            f"hardware={hardware}, period_ms={period_ms}, criticality={criticality}."
        )

    def _find_exact(
        self,
        hardware: str,
        period_ms: int,
        criticality: str | None,
    ) -> AdmissionRule | None:
        for rule in self._rules:
            if (
                rule.hardware == hardware
                and rule.period_ms == period_ms
                and rule.criticality == criticality
            ):
                return rule
        return None

    @staticmethod
    def _normalize_criticality(criticality: str | None) -> str | None:
        if criticality is None:
            return None
        return criticality.strip().upper()

