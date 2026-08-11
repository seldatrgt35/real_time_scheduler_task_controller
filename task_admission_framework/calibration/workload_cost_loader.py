"""JSON loader for target-calibrated workload cost profiles."""

from __future__ import annotations

import json
from pathlib import Path

from task_admission_framework.calibration.workload_cost_profile import (
    WorkloadCostProfile,
    WorkloadGroupCorrection,
)


class WorkloadCostLoader:
    """Load and validate a dynamic workload calibration profile."""

    def load(self, profile_path: str | Path) -> WorkloadCostProfile:
        path = Path(profile_path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not load workload cost profile: {path}") from exc

        raw_costs = data.get("execution_time_us_per_work_unit")
        if not isinstance(raw_costs, dict) or not raw_costs:
            raise ValueError(
                "execution_time_us_per_work_unit must be a non-empty object."
            )

        costs = {
            str(name).strip().lower().replace("-", "_"): float(value)
            for name, value in raw_costs.items()
        }
        if any(value <= 0 for value in costs.values()):
            raise ValueError("All workload cost coefficients must be greater than 0.")

        safety_ratio = float(data.get("safety_limit_ratio", 0.8))
        if not 0 < safety_ratio <= 1:
            raise ValueError("safety_limit_ratio must be in the interval (0, 1].")
        intercept_us = float(data.get("intercept_us", 0.0))
        if intercept_us < 0:
            raise ValueError("intercept_us must be greater than or equal to 0.")
        estimate_margin_ratio = float(data.get("estimate_margin_ratio", 0.0))
        if estimate_margin_ratio < 0:
            raise ValueError(
                "estimate_margin_ratio must be greater than or equal to 0."
            )
        corrections: list[WorkloadGroupCorrection] = []
        for raw in data.get("group_corrections", []):
            classes = frozenset(
                str(name).strip().lower().replace("-", "_")
                for name in raw.get("workload_classes", [])
            )
            scale = float(raw.get("scale", 1.0))
            group_intercept = float(raw.get("intercept_us", 0.0))
            if not classes or scale <= 0 or group_intercept < 0:
                raise ValueError("Invalid workload group correction.")
            if not classes.issubset(costs):
                raise ValueError(
                    "Workload group correction contains an unknown class."
                )
            required_classes = frozenset(
                str(name).strip().lower().replace("-", "_")
                for name in raw.get("required_workload_classes", [])
            )
            if not required_classes.issubset(classes):
                raise ValueError(
                    "Required workload classes must belong to their correction group."
                )
            corrections.append(
                WorkloadGroupCorrection(
                    name=str(raw["name"]),
                    workload_classes=classes,
                    scale=scale,
                    intercept_us=group_intercept,
                    validated=bool(raw.get("validated", False)),
                    source=str(raw.get("source", "")),
                    require_all_classes=bool(raw.get("require_all_classes", False)),
                    required_workload_classes=required_classes,
                )
            )
        return WorkloadCostProfile(
            profile_id=str(data["profile_id"]),
            reference_hardware=str(data["reference_hardware"]),
            safety_limit_ratio=safety_ratio,
            validated=bool(data.get("validated", False)),
            execution_time_us_per_work_unit=costs,
            intercept_us=intercept_us,
            estimate_margin_ratio=estimate_margin_ratio,
            source=str(data.get("source", "")),
            group_corrections=tuple(corrections),
        )
