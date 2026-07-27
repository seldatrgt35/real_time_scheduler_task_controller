"""Descriptor loading facade."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from task_admission_framework.descriptor.criticality import Criticality
from task_admission_framework.descriptor.exceptions import DescriptorLoadError
from task_admission_framework.descriptor.task_descriptor import TaskDescriptor


class DescriptorLoader(ABC):
    """Abstract contract for task descriptor loaders.

    Future implementations can load JSON, AUTOSAR OIL, or ECUC XML while
    preserving this public API.
    """

    @abstractmethod
    def load(self, descriptor_path: str | Path) -> TaskDescriptor:
        """Load a task descriptor from a supported source."""


class YamlDescriptorLoader(DescriptorLoader):
    """Loads task descriptors from YAML files."""

    _YAML_SUFFIXES = {".yaml", ".yml"}

    def load(self, descriptor_path: str | Path) -> TaskDescriptor:
        path = Path(descriptor_path)
        if path.suffix.lower() not in self._YAML_SUFFIXES:
            raise DescriptorLoadError(f"Unsupported descriptor format: {path.suffix}")

        data = self._load_yaml(path)
        return self._build_descriptor(data)

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise DescriptorLoadError(f"Descriptor file not found: {path}")

        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise DescriptorLoadError(f"Could not read descriptor file: {path}") from exc

        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            return self._parse_simple_yaml(text)

        try:
            loaded = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise DescriptorLoadError(f"Invalid YAML descriptor: {path}") from exc

        if not isinstance(loaded, dict):
            raise DescriptorLoadError("Descriptor YAML must contain a mapping.")

        return loaded

    @staticmethod
    def _parse_simple_yaml(text: str) -> dict[str, Any]:
        data: dict[str, Any] = {}

        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.split("#", maxsplit=1)[0].strip()
            if not line:
                continue

            if ":" not in line:
                raise DescriptorLoadError(
                    f"Invalid YAML line {line_number}: expected 'key: value'."
                )

            key, value = line.split(":", maxsplit=1)
            data[key.strip()] = YamlDescriptorLoader._parse_scalar(value.strip())

        return data

    @staticmethod
    def _parse_scalar(value: str) -> str | int:
        unquoted = value.strip("\"'")
        if unquoted.isdigit():
            return int(unquoted)
        return unquoted

    @staticmethod
    def _build_descriptor(data: dict[str, Any]) -> TaskDescriptor:
        try:
            return TaskDescriptor(
                task_name=str(data["task_name"]),
                entry_function=str(data["entry_function"]),
                period_ms=int(data["period_ms"]),
                deadline_ms=int(data["deadline_ms"]),
                priority=int(data["priority"]),
                stack_size=int(data.get("stack_size", 512)),
                criticality=YamlDescriptorLoader._parse_criticality(
                    data.get("criticality", "HIGH")
                ),
            )
        except KeyError as exc:
            raise DescriptorLoadError(f"Missing descriptor field: {exc.args[0]}") from exc
        except (TypeError, ValueError) as exc:
            raise DescriptorLoadError("Descriptor contains invalid field types.") from exc

    @staticmethod
    def _parse_criticality(value: Any) -> Criticality:
        criticality_name = str(value).upper()
        try:
            return Criticality[criticality_name]
        except KeyError as exc:
            raise DescriptorLoadError(
                f"Invalid criticality value: {criticality_name}"
            ) from exc
