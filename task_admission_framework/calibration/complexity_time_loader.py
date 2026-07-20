"""JSON loader for complexity-time calibration profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from task_admission_framework.calibration.complexity_time_point import (
    ComplexityTimePoint,
)
from task_admission_framework.calibration.complexity_time_profile import (
    ComplexityTimeProfile,
)
from task_admission_framework.calibration.exceptions import CalibrationLoadError


class ComplexityTimeLoader:
    """Loads task-independent complexity-time calibration data from JSON."""

    def load(self, profile_path: str | Path) -> ComplexityTimeProfile:
        path = Path(profile_path)
        data = self._load_json(path)
        try:
            points = [
                ComplexityTimePoint(
                    complexity=float(item["complexity"]),
                    execution_time_ms=float(item["execution_time_ms"]),
                )
                for item in data["points"]
            ]
            profile = ComplexityTimeProfile(
                profile_id=str(data["profile_id"]),
                reference_hardware=str(data["reference_hardware"]),
                source=str(data["source"]),
                validated=bool(data["validated"]),
                points=sorted(points, key=lambda item: item.complexity),
            )
        except KeyError as exc:
            raise CalibrationLoadError(
                f"Missing calibration profile field: {exc.args[0]}"
            ) from exc
        except (TypeError, ValueError) as exc:
            raise CalibrationLoadError("Calibration profile has invalid field types.") from exc

        self._validate(profile)
        return profile

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise CalibrationLoadError(f"Calibration profile not found: {path}")

        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise CalibrationLoadError(f"Could not read calibration profile: {path}") from exc
        except json.JSONDecodeError as exc:
            raise CalibrationLoadError(f"Invalid JSON calibration profile: {path}") from exc

        if not isinstance(loaded, dict):
            raise CalibrationLoadError("Calibration profile JSON must be an object.")

        return loaded

    @staticmethod
    def _validate(profile: ComplexityTimeProfile) -> None:
        if not profile.points:
            raise CalibrationLoadError("Calibration profile must contain points.")

        previous_complexity = 0.0
        for point in profile.points:
            if point.complexity <= 0:
                raise CalibrationLoadError("Calibration complexity must be positive.")
            if point.execution_time_ms <= 0:
                raise CalibrationLoadError("Calibration execution time must be positive.")
            if point.complexity <= previous_complexity:
                raise CalibrationLoadError(
                    "Calibration complexity points must be strictly increasing."
                )
            previous_complexity = point.complexity

