"""JSON loader for STAR admission threshold rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from task_admission_framework.rules.admission_rule import AdmissionRule
from task_admission_framework.rules.exceptions import RuleLoadError, RuleValidationError
from task_admission_framework.rules.rule_validator import RuleValidator


class RuleLoader:
    """Loads and validates admission rules from JSON files."""

    _JSON_SUFFIX = ".json"

    def __init__(self, validator: RuleValidator | None = None) -> None:
        self._validator = validator or RuleValidator()

    def load(self, rule_path: str | Path) -> list[AdmissionRule]:
        path = Path(rule_path)
        if path.suffix.lower() != self._JSON_SUFFIX:
            raise RuleLoadError(f"Unsupported rule file format: {path.suffix}")

        data = self._load_json(path)
        rules = [self._build_rule(item) for item in data]

        for rule in rules:
            try:
                self._validator.validate(rule)
            except RuleValidationError as exc:
                raise RuleLoadError(f"Invalid rule in {path}: {exc}") from exc

        return rules

    @staticmethod
    def _load_json(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            raise RuleLoadError(f"Rule file not found: {path}")

        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise RuleLoadError(f"Could not read rule file: {path}") from exc
        except json.JSONDecodeError as exc:
            raise RuleLoadError(f"Invalid JSON rule file: {path}") from exc

        if not isinstance(loaded, list):
            raise RuleLoadError("Rule JSON must contain a list of rule objects.")

        for item in loaded:
            if not isinstance(item, dict):
                raise RuleLoadError("Each rule entry must be a JSON object.")

        return loaded

    @staticmethod
    def _build_rule(data: dict[str, Any]) -> AdmissionRule:
        try:
            criticality = data["criticality"]
            if criticality is not None:
                criticality = str(criticality).upper()

            return AdmissionRule(
                hardware=str(data["hardware"]),
                period_ms=int(data["period_ms"]),
                criticality=criticality,
                max_complexity=float(data["max_complexity"]),
                description=str(data["description"]),
                source=str(data["source"]),
                validated=data["validated"],
            )
        except KeyError as exc:
            raise RuleLoadError(f"Missing rule field: {exc.args[0]}") from exc
        except (TypeError, ValueError) as exc:
            raise RuleLoadError("Rule contains invalid field types.") from exc

